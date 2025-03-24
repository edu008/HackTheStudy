from flask import request, jsonify, current_app, g, Blueprint
from . import api_bp
from .utils import query_chatgpt, detect_language, generate_concept_map_suggestions, check_and_manage_user_sessions
from core.models import db, Upload, Topic, UserActivity, Connection, User
import logging
from .auth import token_required
import uuid
from datetime import datetime
import tiktoken
import json
import time
from api.token_tracking import check_credits_available, calculate_token_cost, deduct_credits
import os
from openai import OpenAI
from api.error_handler import InvalidInputError, ResourceNotFoundError, InsufficientCreditsError

logger = logging.getLogger(__name__)

@api_bp.route('/load-topics', methods=['POST', 'OPTIONS'])
def load_topics():
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        return response
        
    # Authentifizierung für nicht-OPTIONS Anfragen
    auth_decorator = token_required(lambda: None)
    auth_result = auth_decorator()
    if auth_result is not None:
        return auth_result
    
    try:
        user_id = getattr(request, 'user_id', None)
        
        # Überprüfe und verwalte die Anzahl der Sessions des Benutzers
        if user_id:
            check_and_manage_user_sessions(user_id)
        
        # Generiere eine neue Session-ID
        session_id = str(uuid.uuid4())
        
        logger.info(f"Creating new session with ID: {session_id} for user: {user_id}")
        
        # Rückgabe der neuen Session-ID
        return jsonify({
            "success": True,
            "message": "Session zurückgesetzt und neue Session erstellt",
            "session_id": session_id
        }), 200
    except Exception as e:
        logger.error(f"Error resetting session: {str(e)}")
        return jsonify({"success": False, "message": f"Fehler beim Zurücksetzen der Session: {str(e)}"}), 500

