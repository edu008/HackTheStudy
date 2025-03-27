"""
Topic-Generierung
--------------

Dieses Modul enthält Funktionen zur automatischen Generierung von Topics
und deren Verbindungen.
"""

import logging
import uuid
from datetime import datetime
import tiktoken
import json
import time
from flask import current_app, g
from ..utils import query_chatgpt, detect_language
from core.models import db, Upload, Topic, Connection, User
from api.token_tracking import check_credits_available, calculate_token_cost, deduct_credits
from openai import OpenAI
from api.error_handler import InvalidInputError, ResourceNotFoundError, InsufficientCreditsError
from .utils import get_openai_client, process_topic_response, build_topic_prompt, find_upload_by_session
from .models import create_topic, create_connection, find_topic_by_name, create_topics_from_list, create_connections_from_list

logger = logging.getLogger(__name__)

def generate_topics(session_id, user_id=None):
    """
    Generiert Topics für eine Sitzung und erzeugt eine Concept Map.
    
    Args:
        session_id: Die ID der Sitzung
        user_id: Die ID des Benutzers (optional)
        
    Returns:
        dict: Status-Informationen zur Topic-Generierung
    """
    try:
        upload = find_upload_by_session(session_id)
        if not upload:
            logger.error(f"Upload not found for session ID: {session_id}")
            raise ResourceNotFoundError("Upload nicht gefunden")
        
        # Prüfe, ob bereits Topics existieren
        existing_topics = Topic.query.filter_by(upload_id=upload.id).first()
        if existing_topics:
            logger.info(f"Topics already exist for session ID: {session_id}")
            return {"success": True, "message": "Topics bereits generiert"}
        
        # Prüfe, ob genügend Credits vorhanden sind
        user = User.query.get(user_id) if user_id else None
        credit_cost = _calculate_generation_cost(upload.content)
        
        if user and not check_credits_available(user.id, credit_cost):
            logger.warning(f"Insufficient credits for user ID: {user_id}, required: {credit_cost}")
            raise InsufficientCreditsError(
                "Nicht genügend Credits für die Generierung von Topics",
                required_credits=credit_cost
            )
        
        # Generiere Haupttopics aus dem Inhalt
        language = detect_language(upload.content)
        topics, concept_map = _generate_main_topics(upload.content, language)
        
        # Erstelle Haupttopic und Subtopics in der Datenbank
        if topics and len(topics) > 0:
            main_topic = create_topic(upload.id, topics[0], True)
            
            # Erstelle Subtopics
            for i in range(1, len(topics)):
                create_topic(upload.id, topics[i], False, main_topic.id)
            
            # Erstelle Verbindungen, falls vorhanden
            if concept_map:
                for connection in concept_map:
                    source_name = connection.get("source")
                    target_name = connection.get("target")
                    label = connection.get("label", "related to")
                    
                    source = find_topic_by_name(upload.id, source_name)
                    target = find_topic_by_name(upload.id, target_name)
                    
                    if source and target:
                        create_connection(upload.id, source.id, target.id, label)
            
            # Speichere Änderungen in der Datenbank
            db.session.commit()
            
            # Ziehe Credits ab, wenn ein Benutzer angegeben ist
            if user:
                deduct_credits(user.id, credit_cost, f"Topic generation for session {session_id}")
            
            return {
                "success": True,
                "message": "Topics erfolgreich generiert",
                "topics_count": len(topics),
                "main_topic": topics[0] if topics else None
            }
        else:
            logger.error(f"No topics generated for session ID: {session_id}")
            return {"success": False, "message": "Keine Topics generiert"}
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error generating topics: {str(e)}")
        if isinstance(e, (InvalidInputError, ResourceNotFoundError, InsufficientCreditsError)):
            raise
        return {"success": False, "message": f"Fehler bei der Generierung von Topics: {str(e)}"}

