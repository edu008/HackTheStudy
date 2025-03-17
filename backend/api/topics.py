from flask import request, jsonify, current_app
from . import api_bp
from .utils import query_chatgpt, detect_language
from models import db, Upload, Topic, UserActivity
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
    
    # Initialize OpenAI client directly
    from openai import OpenAI
    client = OpenAI(api_key=current_app.config['OPENAI_API_KEY'])
    prompt = (
        f"""
        Based on the following topics, suggest exactly one new related topic for each subtopic (except the main topic) and create connections between these topics. Analyze the content relationships and describe the connections precisely. The main topic should also be linked to at least one of the new topics.

        Main Topic: {main_topic.name}
        Subtopics: {', '.join([s.name for s in subtopics])}

        Format:
        New Topics: [Topic1, Topic2, Topic3, ...]
        New Connections:
        - source_text:Topic1:target_text:Topic2:label:Description of the relationship
        - source_text:Topic3:target_text:Topic4:label:Description of the relationship

        Rules:
        - Generate exactly 1 new related topic for each subtopic (except the main topic).
        - DO NOT use generic names like "Related Topic X".
        - DO NOT use numbering or bullet points for the new topics.
        - Each new topic must have a specific, descriptive name that clearly reflects the content.
        - Create connections between each subtopic and its new topic.
        - Create at least one connection between the main topic and one of the new topics.
        - Describe each relationship clearly and specifically.
        - Ensure the answer strictly follows the specified format and each connection starts with a '-'.
        - All topics must be technically correct and relevant to the main topic.
        """ if language != 'de' else
        f"""
        Basierend auf den folgenden Themen, schlage für jedes Subthema (außer dem Hauptthema) genau ein neues verwandtes Thema vor und erstelle Verbindungen zwischen diesen Themen. Analysiere die inhaltlichen Zusammenhänge und beschreibe die Beziehungen präzise. Das Hauptthema sollte ebenfalls mit mindestens einem der neuen Themen verknüpft werden.

        Hauptthema: {main_topic.name}
        Subthemen: {', '.join([s.name for s in subtopics])}

        Format:
        Neue Themen: [Thema1, Thema2, Thema3, ...]
        Neue Verbindungen:
        - source_text:Thema1:target_text:Thema2:label:Beschreibung der Beziehung
        - source_text:Thema3:target_text:Thema4:label:Beschreibung der Beziehung

        Regeln:
        - Generiere für jedes Subthema (außer dem Hauptthema) genau 1 neues verwandtes Thema.
        - Verwende KEINE generischen Namen wie "Verwandtes Thema X".
        - Verwende KEINE Nummerierung oder Aufzählungszeichen bei den neuen Themen.
        - Jedes neue Thema muss einen spezifischen, beschreibenden Namen haben, der den Inhalt klar widerspiegelt.
        - Erstelle Verbindungen zwischen jedem Subthema und seinem neuen Thema.
        - Erstelle mindestens eine Verbindung zwischen dem Hauptthema und einem der neuen Themen.
        - Beschreibe jede Beziehung klar und spezifisch.
        - Stelle sicher, dass die Antwort strikt dem angegebenen Format entspricht und jede Verbindung mit einem '-' beginnt.
        - Alle Themen müssen fachlich korrekt und relevant für das Hauptthema sein.
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
        
        for line in lines:
            line = line.strip()
            if line.startswith("Neue Themen:") or line.startswith("New Topics:"):
                in_topics = True
                in_connections = False
                topics_str = line[line.find(":") + 1:].strip()[1:-1]
                new_topics = [t.strip() for t in topics_str.split(",") if t.strip()] if topics_str else []
            elif line.startswith("Neue Verbindungen:") or line.startswith("New Connections:"):
                in_topics = False
                in_connections = True
            elif in_connections and line.startswith('-'):
                parts = line[1:].strip().split(':')
                if len(parts) >= 5:
                    source_text = parts[1].strip()
                    target_text = parts[3].strip()
                    label = parts[5].strip() if len(parts) > 5 else parts[4].strip()
                    new_connections.append({"source_text": source_text, "target_text": target_text, "label": label})
        
        if hasattr(request, 'user_id'):
            for i, topic_name in enumerate(new_topics[:len(subtopics)]):
                db.session.add(Topic(upload_id=upload.id, name=topic_name, is_main_topic=False, parent_id=subtopics[i].id))
            activity = UserActivity(user_id=request.user_id, activity_type='concept', title=f"Generated topics for {main_topic.name}", details={"new_topics": new_topics})
            db.session.add(activity)
        
        db.session.commit()
        return jsonify({"success": True, "data": {"new_topics": new_topics, "new_connections": new_connections}}), 200
    except Exception as e:
        logger.error(f"Error generating topics: {str(e)}")
        return jsonify({"success": False, "error": {"code": "GENERATION_FAILED", "message": str(e)}}), 500

@api_bp.route('/topics/<session_id>', methods=['GET'])
def get_topics(session_id):
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
    
    main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
    subtopics = Topic.query.filter_by(upload_id=upload.id, parent_id=main_topic.id).all() if main_topic else []
    child_topics = []
    for subtopic in subtopics:
        children = Topic.query.filter_by(upload_id=upload.id, parent_id=subtopic.id).all()
        child_topics.extend([{"id": c.id, "name": c.name, "parent_id": c.parent_id, "parent_name": subtopic.name} for c in children])
    
    return jsonify({
        "success": True,
        "topics": {
            "main_topic": {"id": main_topic.id, "name": main_topic.name},
            "subtopics": [{"id": s.id, "name": s.name, "parent_id": s.parent_id} for s in subtopics],
            "child_topics": child_topics
        }
    }), 200
