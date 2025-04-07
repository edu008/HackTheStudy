"""
Concept Map Generierung
--------------------

Dieses Modul enthält Funktionen zur Generierung von Concept Maps
und Vorschlägen für Verbindungen zwischen Topics.
"""

import json
import logging

from api.token_tracking import (calculate_token_cost, check_credits_available,
                                deduct_credits)
from core.models import Topic, Upload, User, db
from flask import current_app
from openai import OpenAI

from ..utils import (detect_language, query_chatgpt)
from .models import create_connection_via_parent, find_topic_by_name
from .utils import get_openai_client, process_topic_response

logger = logging.getLogger(__name__)


def generate_concept_map_suggestions(upload_id, main_topic, max_suggestions=5, language='en'):
    """
    Generiert Vorschläge für Verbindungen in einer Concept Map.

    Args:
        upload_id: Die ID des Uploads
        main_topic: Das Hauptthema
        max_suggestions: Maximale Anzahl von Vorschlägen
        language: Die Sprache der Vorschläge

    Returns:
        list: Liste der Verbindungsvorschläge
    """
    try:
        # Hole alle Themen für diesen Upload
        topics = Topic.query.filter_by(upload_id=upload_id).all()
        
        # Wenn keine Themen gefunden wurden, gib eine leere Liste zurück
        if not topics:
            logger.warning("Keine Themen gefunden für Upload %s", upload_id)
            return []
        
        # Extrahiere die Topic-Namen als Set (effizienter für die "in" Operation)
        topic_names = {topic.name for topic in topics}
        
        # Erstelle eine kommagetrennte Liste aller Themen
        topic_names_str = ", ".join(topic_names)
        
        # Erstelle den Prompt
        prompt = _build_concept_map_prompt(main_topic.name, topic_names_str, language)
        
        # Erstelle OpenAI-Client
        client = get_openai_client()
        
        # Sende Anfrage an OpenAI
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an assistant that helps create concept maps."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        # Extrahiere die Antwort
        answer = response.choices[0].message.content.strip()
        
        # Parse die Antwort und extrahiere die Vorschläge
        suggestions = _parse_suggestion_response(answer)
        
        # Begrenze die Anzahl der Vorschläge
        return suggestions[:max_suggestions]
    
    except Exception as e:
        logger.error("Fehler bei der Generierung von Concept-Map-Vorschlägen: %s", str(e))
        return []


def _build_concept_map_prompt(main_topic, topic_names, language='en'):
    """
    Baut den Prompt für die Generierung von Concept Map Vorschlägen.

    Args:
        main_topic: Das Hauptthema
        topic_names: Komma-getrennte Liste aller Themen
        language: Die Sprache des Prompts

    Returns:
        str: Der generierte Prompt
    """
    if language != 'de':
        return f"""
        Based on the following list of topics, suggest 10 meaningful connections for a concept map.
        The main topic is "{main_topic}" and the other topics are related to it.

        Topics: {topic_names}

        For each connection, provide:
        1. Source topic (exactly as listed above)
        2. Target topic (exactly as listed above)
        3. Label (a clear and concise description of the relationship)

        Format your response as a list of connections in the following JSON-like format:
        [{{"source": "Topic A", "target": "Topic B", "label": "describes"}},
         {{"source": "Topic C", "target": "Topic D", "label": "influences"}},
         ...and so on]

        IMPORTANT RULES:
        - Suggest diverse connections between different topics
        - Use precise relationship labels (e.g., "includes", "causes", "influences")
        - Make sure that ALL topics and labels are grammatically correct and make sense
        - Each source and target must exactly match one of the provided topic names
        - Return exactly 10 connection suggestions
        - The connections should form a coherent concept map
        """
    
    return f"""
    Basierend auf der folgenden Liste von Themen, schlage 10 sinnvolle Verbindungen für eine Concept Map vor.
    Das Hauptthema ist "{main_topic}" und die anderen Themen sind damit verwandt.

    Themen: {topic_names}

    Für jede Verbindung gib an:
    1. Quellthema (genau wie oben aufgeführt)
    2. Zielthema (genau wie oben aufgeführt)
    3. Beschriftung (eine klare und präzise Beschreibung der Beziehung)

    Formatiere deine Antwort als Liste von Verbindungen im folgenden JSON-ähnlichen Format:
    [{{"source": "Thema A", "target": "Thema B", "label": "beschreibt"}},
     {{"source": "Thema C", "target": "Thema D", "label": "beeinflusst"}},
     ...und so weiter]

    WICHTIGE REGELN:
    - Schlage vielfältige Verbindungen zwischen verschiedenen Themen vor
    - Verwende präzise Beziehungsbeschriftungen (z.B. "beinhaltet", "verursacht", "beeinflusst")
    - Stelle sicher, dass ALLE Themen und Beschriftungen grammatikalisch korrekt sind und Sinn ergeben
    - Jede Quelle und jedes Ziel muss genau einem der angegebenen Themennamen entsprechen
    - Gib genau 10 Verbindungsvorschläge zurück
    - Die Verbindungen sollten eine kohärente Concept Map bilden
    """


def _parse_suggestion_response(response):
    """
    Parst die Antwort der OpenAI-API und extrahiert die vorgeschlagenen Verbindungen.

    Args:
        response: Die Antwort der OpenAI-API

    Returns:
        list: Liste der vorgeschlagenen Verbindungen
    """
    try:
        # Suche nach JSON-Array in der Antwort
        start_idx = response.find('[')
        end_idx = response.rfind(']')

        if start_idx == -1 or end_idx == -1:
            logger.warning("Could not find JSON array in response")
            # Versuche, einzelne Vorschläge zu extrahieren
            return _extract_suggestions_from_text(response)

        # Extrahiere und parse das JSON-Array
        json_str = response[start_idx:end_idx+1]
        suggestions = json.loads(json_str)

        # Validiere und normalisiere die Vorschläge
        valid_suggestions = []
        for suggestion in suggestions:
            if "source" in suggestion and "target" in suggestion and "label" in suggestion:
                valid_suggestions.append({
                    "source": suggestion["source"].strip(),
                    "target": suggestion["target"].strip(),
                    "label": suggestion["label"].strip()
                })

        return valid_suggestions
    except Exception as e:
        logger.error("Error parsing suggestion response: %s", str(e))
        # Fallback zu textbasierter Extraktion
        return _extract_suggestions_from_text(response)


def _extract_suggestions_from_text(text):
    """
    Extrahiert Verbindungsvorschläge aus Freitext, wenn JSON-Parsing fehlschlägt.

    Args:
        text: Der Text, aus dem Vorschläge extrahiert werden sollen

    Returns:
        list: Liste der extrahierten Vorschläge
    """
    suggestions = []
    lines = text.split('\n')

    for line in lines:
        line = line.strip()
        # Suche nach Zeilen, die wie Vorschläge aussehen
        if ":" in line and "->" in line:
            parts = line.split("->")
            if len(parts) == 2:
                source = parts[0].strip()
                target_and_label = parts[1].strip()

                # Extrahiere Target und Label
                if ":" in target_and_label:
                    target_parts = target_and_label.split(":")
                    target = target_parts[0].strip()
                    label = ":".join(target_parts[1:]).strip()

                    suggestions.append({
                        "source": source,
                        "target": target,
                        "label": label
                    })

    return suggestions
