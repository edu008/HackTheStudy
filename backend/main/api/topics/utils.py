"""
Hilfsfunktionen für das Topics-Modul
---------------------------------

Dieses Modul enthält Hilfsfunktionen für die Verarbeitung von Topics-Daten
und die Interaktion mit der OpenAI-API.
"""

import json
import logging

from api.token_tracking import (calculate_token_cost, check_credits_available,
                                deduct_credits)
from core.models import Topic, Upload
from flask import current_app
from openai import OpenAI

from ..utils import (check_and_manage_user_sessions, detect_language,
                     query_chatgpt)

logger = logging.getLogger(__name__)


def process_topic_response(response, language='en'):
    """
    Verarbeitet die Antwort der OpenAI-API und extrahiert Topics und Connections.

    Args:
        response: Die Antwort der OpenAI-API
        language: Die Sprache der Topics (Standard: Englisch)

    Returns:
        tuple: (list[str], list[dict]) - Liste der Topics und Liste der Connections
    """
    logger.info("Processing OpenAI response for topics:\n%s", response)
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
            while (next_line_index < len(lines) and 
                  not lines[next_line_index].strip().startswith('-') and 
                  lines[next_line_index].strip()):
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
                logger.info("Parsed connection: %s -> %s with label: %s", source_text, target_text, label)

    logger.info("Parsed new topics: %s", new_topics)
    logger.info("Parsed new connections: %s", new_connections)

    return new_topics, new_connections


def get_openai_client():
    """
    Erstellt einen OpenAI-Client mit dem API-Key aus der Konfiguration.

    Returns:
        OpenAI: Eine Instanz des OpenAI-Clients
    """
    return OpenAI(
        api_key=current_app.config['OPENAI_API_KEY'],
        default_headers={
            "OpenAI-Beta": "assistants=v2"
        }
    )


def build_topic_prompt(main_topic, subtopics, language='en'):
    """
    Baut den Prompt für die Generierung von verwandten Topics.

    Args:
        main_topic: Das Hauptthema
        subtopics: Die Subthemen
        language: Die Sprache des Prompts (Standard: Englisch)

    Returns:
        str: Der generierte Prompt
    """
    if language != 'de':
        return f"""
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
        """
    
    return f"""
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


def find_upload_by_session(session_id):
    """
    Findet einen Upload anhand der Session-ID.

    Args:
        session_id: Die Session-ID

    Returns:
        Upload: Das Upload-Objekt oder None, wenn nicht gefunden
    """
    return Upload.query.filter_by(session_id=session_id).first()