@api_bp.route('/generate-related-topics', methods=['POST', 'OPTIONS'])
def generate_related_topics():
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        return response

    # Führe Authentifizierung durch
    auth_decorator = token_required(lambda: None)
    auth_result = auth_decorator()
    if auth_result is not None:
        return auth_result
    
    data = request.json
    session_id = data.get('session_id')
    if not session_id:
        return jsonify({"success": False, "error": {"code": "NO_SESSION_ID", "message": "Session ID required"}}), 400
    
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
    
    main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
    subtopics = Topic.query.filter_by(upload_id=upload.id, parent_id=main_topic.id).all() if main_topic else []
    language = detect_language(upload.content)
    
    client = OpenAI(api_key=current_app.config['OPENAI_API_KEY'])
    prompt = (
        f"""
        Based on the following topics, suggest exactly one new related topic for each subtopic (except the main topic) and create connections between these topics. Analyze the content relationships and provide a precise, detailed description for each connection as a label. The main topic should also be linked to at least one of the new topics.

        Main Topic: {main_topic.name}
        Subtopics: {', '.join([s.name for s in subtopics])}

        Format:
        New Topics: [Topic1, Topic2, Topic3, ...]
        New Connections:
        - source_text:Topic1:target_text:Topic2:label:Detailed description of the relationship
        - source_text:Topic3:target_text:Topic4:label:Detailed description of the relationship

        IMPORTANT: For connections, use EXACTLY the format shown above with colons separating the fields.
        For example:
        - source_text:Economics:target_text:Market Failures:label:Economics explains the concept of market failures, which are situations where the free market fails to allocate resources efficiently.

        Rules:
        - Generate exactly 1 new related topic for each subtopic (except the main topic).
        - DO NOT use generic names like "Related Topic X".
        - DO NOT use numbering or bullet points for the new topics.
        - Each new topic must have a specific, descriptive name that clearly reflects the content.
        - Create connections between each subtopic and its new topic.
        - Create at least one connection between the main topic and one of the new topics.
        - Provide a DETAILED, SPECIFIC description for EVERY connection as the 'label' field (e.g., 'explains', 'is a subset of', 'influences', with a brief explanation like "explains the economic impact").
        - Ensure the answer strictly follows the specified format and each connection starts with a '-'.
        - All topics must be technically correct and relevant to the main topic.
        - If a description is missing, infer a logical relationship based on the context (e.g., 'relates to' with a brief explanation).
        """ if language != 'de' else
        f"""
        Basierend auf den folgenden Themen, schlage für jedes Subthema (ausser dem Hauptthema) genau ein neues verwandtes Thema vor und erstelle Verbindungen zwischen diesen Themen. Analysiere die inhaltlichen Zusammenhänge und gib für jede Verbindung eine präzise, detaillierte Beschreibung als Label an. Das Hauptthema sollte ebenfalls mit mindestens einem der neuen Themen verknüpft werden.

        Hauptthema: {main_topic.name}
        Subthemen: {', '.join([s.name for s in subtopics])}

        Format:
        Neue Themen: [Thema1, Thema2, Thema3, ...]
        Neue Verbindungen:
        - source_text:Thema1:target_text:Thema2:label:Beschreibung der Beziehung
        - source_text:Thema3:target_text:Thema4:label:Beschreibung der Beziehung

        WICHTIG: Für Verbindungen, verwende GENAU das oben gezeigte Format mit Doppelpunkten zur Trennung der Felder.
        Zum Beispiel:
        - source_text:Wirtschaft:target_text:Marktversagen:label:Wirtschaft erklärt das Konzept des Marktversagens, bei dem der freie Markt Ressourcen nicht effizient zuteilen kann.

        Regeln:
        - Generiere für jedes Subthema (ausser dem Hauptthema) genau 1 neues verwandtes Thema.
        - Verwende KEINE generischen Namen wie "Verwandtes Thema X".
        - Verwende KEINE Nummerierung oder Aufzählungszeichen bei den neuen Themen.
        - Jedes neue Thema muss einen spezifischen, beschreibenden Namen haben, der den Inhalt klar widerspiegelt.
        - Erstelle Verbindungen zwischen jedem Subthema und seinem neuen Thema.
        - Erstelle mindestens eine Verbindung zwischen dem Hauptthema und einem der neuen Themen.
        - Gib für JEDEN Verbindungsweg eine DETALLIERTE, SPEZIFISCHE Beschreibung als 'label'-Feld an (z. B. 'erklärt', 'ist eine Untermenge von', 'beeinflusst', mit einer kurzen Erklärung wie "erklärt den wirtschaftlichen Einfluss").
        - Stelle sicher, dass die Antwort strikt dem angegebenen Format entspricht und jede Verbindung mit einem '-' beginnt.
        - Alle Themen müssen fachlich korrekt und relevant für das Hauptthema sein.
        - Wenn eine Beschreibung fehlt, schlussfolgere eine logische Beziehung basierend auf dem Kontext (z. B. 'bezieht sich auf' mit einer kurzen Erklärung).
        """
    )
    
    try:
        # Verwende die query_chatgpt Funktion anstatt direkten API-Aufrufs
        response = query_chatgpt(prompt, client)
        logger.info(f"OpenAI response for related topics:\n{response}")
        new_topics = []
        new_connections = []
        lines = response.split('\n')
        in_topics = False
        in_connections = False
        
        # Parse the response to extract new topics and connections
        new_topics = []
        new_connections = []
        in_topics = False
        in_connections = False
        
        for line in lines:
            line = line.strip()
            if line.startswith("Neue Themen:") or line.startswith("New Topics:"):
                in_topics = True
                in_connections = False
                # Check if the topics are on the same line
                topics_str = line[line.find(":") + 1:].strip()
                if topics_str.startswith("[") and topics_str.endswith("]"):
                    # Parse comma-separated list
                    topics_str = topics_str[1:-1]
                    new_topics = [t.strip() for t in topics_str.split(",") if t.strip()]
            elif in_topics and (line.startswith("Neue Verbindungen:") or line.startswith("New Connections:")):
                in_topics = False
                in_connections = True
            elif in_topics and line.strip() and not line.startswith("Neue Verbindungen:") and not line.startswith("New Connections:"):
                # Parse numbered list format (e.g., "1. Topic Name")
                if line[0].isdigit() and "." in line:
                    topic_name = line[line.find(".") + 1:].strip()
                    if topic_name:
                        new_topics.append(topic_name)
            elif line.startswith("Neue Verbindungen:") or line.startswith("New Connections:"):
                in_topics = False
                in_connections = True
            elif in_connections and line.startswith('-'):
                # Handle connections that might span multiple lines
                connection_text = line.strip()
                
                # If the next line doesn't start with a dash, it's a continuation of this connection
                next_line_index = lines.index(line) + 1
                while next_line_index < len(lines) and not lines[next_line_index].strip().startswith('-') and lines[next_line_index].strip():
                    connection_text += " " + lines[next_line_index].strip()
                    next_line_index += 1
                
                # Now parse the complete connection text
                parts = connection_text[1:].strip().split(':')
                if len(parts) >= 5:
                    source_text = parts[1].strip()
                    target_text = parts[3].strip()
                    # Extract everything after the 5th colon as the label
                    label_parts = parts[5:]
                    label = ":".join(label_parts).strip() if label_parts else "relates to: inferred relationship"
                    new_connections.append({"source_text": source_text, "target_text": target_text, "label": label})
                    logger.info(f"Parsed connection: {source_text} -> {target_text} with label: {label}")
        
        logger.info(f"Parsed new topics: {new_topics}")
        logger.info(f"Parsed new connections: {new_connections}")
        
        # Speichere die neuen Topics in der Datenbank mit korrekter parent_id
        new_topic_objects = []
        if len(new_topics) == len(subtopics):
            for i, (subtopic, new_topic_name) in enumerate(zip(subtopics, new_topics)):
                new_topic = Topic(upload_id=upload.id, name=new_topic_name, is_main_topic=False, parent_id=subtopic.id)
                db.session.add(new_topic)
                new_topic_objects.append(new_topic)
                logger.info(f"Saved new topic: {new_topic_name} with parent_id: {subtopic.id}")
            db.session.flush()  # Flush, um die IDs der neuen Topics zu erhalten
        
        # Create all topics mentioned in connections if they don't exist yet
        all_topics = Topic.query.filter_by(upload_id=upload.id).all()
        all_topic_names = [t.name for t in all_topics]
        
        # First, create new topics from the new_topics list
        for new_topic_name in new_topics:
            if new_topic_name not in all_topic_names:
                # Find a suitable parent (any subtopic)
                parent_id = subtopics[0].id if subtopics else main_topic.id
                new_topic = Topic(upload_id=upload.id, name=new_topic_name, is_main_topic=False, parent_id=parent_id)
                db.session.add(new_topic)
                logger.info(f"Created new topic: {new_topic_name} with parent_id: {parent_id}")
                all_topic_names.append(new_topic_name)
        
        # Then, create any source or target topics mentioned in connections that don't exist yet
        for conn in new_connections:
            source_text = conn["source_text"]
            target_text = conn["target_text"]
            
            # Create source topic if it doesn't exist
            if source_text not in all_topic_names:
                new_source = Topic(upload_id=upload.id, name=source_text, is_main_topic=False, parent_id=main_topic.id)
                db.session.add(new_source)
                logger.info(f"Created source topic: {source_text} with parent_id: {main_topic.id}")
                all_topic_names.append(source_text)
            
            # Create target topic if it doesn't exist
            if target_text not in all_topic_names:
                new_target = Topic(upload_id=upload.id, name=target_text, is_main_topic=False, parent_id=main_topic.id)
                db.session.add(new_target)
                logger.info(f"Created target topic: {target_text} with parent_id: {main_topic.id}")
                all_topic_names.append(target_text)
        
        # Flush to get IDs for the new topics
        db.session.flush()
        
        # Get all topics again after adding new ones
        all_topics = Topic.query.filter_by(upload_id=upload.id).all()
        
        # Speichere die Verbindungen in der Connection-Tabelle
        logger.info(f"Creating connections between topics. New connections data: {new_connections}")
        for conn in new_connections:
            logger.info(f"Processing connection: {conn}")
            source_topic = next((t for t in all_topics if t.name == conn["source_text"]), None)
            target_topic = next((t for t in all_topics if t.name == conn["target_text"]), None)
            
            logger.info(f"Source topic found: {source_topic.name if source_topic else 'None'}, ID: {source_topic.id if source_topic else 'None'}")
            logger.info(f"Target topic found: {target_topic.name if target_topic else 'None'}, ID: {target_topic.id if target_topic else 'None'}")
            
            if source_topic and target_topic:
                # Check if this connection already exists
                existing_conn = Connection.query.filter_by(
                    upload_id=upload.id,
                    source_id=source_topic.id,
                    target_id=target_topic.id
                ).first()
                
                if not existing_conn:
                    connection = Connection(
                        upload_id=upload.id,
                        source_id=source_topic.id,
                        target_id=target_topic.id,
                        label=conn["label"]
                    )
                    logger.info(f"Creating connection object: {connection.__dict__}")
                    db.session.add(connection)
                    logger.info(f"Saved connection: {source_topic.name} -> {target_topic.name} with label: {conn['label']}")
                else:
                    logger.info(f"Connection already exists: {source_topic.name} -> {target_topic.name}")
            else:
                logger.error(f"Could not create connection: source or target topic not found. Source: {conn['source_text']}, Target: {conn['target_text']}")
        
        # Begrenze auf 5 Einträge
        existing_activities = UserActivity.query.filter_by(user_id=request.user_id).order_by(UserActivity.timestamp.asc()).all()
        if len(existing_activities) >= 5:
            oldest_activity = existing_activities[0]
            db.session.delete(oldest_activity)
            logger.info(f"Deleted oldest activity: {oldest_activity.id}")
        
        # Speichere Benutzeraktivität
        activity = UserActivity(
            user_id=request.user_id,
            activity_type='concept',
            title=f"Generated topics for {main_topic.name}",
            main_topic=main_topic.name,
            subtopics=[s.name for s in subtopics],
            session_id=session_id,
            details={"new_topics": new_topics, "new_connections": new_connections}
        )
        db.session.add(activity)
        
        db.session.commit()
        logger.info(f"Committed {len(new_topics)} new topics and {len(new_connections)} connections to database")
        
        # Rückgabe der aktualisierten Daten
        return jsonify({
            "success": True,
            "data": {
                "new_topics": new_topics,
                "new_connections": new_connections,
                "updated_topics": [
                    {"id": t.id, "name": t.name, "parent_id": t.parent_id, "is_main_topic": t.is_main_topic}
                    for t in Topic.query.filter_by(upload_id=upload.id).all()
                ],
                "connections": [
                    {"id": c.id, "source_id": c.source_id, "target_id": c.target_id, "label": c.label}
                    for c in Connection.query.filter_by(upload_id=upload.id).all()
                ]
            }
        }), 200
    except Exception as e:
        logger.error(f"Error generating topics: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "error": {"code": "GENERATION_FAILED", "message": str(e)}}), 500

@api_bp.route('/topics/<session_id>', methods=['GET', 'OPTIONS'])
def get_topics(session_id):
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        return response
    
    # Authentifizierung für nicht-OPTIONS Anfragen
    auth_decorator = token_required(lambda: None)
    auth_result = auth_decorator()
    if auth_result is not None:
        return auth_result
    
    try:
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
        
        # Hauptthema finden
        main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
        if not main_topic:
            return jsonify({"success": False, "error": {"code": "NO_MAIN_TOPIC", "message": "No main topic found for this session"}}), 404
        
        # Direkte Subtopics finden (keine Kinder-Topics)
        subtopics = Topic.query.filter_by(upload_id=upload.id, parent_id=main_topic.id).all()
        
        # Format für die Antwort
        topics_data = {
            "main_topic": {
                "id": main_topic.id,
                "name": main_topic.name
            },
            "subtopics": [
                {
                    "id": topic.id,
                    "name": topic.name,
                    "parent_id": topic.parent_id
                } for topic in subtopics
            ]
            # Child-Topics werden absichtlich weggelassen, um sie erst bei Bedarf zu laden
        }
        
        # Verbindungen zwischen den Topics finden
        connections = []
        topic_ids = [main_topic.id] + [topic.id for topic in subtopics]
        
        # Hole alle Verbindungen für die aktuellen Topics
        db_connections = Connection.query.filter(
            Connection.upload_id == upload.id,
            Connection.source_id.in_(topic_ids),
            Connection.target_id.in_(topic_ids)
        ).all()
        
        # Stelle sicher, dass jede Verbindung ein aussagekräftiges Label hat
        language = detect_language(upload.content)
        default_label = "hängt zusammen mit" if language == 'de' else "related to"
        
        for conn in db_connections:
            # Finde die Quell- und Zielthemen
            source_topic = next((t for t in [main_topic] + subtopics if t.id == conn.source_id), None)
            target_topic = next((t for t in [main_topic] + subtopics if t.id == conn.target_id), None)
            
            if source_topic and target_topic:
                # Wenn das Label leer ist oder zu kurz, erstelle ein aussagekräftiges Label
                label = conn.label
                if not label or len(label.strip()) < 5:
                    if source_topic.is_main_topic:
                        label = f"{source_topic.name} umfasst {target_topic.name}"
                    elif target_topic.is_main_topic:
                        label = f"{source_topic.name} ist Teil von {target_topic.name}"
                    else:
                        label = f"{source_topic.name} {default_label} {target_topic.name}"
                
                connections.append({
                    "id": conn.id,
                    "source_id": conn.source_id,
                    "target_id": conn.target_id,
                    "label": label
                })
        
        return jsonify({
            "success": True,
            "topics": topics_data,
            "connections": connections
        }), 200
        
    except Exception as e:
        logger.error(f"Error retrieving topics: {str(e)}")
        return jsonify({"success": False, "error": {"code": "RETRIEVAL_FAILED", "message": str(e)}}), 500

@api_bp.route('/generate-concept-map-suggestions', methods=['POST', 'OPTIONS'])
def generate_concept_map_suggestions():
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        return response
        
    # Authentifizierung für nicht-OPTIONS Anfragen
    auth_decorator = token_required(lambda: None)
    auth_result = auth_decorator()
    if auth_result is not None:
        return auth_result
    
    data = request.json
    session_id = data.get('session_id')
    parent_subtopics = data.get('parent_subtopics', [])
    
    if not session_id:
        return jsonify({"success": False, "error": {"code": "NO_SESSION_ID", "message": "Session ID required"}}), 400
    
    if not parent_subtopics:
        return jsonify({"success": False, "error": {"code": "NO_PARENT_TOPICS", "message": "Parent subtopics required"}}), 400
    
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
    
    # Holen des Hauptthemas
    main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
    main_topic_name = "Unknown Topic"
    if main_topic:
        main_topic_name = main_topic.name
    
    # Ermittle die Sprache
    language = detect_language(upload.content)
    
    # Initialisiere den OpenAI-Client
    client = OpenAI(api_key=current_app.config['OPENAI_API_KEY'])
    
    try:
        # Generiere Vorschläge für Kinder-Unterthemen
        suggestions = generate_concept_map_suggestions(
            upload.content,
            client,
            main_topic=main_topic_name,
            parent_subtopics=parent_subtopics,
            language=language
        )
        
        logger.info(f"Generated concept map suggestions: {suggestions}")
        
    except Exception as e:
        logger.error(f"Error generating concept map suggestions: {str(e)}")
        # Fallback: Generiere einfache Vorschläge, wenn die API fehlschlägt
        suggestions = generate_fallback_suggestions(main_topic_name, parent_subtopics, language)
        logger.info(f"Generated fallback suggestions: {suggestions}")
    
    return jsonify({
        "success": True,
        "data": {
            "suggestions": suggestions
        },
        "message": "Concept map suggestions generated successfully"
    }), 200

def generate_fallback_suggestions(main_topic, parent_subtopics, language='en'):
    """
    Generiert einfache Fallback-Vorschläge für Concept-Map-Kinder-Unterthemen.
    Wird verwendet, wenn die OpenAI-API nicht verfügbar ist.
    Stellt sicher, dass für jedes Elternthema mindestens 3 einzigartige Kinder generiert werden.
    
    Args:
        main_topic: Das Hauptthema der Concept-Map
        parent_subtopics: Liste der übergeordneten Subtopics
        language: Die erkannte Sprache
        
    Returns:
        Ein Dictionary mit Elternthemen als Schlüssel und Listen von vorgeschlagenen Kindern als Werte
    """
    import random
    
    # Generische Kind-Themen zur Auswahl - kategorisiert für mehr thematische Konsistenz
    if language == 'de':
        generic_child_topics = {
            "Grundlagen": [
                "Definitionen", "Grundkonzepte", "Hauptprinzipien", "Kernelemente", 
                "Grundlegende Theorien", "Fundamentale Strukturen", "Basiswissen", "Grundlagen",
                "Konzeptueller Rahmen", "Theoretische Grundlagen", "Kernideen"
            ],
            "Anwendungen": [
                "Anwendungsgebiete", "Praktische Umsetzungen", "Einsatzbereiche", "Nutzungskontexte",
                "Reale Beispiele", "Industrielle Anwendungen", "Praxisrelevanz", "Implementierungen",
                "Anwendungsszenarien", "Fallstudien", "Praktische Beispiele"
            ],
            "Methoden": [
                "Methoden", "Techniken", "Verfahren", "Ansätze", "Strategien", "Prozesse",
                "Vorgehensweisen", "Arbeitsabläufe", "Mechanismen", "Arbeitsweisen", "Praktiken"
            ],
            "Historisches": [
                "Historische Entwicklung", "Entstehungsgeschichte", "Evolution", "Fortschritt",
                "Historischer Kontext", "Zeitliche Entwicklung", "Meilensteine", "Historische Perspektive",
                "Geschichtlicher Hintergrund", "Entwicklungsphasen", "Chronologie"
            ],
            "Bewertung": [
                "Vorteile", "Nutzen", "Stärken", "Positive Aspekte", "Mehrwert", "Potenziale",
                "Herausforderungen", "Schwächen", "Einschränkungen", "Probleme", "Grenzen",
                "Kritische Betrachtung", "Evaluationsmethoden", "Qualitätskriterien"
            ],
            "Zukunft": [
                "Zukunftsperspektiven", "Trends", "Entwicklungsrichtungen", "Innovationen",
                "Zukünftige Anwendungen", "Weiterentwicklungen", "Forschungsbedarf", "Visionen",
                "Zukünftige Herausforderungen", "Innovationspotenziale", "Perspektiven"
            ],
            "Beziehungen": [
                "Beziehungen", "Verbindungen", "Schnittstellen", "Integrationen", "Vernetzungen",
                "Interdependenzen", "Wechselwirkungen", "Zusammenhänge", "Korrelationen",
                "Kontextuelle Einbettung", "Systemische Beziehungen"
            ],
            "Beispiele": [
                "Beispiele", "Fallstudien", "Instanzen", "Anwendungsfälle", "Praxisbeispiele",
                "Referenzmodelle", "Typische Fälle", "Musterbeispiele", "Exemplarische Fälle",
                "Illustrationen", "Konkrete Beispiele"
            ],
            "Komponenten": [
                "Komponenten", "Bausteine", "Elemente", "Strukturen", "Bestandteile",
                "Teilaspekte", "Module", "Kernkomponenten", "Funktionale Einheiten",
                "Strukturelle Elemente", "Architektur", "Aufbau"
            ],
            "Spezifisches": [
                "Spezialgebiete", "Nischenanwendungen", "Spezifische Merkmale", "Besonderheiten",
                "Differenzierungsmerkmale", "Spezialisierungen", "Domänenspezifische Aspekte",
                "Fachspezifische Konzepte", "Besondere Eigenschaften"
            ]
        }
    else:  # English
        generic_child_topics = {
            "Fundamentals": [
                "Definitions", "Basic Concepts", "Main Principles", "Core Elements", 
                "Fundamental Theories", "Fundamental Structures", "Basic Knowledge", "Foundations",
                "Conceptual Framework", "Theoretical Foundations", "Core Ideas"
            ],
            "Applications": [
                "Application Areas", "Practical Implementations", "Usage Areas", "Usage Contexts",
                "Real Examples", "Industrial Applications", "Practical Relevance", "Implementations",
                "Application Scenarios", "Case Studies", "Practical Examples"
            ],
            "Methods": [
                "Methods", "Techniques", "Procedures", "Approaches", "Strategies", "Processes",
                "Work Procedures", "Workflows", "Mechanisms", "Working Methods", "Practices"
            ],
            "Historical": [
                "Historical Development", "Origin History", "Evolution", "Progress",
                "Historical Context", "Timeline", "Milestones", "Historical Perspective",
                "Historical Background", "Development Phases", "Chronology"
            ],
            "Evaluation": [
                "Advantages", "Benefits", "Strengths", "Positive Aspects", "Added Value", "Potentials",
                "Challenges", "Weaknesses", "Limitations", "Problems", "Boundaries",
                "Critical Review", "Evaluation Methods", "Quality Criteria"
            ],
            "Future": [
                "Future Perspectives", "Trends", "Development Directions", "Innovations",
                "Future Applications", "Further Developments", "Research Needs", "Visions",
                "Future Challenges", "Innovation Potentials", "Perspectives"
            ],
            "Relationships": [
                "Relationships", "Connections", "Interfaces", "Integrations", "Networks",
                "Interdependencies", "Interactions", "Correlations", "Interrelations",
                "Contextual Embedding", "Systemic Relationships"
            ],
            "Examples": [
                "Examples", "Case Studies", "Instances", "Use Cases", "Practical Examples",
                "Reference Models", "Typical Cases", "Model Examples", "Exemplary Cases",
                "Illustrations", "Concrete Examples"
            ],
            "Components": [
                "Components", "Building Blocks", "Elements", "Structures", "Constituents",
                "Subaspects", "Modules", "Core Components", "Functional Units",
                "Structural Elements", "Architecture", "Structure"
            ],
            "Specifics": [
                "Special Areas", "Niche Applications", "Specific Features", "Peculiarities",
                "Differentiating Features", "Specializations", "Domain-Specific Aspects",
                "Subject-Specific Concepts", "Special Properties"
            ]
        }
    
    # Erstelle das Ergebnis-Dictionary
    result = {}
    
    # Stelle sicher, dass die Kategorienliste zufällig gemischt ist, um Variation zu gewährleisten
    categories = list(generic_child_topics.keys())
    random.shuffle(categories)
    
    # Generiere für jeden übergeordneten Subtopic mindestens 3 Kinder
    for parent in parent_subtopics:
        # Extrahiere Schlüsselwörter aus dem Elternthema, um thematisch passendere Kinder zu generieren
        parent_keywords = parent.lower().split()
        
        # Wähle 3-5 Kategorien aus, die für dieses Elternthema relevant sein könnten
        # Aber gewährleiste immer mindestens 3 verschiedene Kategorien
        num_categories = random.randint(3, min(5, len(categories)))
        selected_categories = random.sample(categories, num_categories)
        
        # Wähle aus jeder Kategorie ein Kind-Thema und stelle sicher, dass es thematisch zum Elternthema passt
        children = []
        for category in selected_categories:
            category_topics = generic_child_topics[category]
            topic = random.choice(category_topics)
            
            # Vermeide Duplikate
            while topic in children and len(category_topics) > 1:
                topic = random.choice(category_topics)
                
            children.append(topic)
        
        # Stelle sicher, dass wir mindestens 3 Kinder haben
        while len(children) < 3:
            # Wähle eine zufällige Kategorie
            category = random.choice(categories)
            topic = random.choice(generic_child_topics[category])
            
            # Vermeide Duplikate
            if topic not in children:
                children.append(topic)
        
        # Speichere die Kinder im Ergebnis
        result[parent] = children
    
    return result

@api_bp.route('/generate/<session_id>', methods=['POST', 'OPTIONS'])
def generate_topics_for_session(session_id):
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        return response
        
    # Authentifizierung für nicht-OPTIONS Anfragen
    auth_decorator = token_required(lambda: None)
    auth_result = auth_decorator()
    if auth_result is not None:
        return auth_result
    
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
    
    # Prüfen, ob der Text zu lang ist
    content = upload.content or ""
    content_length = len(content)
    
    if content_length > 100000:
        return jsonify({
            "success": False,
            "error": {
                "code": "CONTENT_TOO_LARGE",
                "message": "Der Text ist zu lang. Bitte versuchen Sie es mit einem kürzeren Text."
            }
        }), 400
        
    # Schätze die Kosten basierend auf der Länge des Inhalts
    estimated_prompt_tokens = min(content_length // 3, 100000)  # Ungefähre Schätzung: 1 Token pro 3 Zeichen
    
    # Anpassung der Output-Token-Schätzung basierend auf der Eingabegröße
    if estimated_prompt_tokens < 100:
        estimated_output_tokens = 200  # Minimale Ausgabe für winzige Dokumente
    elif estimated_prompt_tokens < 500:
        estimated_output_tokens = 500  # Reduzierte Ausgabe für kleine Dokumente
    else:
        estimated_output_tokens = 4000  # Geschätzte Ausgabe für Topics und Verbindungen
    
    # Berechne die ungefähren Kosten
    content_tokens = count_tokens(upload.content)
    estimated_cost = calculate_token_cost(estimated_prompt_tokens, estimated_output_tokens, document_tokens=content_tokens)
    
    # Prüfe, ob der Benutzer genügend Credits hat
    if not check_credits_available(estimated_cost):
        # Hole die aktuellen Credits des Benutzers
        user = User.query.get(g.user.id)
        current_credits = user.credits if user else 0
        
        return jsonify({
            "success": False,
            "error": {
                "code": "INSUFFICIENT_CREDITS",
                "message": f"Nicht genügend Credits. Sie benötigen {estimated_cost} Credits für diese Anfrage, haben aber nur {current_credits} Credits.",
                "credits_required": estimated_cost,
                "credits_available": current_credits
            }
        }), 402
    
    try:
        # Einrichten des OpenAI Clients
        client = OpenAI(api_key=current_app.config['OPENAI_API_KEY'])
        
        # Analyse des Inhalts und Generierung der Topics
        prompt = f"""
        Analyze the following text and extract a hierarchical knowledge structure:
        
        1. MAIN TOPIC: Identify the primary topic of the text as a concise phrase (2-5 words)
        
        2. SUBTOPICS: Extract 5-8 key concepts or areas within the main topic. These should be the most important concepts covered in the text.
        
        Return the result as a JSON object:
        {{
          "main_topic": "The main topic name",
          "subtopics": ["Subtopic 1", "Subtopic 2", "Subtopic 3", ...]
        }}
        
        Text to analyze:
        {content[:50000]}  <!-- Limit content to prevent token limits -->
        """
        
        # Berechne die tatsächlichen Tokens vor dem API-Aufruf
        from .utils import count_tokens
        input_tokens = count_tokens(prompt)
        
        # OpenAI API Anfrage
        response = query_chatgpt(prompt, client)
        
        # Verarbeite die Antwort
        import re
        
        # Versuche, die JSON-Antwort zu extrahieren
        try:
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                topics_data = json.loads(match.group(0))
            else:
                # Falls kein JSON-Pattern gefunden wird
                raise ValueError("Konnte keine JSON-Struktur in der Antwort finden")
        except (json.JSONDecodeError, ValueError) as e:
            # Fallback für Nicht-JSON-Antworten
            # Extrahiere Teile mit Regex
            main_topic_match = re.search(r'"main_topic"\s*:\s*"([^"]+)"', response)
            subtopics_match = re.search(r'"subtopics"\s*:\s*\[(.*?)\]', response, re.DOTALL)
            
            main_topic = main_topic_match.group(1) if main_topic_match else "Unbekanntes Thema"
            
            subtopics = []
            if subtopics_match:
                subtopics_str = subtopics_match.group(1)
                # Extrahiere alle in Anführungszeichen stehenden Strings
                subtopics = re.findall(r'"([^"]+)"', subtopics_str)
            
            # Wenn keine Subtopics gefunden wurden, erstelle generische
            if not subtopics:
                subtopics = ["Thema 1", "Thema 2", "Thema 3", "Thema 4", "Thema 5"]
            
            topics_data = {
                "main_topic": main_topic,
                "subtopics": subtopics
            }
        
        # Speichere das Hauptthema in der Datenbank
        main_topic = Topic(
            upload_id=upload.id,
            name=topics_data["main_topic"],
            is_main_topic=True,
            parent_id=None
        )
        db.session.add(main_topic)
        db.session.flush()  # Flush, um die ID des Hauptthemas zu erhalten
        
        # Speichere die Subtopics mit dem Hauptthema als parent_id
        for subtopic_name in topics_data["subtopics"]:
            subtopic = Topic(
                upload_id=upload.id,
                name=subtopic_name,
                is_main_topic=False,
                parent_id=main_topic.id
            )
            db.session.add(subtopic)
        
        # Markiere den Upload als verarbeitet
        upload.processed = True
        upload.last_used_at = db.func.current_timestamp()
        
        # Speichere Benutzeraktivität
        activity = UserActivity(
            user_id=getattr(request, 'user_id', None),
            activity_type='generate',
            title=f"Generated topics for: {topics_data['main_topic']}",
            main_topic=topics_data["main_topic"],
            subtopics=topics_data["subtopics"],
            session_id=session_id,
            details={"main_topic": topics_data["main_topic"], "subtopics": topics_data["subtopics"]}
        )
        db.session.add(activity)
        
        # Commit der Änderungen in der Datenbank
        db.session.commit()
        
        # Nach erfolgreicher Verarbeitung die Credits abziehen
        # Die Berechnung der Kosten erfolgt bereits in query_chatgpt, 
        # das deduct_credits wird dort bereits aufgerufen
        
        # Hole die aktuellen Credits des Benutzers
        user = User.query.get(g.user.id)
        
        return jsonify({
            "success": True,
            "message": "Topics successfully generated",
            "data": {
                "main_topic": topics_data["main_topic"],
                "subtopics": topics_data["subtopics"]
            },
            "credits_available": user.credits if user else 0  # Füge aktuelle Credits in der Antwort hinzu
        }), 200
    except Exception as e:
        logger.error(f"Error generating topics: {str(e)}")
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": {
                "code": "GENERATION_FAILED",
                "message": f"Fehler bei der Generierung: {str(e)}"
            }
        }), 500
