# api/content_analysis.py
"""
Funktionen zur Analyse von Texten und Inhalten mit KI-Unterstützung.
"""

import json
import logging
import re
import time

from core.models import Flashcard, Question, Topic, Upload, db
from core.redis_client import redis_client

from .ai_utils import query_chatgpt
from .text_processing import clean_text_for_database, detect_language

logger = logging.getLogger(__name__)


def analyze_content(text, client, language='en', session_id=None, function_name="analyze_content"):
    """
    Analysiert den Inhalt eines Textes mittels KI, um Themen und Strukturen zu erkennen.

    Args:
        text: Der zu analysierende Text
        client: Der OpenAI-Client
        language: Die Sprache des Textes ('en' oder 'de')
        session_id: Session-ID für Tracking
        function_name: Name der Funktion für Logs

    Returns:
        dict: Analyseergebnisse mit Themen, Schlüsselkonzepten usw.
    """
    try:
        # System-Prompt basierend auf der Sprache
        if language == 'de':
            system_content = """Du bist ein KI-Assistent, der beim Lernen und Verstehen von Texten hilft.
            Deine Aufgabe ist es, einen Text zu analysieren und seine Hauptthemen, wichtigen Konzepte und
            Zusammenhänge zu identifizieren. Formatiere die Antwort als JSON."""

            user_prompt = f"""Analysiere den folgenden Text und extrahiere folgende Informationen:
            1. Das Hauptthema
            2. 4-6 wichtige Unterthemen
            3. 3-5 wichtige Konzepte oder Definitionen
            4. 2-3 potenzielle Prüfungsfragen zum Inhalt

            Gib deine Antwort als JSON mit den folgenden Feldern zurück:
            - main_topic (string): Das Hauptthema
            - subtopics (array of strings): Die wichtigsten Unterthemen
            - key_concepts (array of objects): Wichtige Konzepte mit jeweils einem "name" und einer "description"
            - possible_questions (array of strings): Mögliche Prüfungsfragen
            - summary (string): Eine kurze Zusammenfassung (max. 100 Wörter)

            Hier ist der Text:
            {text[:8000]}"""
        else:
            system_content = """You are an AI assistant helping with learning and understanding texts.
            Your task is to analyze a text and identify its main themes, important concepts, and
            relationships. Format the response as JSON."""

            user_prompt = f"""Analyze the following text and extract the following information:
            1. The main topic
            2. 4-6 important subtopics
            3. 3-5 key concepts or definitions
            4. 2-3 potential exam questions about the content

            Return your answer as JSON with the following fields:
            - main_topic (string): The main topic
            - subtopics (array of strings): The key subtopics
            - key_concepts (array of objects): Important concepts, each with a "name" and a "description"
            - possible_questions (array of strings): Possible exam questions
            - summary (string): A brief summary (max 100 words)

            Here's the text:
            {text[:8000]}"""

        # Sende die Anfrage an die KI
        response = query_chatgpt(
            prompt=user_prompt,
            client=client,
            system_content=system_content,
            temperature=0.7,
            use_cache=True,
            session_id=session_id,
            function_name=function_name
        )

        # Versuche, das JSON zu parsen
        try:
            # Entferne mögliche Markdown-Code-Blöcke
            json_text = re.sub(r'```json\s*|\s*```', '', response)
            result = json.loads(json_text)

            # Erweitere mit Metadaten
            result['language'] = language
            result['analysis_timestamp'] = int(time.time())

            return result
        except json.JSONDecodeError as json_err:
            logger.error("Fehler beim Parsen des JSON aus der AI-Antwort: %s", str(json_err))
            logger.debug("AI-Antwort war: %s", response)

            # Versuche ein alternatives Parsing
            try:
                # Extrahiere alles zwischen geschweiften Klammern
                json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
                json_matches = re.findall(json_pattern, response)

                if json_matches:
                    result = json.loads(json_matches[0])
                    result['language'] = language
                    result['analysis_timestamp'] = int(time.time())
                    return result
            except Exception as e:
                logger.error("Alternativer JSON-Parsing-Versuch fehlgeschlagen: %s", str(e))

            # Fallback: Gib ein Minimal-Ergebnis zurück
            return {
                "main_topic": "Topic extraction failed",
                "subtopics": ["Error processing content"],
                "key_concepts": [],
                "possible_questions": [],
                "summary": "There was an error analyzing the content.",
                "language": language,
                "analysis_timestamp": int(time.time())
            }
    except Exception as e:
        logger.error("Fehler bei der Inhaltsanalyse: %s", str(e))
        return {
            "main_topic": "Error",
            "subtopics": ["Error processing content"],
            "key_concepts": [],
            "possible_questions": [],
            "summary": "There was an error analyzing the content.",
            "language": language,
            "analysis_timestamp": int(time.time())
        }