def generate_related_topics(session_id, user_id=None):
    """
    Generiert verwandte Topics für bereits bestehende Topics.
    
    Args:
        session_id: Die ID der Sitzung
        user_id: Die ID des Benutzers (optional)
        
    Returns:
        dict: Informationen zu den generierten verwandten Topics
    """
    try:
        upload = find_upload_by_session(session_id)
        if not upload:
            logger.error(f"Upload not found for session ID: {session_id}")
            raise ResourceNotFoundError("Upload nicht gefunden")
        
        # Hole das Haupttopic und Subtopics
        main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
        if not main_topic:
            logger.error(f"Main topic not found for session ID: {session_id}")
            raise ResourceNotFoundError("Hauptthema nicht gefunden")
            
        subtopics = Topic.query.filter_by(upload_id=upload.id, parent_id=main_topic.id).all()
        if not subtopics:
            logger.error(f"No subtopics found for session ID: {session_id}")
            raise ResourceNotFoundError("Keine Unterthemen gefunden")
        
        # Prüfe, ob genügend Credits vorhanden sind
        user = User.query.get(user_id) if user_id else None
        credit_cost = 50  # Standardkosten für die Generierung verwandter Topics
        
        if user and not check_credits_available(user.id, credit_cost):
            logger.warning(f"Insufficient credits for user ID: {user_id}, required: {credit_cost}")
            raise InsufficientCreditsError(
                "Nicht genügend Credits für die Generierung verwandter Topics",
                required_credits=credit_cost
            )
        
        # Generiere verwandte Topics
        language = detect_language(upload.content)
        client = get_openai_client()
        prompt = build_topic_prompt(main_topic, subtopics, language)
        
        # Generiere Vorschläge mit OpenAI
        response = query_chatgpt(prompt, client)
        logger.info(f"OpenAI response for related topics:\n{response}")
        
        # Verarbeite die Antwort und extrahiere die Topics und Verbindungen
        new_topics, new_connections = process_topic_response(response)
        
        # Speichere die neuen Topics und Verbindungen in der Datenbank
        if len(new_topics) > 0:
            # Erstelle neue Topics mit korrekter Verknüpfung zu Subtopics
            if len(new_topics) == len(subtopics):
                for i, (subtopic, new_topic_name) in enumerate(zip(subtopics, new_topics)):
                    create_topic(upload.id, new_topic_name, False, subtopic.id)
            else:
                # Wenn die Anzahl nicht übereinstimmt, erstelle sie mit Haupttopic als Parent
                for new_topic_name in new_topics:
                    create_topic(upload.id, new_topic_name, False, main_topic.id)
            
            # Erstelle neue Verbindungen
            for conn in new_connections:
                source_text = conn.get("source_text")
                target_text = conn.get("target_text")
                label = conn.get("label")
                
                source = find_topic_by_name(upload.id, source_text)
                target = find_topic_by_name(upload.id, target_text)
                
                if source and target:
                    create_connection(upload.id, source.id, target.id, label)
            
            # Speichere Änderungen in der Datenbank
            db.session.commit()
            
            # Ziehe Credits ab, wenn ein Benutzer angegeben ist
            if user:
                deduct_credits(user.id, credit_cost, f"Related topic generation for session {session_id}")
            
            return {
                "success": True,
                "message": "Verwandte Topics erfolgreich generiert",
                "new_topics_count": len(new_topics),
                "new_connections_count": len(new_connections)
            }
        else:
            logger.error(f"No related topics generated for session ID: {session_id}")
            return {"success": False, "message": "Keine verwandten Topics generiert"}
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error generating related topics: {str(e)}")
        if isinstance(e, (InvalidInputError, ResourceNotFoundError, InsufficientCreditsError)):
            raise
        return {"success": False, "message": f"Fehler bei der Generierung verwandter Topics: {str(e)}"}

