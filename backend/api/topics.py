from flask import request, jsonify, current_app
from . import api_bp
from .utils import query_chatgpt, detect_language
from models import db, Upload, Topic, UserActivity, Connection
import logging

logger = logging.getLogger(__name__)

@api_bp.route('/generate-related-topics', methods=['POST'])
def generate_related_topics():
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
    
    from openai import OpenAI
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
        Basierend auf den folgenden Themen, schlage für jedes Subthema (außer dem Hauptthema) genau ein neues verwandtes Thema vor und erstelle Verbindungen zwischen diesen Themen. Analysiere die inhaltlichen Zusammenhänge und gib für jede Verbindung eine präzise, detaillierte Beschreibung als Label an. Das Hauptthema sollte ebenfalls mit mindestens einem der neuen Themen verknüpft werden.

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
        - Generiere für jedes Subthema (außer dem Hauptthema) genau 1 neues verwandtes Thema.
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
        
        if hasattr(request, 'user_id'):
            activity = UserActivity(
                user_id=request.user_id,
                activity_type='concept',
                title=f"Generated topics for {main_topic.name}",
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

@api_bp.route('/topics/<session_id>', methods=['GET'])
def get_topics(session_id):
    try:
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
        
        main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
        if not main_topic:
            return jsonify({"success": False, "error": {"code": "MAIN_TOPIC_NOT_FOUND", "message": "Main topic not found"}}), 404
        
        subtopics = Topic.query.filter_by(upload_id=upload.id, parent_id=main_topic.id).all()
        child_topics = Topic.query.filter(Topic.upload_id == upload.id, Topic.parent_id.in_([t.id for t in subtopics])).all()
        connections = Connection.query.filter_by(upload_id=upload.id).all()

        return jsonify({
            "success": True,
            "topics": {
                "main_topic": {
                    "id": main_topic.id,
                    "name": main_topic.name,
                    "is_main_topic": main_topic.is_main_topic,
                    "parent_id": main_topic.parent_id
                },
                "subtopics": [
                    {"id": t.id, "name": t.name, "parent_id": t.parent_id, "is_main_topic": t.is_main_topic}
                    for t in subtopics
                ],
                "child_topics": [
                    {"id": t.id, "name": t.name, "parent_id": t.parent_id, "is_main_topic": t.is_main_topic}
                    for t in child_topics
                ]
            },
            "connections": [
                {"id": c.id, "source_id": c.source_id, "target_id": c.target_id, "label": c.label}
                for c in connections
            ]
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving topics: {str(e)}")
        return jsonify({"success": False, "error": {"code": "RETRIEVAL_FAILED", "message": str(e)}}), 500