def generate_concept_map_suggestions(text, client, main_topic, parent_subtopics, language='en', analysis_data=None):
    """
    Generiert Vorschläge für eine Concept Map basierend auf dem Text und der Analyse.

    Args:
        text: Der Quelltext
        client: Der OpenAI-Client
        main_topic: Das Hauptthema
        parent_subtopics: Die übergeordneten Unterthemen
        language: Die Sprache ('en' oder 'de')
        analysis_data: Optional, bereits vorhandene Analysedaten

    Returns:
        dict: Vorschläge für eine Concept Map mit Topics und Connections
    """
    try:
        # Verwende vorhandene Analyse, falls verfügbar
        if not analysis_data:
            analysis_data = analyze_content(text, client, language)

        # System-Prompt basierend auf der Sprache
        if language == 'de':
            system_content = """Du bist ein KI-Assistent, der beim Erstellen von Concept Maps hilft.
            Deine Aufgabe ist es, Beziehungen zwischen Konzepten in einem Text zu identifizieren und
            eine Struktur vorzuschlagen, die als Concept Map visualisiert werden kann."""

            user_prompt = f"""Basierend auf dem folgenden Textinhalt und den bereits identifizierten Hauptthemen,
            erstelle eine Concept-Map-Struktur. Das Hauptthema ist: "{main_topic}".

            Die Unterthemen sind: {', '.join([f'"{topic}"' for topic in parent_subtopics[:5]])}

            Identifiziere für jedes Unterthema zusätzliche untergeordnete Themen (2-3 pro Unterthema) und
            beschreibe die Beziehungen zwischen allen Themen.

            Gib deine Antwort als JSON mit den folgenden Feldern zurück:
            - topics: Ein Array von Themen-Objekten mit:
              - id: Eine eindeutige ID (verwende fortlaufende Zahlen)
              - name: Der Name des Themas
              - description: Eine kurze Beschreibung des Themas
              - level: Die Hierarchieebene (0 für Hauptthema, 1 für Unterthemen, 2 für untergeordnete Themen)
              - parent_id: Die ID des übergeordneten Themas (null für das Hauptthema)

            - connections: Ein Array von Verbindungs-Objekten mit:
              - source_id: Die ID des Quellthemas
              - target_id: Die ID des Zielthemas
              - relationship: Die Beschreibung der Beziehung zwischen den Themen

            Der Textinhalt ist (nur die ersten 5000 Zeichen werden angezeigt):
            {text[:5000]}"""
        else:
            system_content = """You are an AI assistant helping with creating concept maps.
            Your task is to identify relationships between concepts in a text and suggest
            a structure that can be visualized as a concept map."""

            user_prompt = f"""Based on the following text content and the already identified main topics,
            create a concept map structure. The main topic is: "{main_topic}".

            The subtopics are: {', '.join([f'"{topic}"' for topic in parent_subtopics[:5]])}

            For each subtopic, identify additional child topics (2-3 per subtopic) and describe
            the relationships between all topics.

            Return your answer as JSON with the following fields:
            - topics: An array of topic objects with:
              - id: A unique ID (use sequential numbers)
              - name: The name of the topic
              - description: A short description of the topic
              - level: The hierarchy level (0 for main topic, 1 for subtopics, 2 for child topics)
              - parent_id: The ID of the parent topic (null for the main topic)

            - connections: An array of connection objects with:
              - source_id: The ID of the source topic
              - target_id: The ID of the target topic
              - relationship: The description of the relationship between the topics

            The text content is (only the first 5000 characters are shown):
            {text[:5000]}"""

        # Sende die Anfrage an die KI
        response = query_chatgpt(
            prompt=user_prompt,
            client=client,
            system_content=system_content,
            temperature=0.7,
            use_cache=True,
            function_name="generate_concept_map_suggestions"
        )

        # Versuche, das JSON zu parsen
        try:
            # Entferne mögliche Markdown-Code-Blöcke
            json_text = re.sub(r'```json\s*|\s*```', '', response)
            result = json.loads(json_text)

            # Validiere und ergänze die Ergebnisse
            if 'topics' not in result or 'connections' not in result:
                raise ValueError("Missing required fields in response")

            # Stelle sicher, dass das Hauptthema die ID 1 hat
            main_topic_exists = False
            for topic in result['topics']:
                if topic.get('level') == 0:
                    main_topic_exists = True
                    break

            if not main_topic_exists and len(result['topics']) > 0:
                # Füge Hauptthema hinzu, falls nicht vorhanden
                result['topics'].insert(0, {
                    "id": 1,
                    "name": main_topic,
                    "description": "Hauptthema",
                    "level": 0,
                    "parent_id": None
                })

            return result
        except json.JSONDecodeError as json_err:
            logger.error("Fehler beim Parsen des JSON aus der AI-Antwort: %s", str(json_err))
            logger.debug("AI-Antwort war: %s", response)

            # Fallback: Erzeuge eine minimale Concept Map
            topics = [{
                "id": 1,
                "name": main_topic,
                "description": "Hauptthema",
                "level": 0,
                "parent_id": None
            }]

            # Füge Unterthemen hinzu
            connections = []
            for i, subtopic in enumerate(parent_subtopics[:5], start=2):
                topics.append({
                    "id": i,
                    "name": subtopic,
                    "description": f"Unterthema zu {main_topic}",
                    "level": 1,
                    "parent_id": 1
                })

                connections.append({
                    "source_id": 1,
                    "target_id": i,
                    "relationship": "enthält"
                })

            return {
                "topics": topics,
                "connections": connections
            }
    except Exception as e:
        logger.error("Fehler beim Generieren der Concept Map: %s", str(e))

        # Fallback: Erzeuge eine minimale Concept Map
        topics = [{
            "id": 1,
            "name": main_topic,
            "description": "Hauptthema",
            "level": 0,
            "parent_id": None
        }]

        # Füge Unterthemen hinzu
        connections = []
        for i, subtopic in enumerate(parent_subtopics[:5], start=2):
            topics.append({
                "id": i,
                "name": subtopic,
                "description": f"Unterthema zu {main_topic}",
                "level": 1,
                "parent_id": 1
            })

            connections.append({
                "source_id": 1,
                "target_id": i,
                "relationship": "enthält"
            })

        return {
            "topics": topics,
            "connections": connections
        }