def _generate_main_topics(content, language='en'):
    """
    Generiert Haupttopics und deren Verbindungen aus dem Inhalt.
    
    Args:
        content: Der Inhalt, aus dem Topics generiert werden sollen
        language: Die Sprache des Inhalts
        
    Returns:
        tuple: (list[str], list[dict]) - Liste der Topics und Liste der Verbindungen
    """
    client = get_openai_client()
    
    # Gekürzte Version für lange Inhalte
    if len(content) > 10000:
        content = content[:9500] + "...\n[Text gekürzt]"
    
    # Prompt je nach Sprache
    if language != 'de':
        prompt = f"""
        Please analyze the following content and extract the main topics and subtopics:

        {content}

        First, identify the single most important main topic that encompasses the entire content.
        Then, identify 5-10 key subtopics (important concepts or themes) related to the main topic.

        Format your response as follows:
        Main Topic: [Main Topic Name]
        Subtopics:
        - [Subtopic 1]
        - [Subtopic 2]
        ...

        Additionally, suggest a concept map showing how these topics relate to each other.
        Format the concept map suggestions as:
        
        Concept Map:
        - source: [Topic A], target: [Topic B], label: [relationship description]
        - source: [Topic C], target: [Topic D], label: [relationship description]
        ...

        IMPORTANT RULES:
        - The main topic should be clear, specific and descriptive (not generic like "Text Analysis")
        - Subtopics should be relevant and specific
        - Each topic should be max 5 words
        - Use only topics that are explicitly mentioned or strongly implied in the text
        - For the concept map, create 5-8 meaningful connections
        - Make sure all topics and relationships are grammatically correct
        """
    else:
        prompt = f"""
        Bitte analysiere den folgenden Inhalt und extrahiere die Hauptthemen und Unterthemen:

        {content}

        Identifiziere zuerst das wichtigste Hauptthema, das den gesamten Inhalt umfasst.
        Identifiziere dann 5-10 wichtige Unterthemen (wichtige Konzepte oder Themen), die mit dem Hauptthema zusammenhängen.

        Formatiere deine Antwort wie folgt:
        Hauptthema: [Name des Hauptthemas]
        Unterthemen:
        - [Unterthema 1]
        - [Unterthema 2]
        ...

        Schlage zusätzlich eine Concept Map vor, die zeigt, wie diese Themen miteinander verbunden sind.
        Formatiere die Concept Map-Vorschläge so:
        
        Concept Map:
        - source: [Thema A], target: [Thema B], label: [Beschreibung der Beziehung]
        - source: [Thema C], target: [Thema D], label: [Beschreibung der Beziehung]
        ...

        WICHTIGE REGELN:
        - Das Hauptthema sollte klar, spezifisch und beschreibend sein (nicht generisch wie "Textanalyse")
        - Unterthemen sollten relevant und spezifisch sein
        - Jedes Thema sollte maximal 5 Wörter umfassen
        - Verwende nur Themen, die im Text explizit erwähnt oder stark impliziert werden
        - Erstelle für die Concept Map 5-8 sinnvolle Verbindungen
        - Stelle sicher, dass alle Themen und Beziehungen grammatikalisch korrekt sind
        """
    
    try:
        response = query_chatgpt(prompt, client)
        logger.info(f"OpenAI response for main topics:\n{response}")
        
        topics = []
        concept_map = []
        
        # Extrahiere Hauptthema und Unterthemen
        main_topic_prefix = "Hauptthema:" if language == 'de' else "Main Topic:"
        subtopics_prefix = "Unterthemen:" if language == 'de' else "Subtopics:"
        concept_map_prefix = "Concept Map:"
        
        lines = response.strip().split('\n')
        parsing_main = False
        parsing_subtopics = False
        parsing_concept_map = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith(main_topic_prefix):
                parsing_main = True
                parsing_subtopics = False
                parsing_concept_map = False
                main_topic = line[len(main_topic_prefix):].strip()
                topics.append(main_topic)
                
            elif line.startswith(subtopics_prefix):
                parsing_main = False
                parsing_subtopics = True
                parsing_concept_map = False
                
            elif line.startswith(concept_map_prefix):
                parsing_main = False
                parsing_subtopics = False
                parsing_concept_map = True
                
            elif parsing_subtopics and line.startswith("-"):
                subtopic = line[1:].strip()
                topics.append(subtopic)
                
            elif parsing_concept_map and line.startswith("-"):
                connection_text = line[1:].strip()
                # Extrahiere source, target und label
                try:
                    source_part = connection_text.split("source:")[1].split(",")[0].strip()
                    target_part = connection_text.split("target:")[1].split(",")[0].strip()
                    label_part = connection_text.split("label:")[1].strip()
                    
                    concept_map.append({
                        "source": source_part,
                        "target": target_part,
                        "label": label_part
                    })
                except:
                    logger.warning(f"Could not parse connection: {connection_text}")
        
        logger.info(f"Extracted topics: {topics}")
        logger.info(f"Extracted concept map: {concept_map}")
        
        return topics, concept_map
    except Exception as e:
        logger.error(f"Error generating main topics: {str(e)}")
        # Fallback zu einem einfachen Haupttopic
        fallback_topic = "Generated Content" if language != 'de' else "Generierter Inhalt"
        return [fallback_topic], []

def _calculate_generation_cost(content):
    """
    Berechnet die Kosten für die Generierung von Topics.
    
    Args:
        content: Der Inhalt, aus dem Topics generiert werden sollen
        
    Returns:
        int: Die berechneten Kosten
    """
    # Grundkosten für kurze Inhalte
    base_cost = 30
    
    # Zusätzliche Kosten basierend auf Tokenzahl
    try:
        tokens = len(tiktoken.encoding_for_model("gpt-4").encode(content[:10000]))
        token_cost = tokens // 1000  # 1 Credit pro 1000 Tokens
    except:
        # Fallback, wenn Tokenizer nicht verfügbar ist
        token_cost = len(content) // 2000  # Ungefähre Schätzung
    
    total_cost = base_cost + token_cost
    
    # Maximalkosten begrenzen
    return min(total_cost, 100) 