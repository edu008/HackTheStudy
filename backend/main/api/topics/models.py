"""
Datenbankoperationen für Topics
----------------------------

Dieses Modul enthält Funktionen für die Datenbankinteraktion mit Topics und Connections.
"""

import logging
from datetime import datetime

from core.models import Connection, Topic, Upload, UserActivity, db

logger = logging.getLogger(__name__)


def get_topic_hierarchy(upload_id):
    """
    Holt die vollständige Topic-Hierarchie für einen Upload.

    Args:
        upload_id: Die ID des Uploads

    Returns:
        dict: Eine strukturierte Hierarchie der Topics und ihrer Verbindungen
    """
    topics = Topic.query.filter_by(upload_id=upload_id).all()
    connections = Connection.query.filter_by(upload_id=upload_id).all()

    # Erstelle ein Dictionary mit allen Topics
    topics_dict = {topic.id: {
        "id": topic.id,
        "name": topic.name,
        "is_main_topic": topic.is_main_topic,
        "parent_id": topic.parent_id,
        "children": []
    } for topic in topics}

    # Füge Kinder zu ihren Eltern hinzu
    for topic_data in topics_dict.values():
        if topic_data["parent_id"] and topic_data["parent_id"] in topics_dict:
            topics_dict[topic_data["parent_id"]]["children"].append(topic_data)

    # Erstelle die Hierarchie, ausgehend vom Hauptthema
    main_topic = next((t for t in topics if t.is_main_topic), None)

    # Erstelle das Ergebnis mit Topics und Connections
    result = {
        "topics": [topics_dict[topic.id] for topic in topics],
        "connections": [{
            "id": conn.id,
            "source_id": conn.source_id,
            "target_id": conn.target_id,
            "label": conn.label,
            "source_text": next((t.name for t in topics if t.id == conn.source_id), ""),
            "target_text": next((t.name for t in topics if t.id == conn.target_id), "")
        } for conn in connections]
    }

    # Füge die Haupthierarchie hinzu, wenn ein Hauptthema existiert
    if main_topic:
        result["hierarchy"] = topics_dict[main_topic.id]

    return result


def create_topic(upload_id, name, is_main_topic=False, parent_id=None):
    """
    Erstellt ein neues Topic in der Datenbank.

    Args:
        upload_id: Die ID des Uploads
        name: Der Name des Topics
        is_main_topic: Ob es sich um das Hauptthema handelt
        parent_id: Die ID des übergeordneten Topics (optional)

    Returns:
        Topic: Das erstellte Topic-Objekt
    """
    topic = Topic(
        upload_id=upload_id,
        name=name,
        is_main_topic=is_main_topic,
        parent_id=parent_id
    )
    db.session.add(topic)
    db.session.flush()  # Flush, um die ID des neuen Topics zu erhalten
    logger.info("Created new topic: %s with ID: %s", name, topic.id)
    return topic


def create_connection(upload_id, source_id, target_id, label):
    """
    Erstellt eine neue Verbindung zwischen zwei Topics.

    Args:
        upload_id: Die ID des Uploads
        source_id: Die ID des Quell-Topics
        target_id: Die ID des Ziel-Topics
        label: Die Beschreibung der Verbindung

    Returns:
        Connection: Das erstellte Connection-Objekt
    """
    # Überprüfe, ob bereits eine Verbindung zwischen diesen Topics existiert
    existing = Connection.query.filter_by(
        upload_id=upload_id,
        source_id=source_id,
        target_id=target_id
    ).first()

    if existing:
        logger.info("Connection between %s and %s already exists, updating label", source_id, target_id)
        existing.label = label
        return existing

    connection = Connection(
        upload_id=upload_id,
        source_id=source_id,
        target_id=target_id,
        label=label
    )
    db.session.add(connection)
    logger.info("Created new connection: %s -> %s with label: %s", source_id, target_id, label)
    return connection


def find_topic_by_name(upload_id, name):
    """
    Findet ein Topic anhand seines Namens.

    Args:
        upload_id: Die ID des Uploads
        name: Der Name des Topics

    Returns:
        Topic: Das gefundene Topic-Objekt oder None, wenn nicht gefunden
    """
    return Topic.query.filter_by(upload_id=upload_id, name=name).first()


def create_topics_from_list(upload_id, topics_list, parent_id=None):
    """
    Erstellt mehrere Topics aus einer Liste von Namen.

    Args:
        upload_id: Die ID des Uploads
        topics_list: Liste der Topic-Namen
        parent_id: Die ID des übergeordneten Topics (optional)

    Returns:
        list: Die erstellten Topic-Objekte
    """
    created_topics = []
    for topic_name in topics_list:
        # Überprüfe, ob das Topic bereits existiert
        existing = find_topic_by_name(upload_id, topic_name)
        if existing:
            created_topics.append(existing)
            continue

        # Erstelle neues Topic
        topic = create_topic(upload_id, topic_name, False, parent_id)
        created_topics.append(topic)

    return created_topics


def create_connections_from_list(upload_id, connections_list):
    """
    Erstellt mehrere Verbindungen aus einer Liste von Verbindungsinformationen.

    Args:
        upload_id: Die ID des Uploads
        connections_list: Liste der Verbindungsinformationen (dict mit source_text, target_text, label)

    Returns:
        list: Die erstellten Connection-Objekte
    """
    created_connections = []
    for conn_info in connections_list:
        source_text = conn_info.get("source_text")
        target_text = conn_info.get("target_text")
        label = conn_info.get("label")

        # Finde die entsprechenden Topics
        source = find_topic_by_name(upload_id, source_text)
        target = find_topic_by_name(upload_id, target_text)

        if not source or not target:
            logger.warning("Could not create connection: source or target not found - %s -> %s", 
                          source_text, target_text)
            continue

        # Erstelle Verbindung
        connection = create_connection(upload_id, source.id, target.id, label)
        created_connections.append(connection)

    return created_connections


def log_topic_activity(user_id, upload_id, activity_type, details=None):
    """
    Protokolliert eine Benutzeraktivität im Zusammenhang mit Topics.

    Args:
        user_id: Die ID des Benutzers
        upload_id: Die ID des Uploads
        activity_type: Der Typ der Aktivität
        details: Zusätzliche Details zur Aktivität (optional)

    Returns:
        UserActivity: Das erstellte UserActivity-Objekt
    """
    activity = UserActivity(
        user_id=user_id,
        upload_id=upload_id,
        activity_type=activity_type,
        timestamp=datetime.utcnow(),
        details=details
    )
    db.session.add(activity)
    return activity