def unified_content_processing(text, client, file_names=None, user_id=None,
                               language=None, max_retries=3, session_id=None):
    """
    Einheitliche Verarbeitung eines Textes, von der Analyse bis zur Generierung von Lernmaterialien.

    Args:
        text: Der zu verarbeitende Text
        client: Der OpenAI-Client
        file_names: Optionale Liste von Dateinamen als Kontext
        user_id: Optionale Benutzer-ID
        language: Optionale Sprache des Textes (wird sonst erkannt)
        max_retries: Maximale Anzahl von Wiederholungsversuchen
        session_id: ID der aktuellen Session

    Returns:
        dict: Ergebnisse der Verarbeitung mit Analysen und Lernmaterialien
    """
    try:
        # Bereinige den Text für die Datenbank
        cleaned_text = clean_text_for_database(text)

        # Erkenne die Sprache, falls nicht angegeben
        if not language:
            language = detect_language(cleaned_text)

        # Aktualisiere den Redis-Fortschritt
        if session_id:
            redis_client.set(f"processing_status:{session_id}", "analyzing")
            redis_client.set(f"processing_progress:{session_id}", "10")

        # Führe die Inhaltsanalyse durch
        logger.info("Beginne Inhaltsanalyse für Session %s", session_id)
        analysis_result = analyze_content(
            text=cleaned_text,
            client=client,
            language=language,
            session_id=session_id,
            function_name="unified_content_processing"
        )

        # Aktualisiere den Redis-Fortschritt
        if session_id:
            redis_client.set(f"processing_progress:{session_id}", "30")

        # Extrahiere das Hauptthema und Unterthemen
        main_topic = analysis_result.get('main_topic', "Unknown Topic")
        subtopics = analysis_result.get('subtopics', [])

        # Generiere die Concept Map
        logger.info("Generiere Concept Map für Session %s", session_id)
        concept_map_result = generate_concept_map_suggestions(
            text=cleaned_text,
            client=client,
            main_topic=main_topic,
            parent_subtopics=subtopics,
            language=language,
            analysis_data=analysis_result
        )

        # Aktualisiere den Redis-Fortschritt
        if session_id:
            redis_client.set(f"processing_progress:{session_id}", "50")

        # Extrahiere Themen und Verbindungen
        topics = concept_map_result.get('topics', [])
        connections = concept_map_result.get('connections', [])

        # Generiere Fragen und Flashcards (von anderen Modulen abgedeckt)
        from .learning_materials import (generate_additional_flashcards,
                                         generate_additional_questions)

        # Aktualisiere den Redis-Fortschritt
        if session_id:
            redis_client.set(f"processing_progress:{session_id}", "70")

        # Generiere Fragen
        questions = generate_additional_questions(
            text=cleaned_text,
            client=client,
            analysis=analysis_result,
            existing_questions=[],
            num_to_generate=5,
            language=language,
            session_id=session_id
        )

        # Aktualisiere den Redis-Fortschritt
        if session_id:
            redis_client.set(f"processing_progress:{session_id}", "80")

        # Generiere Flashcards
        flashcards = generate_additional_flashcards(
            text=cleaned_text,
            client=client,
            analysis=analysis_result,
            existing_flashcards=[],
            num_to_generate=10,
            language=language,
            session_id=session_id
        )

        # Aktualisiere den Redis-Fortschritt
        if session_id:
            redis_client.set(f"processing_progress:{session_id}", "90")

        # Wenn eine Session-ID angegeben ist, speichere die Ergebnisse in der Datenbank
        if session_id:
            logger.info("Speichere Ergebnisse in der Datenbank für Session %s", session_id)
            try:
                # Hole den Upload
                upload = Upload.query.filter_by(session_id=session_id).first()

                if not upload:
                    logger.warning("Kein Upload für Session %s gefunden", session_id)
                else:
                    # Speichere die Themen
                    topics_by_id = {}
                    for topic_data in topics:
                        topic = Topic(
                            upload_id=upload.id,
                            name=topic_data.get('name', ''),
                            description=topic_data.get('description', ''),
                            level=topic_data.get('level', 0),
                            parent_id=topic_data.get('parent_id'),
                            original_id=topic_data.get('id'),
                            is_main_topic=topic_data.get('level', 0) == 0
                        )
                        db.session.add(topic)
                        topics_by_id[topic_data.get('id')] = topic
                    
                    # Commit, um IDs für die Themen zu erhalten
                    db.session.commit()
                    
                    # Verarbeite die Verbindungen, um parent_id zu setzen und descriptions zu erweitern
                    for connection_data in connections:
                        source_id = connection_data.get('source_id')
                        target_id = connection_data.get('target_id')
                        relationship = connection_data.get('relationship', '')
                        
                        if source_id in topics_by_id and target_id in topics_by_id:
                            target_topic = topics_by_id[target_id]
                            source_topic = topics_by_id[source_id]
                            
                            # Setze die parent_id beim Ziel-Topic
                            target_topic.parent_id = source_topic.id
                            
                            # Erweitere die Beschreibung um die Beziehungsinformation
                            if relationship and relationship not in target_topic.description:
                                if target_topic.description:
                                    target_topic.description += f" ({relationship})"
                                else:
                                    target_topic.description = f"({relationship})"
                            
                            db.session.add(target_topic)
                    
                    # Commit der Topic-Änderungen
                    db.session.commit()

                    # Speichere die Fragen
                    for question_data in questions:
                        question = Question(
                            upload_id=upload.id,
                            question=question_data.get('question', ''),
                            answer=question_data.get('answer', ''),
                            difficulty=question_data.get('difficulty', 'medium'),
                            topic=question_data.get('topic', '')
                        )
                        db.session.add(question)

                    # Speichere die Flashcards
                    for flashcard_data in flashcards:
                        flashcard = Flashcard(
                            upload_id=upload.id,
                            front=flashcard_data.get('front', ''),
                            back=flashcard_data.get('back', ''),
                            difficulty=flashcard_data.get('difficulty', 'medium'),
                            topic=flashcard_data.get('topic', '')
                        )
                        db.session.add(flashcard)

                    # Commit aller Änderungen
                    db.session.commit()
            except Exception as db_err:
                logger.error("Fehler beim Speichern der Ergebnisse in der Datenbank: %s", str(db_err))
                db.session.rollback()

        # Aktualisiere den Redis-Fortschritt
        if session_id:
            redis_client.set(f"processing_status:{session_id}", "completed")
            redis_client.set(f"processing_progress:{session_id}", "100")

        # Erstelle das Ergebnis
        result = {
            "success": True,
            "analysis": analysis_result,
            "concept_map": concept_map_result,
            "questions": questions,
            "flashcards": flashcards,
            "language": language
        }

        return result
    except Exception as e:
        logger.error("Fehler bei der einheitlichen Inhaltsverarbeitung: %s", str(e))

        # Setze Fehlerstatus in Redis
        if session_id:
            redis_client.set(f"processing_status:{session_id}", "error")
            redis_client.set(f"error_details:{session_id}", str(e))

        # Gib ein Minimalergebnis zurück
        return {
            "success": False,
            "error": str(e),
            "analysis": {},
            "concept_map": {},
            "questions": [],
            "flashcards": [],
            "language": language or "unknown"
        }
