"""
Concept Map Generierung
--------------------

Dieses Modul enthält Funktionen zur Generierung von Concept Maps
und Vorschlägen für Verbindungen zwischen Topics.
"""

import logging
import json
from flask import current_app
from ..utils import query_chatgpt, detect_language, generate_concept_map_suggestions
from core.models import db, Upload, Topic, Connection, User
from openai import OpenAI
from api.token_tracking import check_credits_available, calculate_token_cost, deduct_credits
from .utils import get_openai_client, process_topic_response
from .models import find_topic_by_name, create_connection

logger = logging.getLogger(__name__)

def generate_concept_map_suggestions(upload_id, main_topic, max_suggestions=5, language='en'):
    """
    Generiert Vorschläge für Verbindungen in einer Concept Map.
    
    Args:
        upload_id: Die ID des Uploads
        main_topic: Das Hauptthema
        max_suggestions: Maximale Anzahl an Vorschlägen
        language: Die Sprache der Vorschläge
        
    Returns:
        list: Liste der vorgeschlagenen Verbindungen
    """
    try:
        # Hole alle existierenden Topics für diesen Upload
        topics = Topic.query.filter_by(upload_id=upload_id).all()
        
        # Wenn weniger als zwei Topics existieren, können keine Verbindungen vorgeschlagen werden
        if len(topics) < 2:
            return []
        
        # Hole alle existierenden Verbindungen
        existing_connections = Connection.query.filter_by(upload_id=upload_id).all()
        existing_pairs = set([(conn.source_id, conn.target_id) for conn in existing_connections])
        
        # Für Debugging-Zwecke
        logger.debug(f"Existing connections: {existing_pairs}")
        
        client = get_openai_client()
        
        # Baue die Prompt für die Generierung der Vorschläge
        topic_names = [t.name for t in topics]
        topic_names_str = ", ".join(topic_names)
        
        prompt = _build_concept_map_prompt(main_topic.name, topic_names_str, language)
        
        # Generiere Vorschläge mit OpenAI
        response = query_chatgpt(prompt, client)
        logger.info(f"OpenAI response for concept map suggestions:\n{response}")
        
        # Verarbeite die Antwort und extrahiere die Vorschläge
        suggested_connections = _parse_suggestion_response(response)
        
        # Filtere bereits existierende Verbindungen heraus
        unique_suggestions = []
        for suggestion in suggested_connections:
            source_name = suggestion["source"]
            target_name = suggestion["target"]
            
            # Finde die entsprechenden Topic-Objekte
            source = find_topic_by_name(upload_id, source_name)
            target = find_topic_by_name(upload_id, target_name)
            
            if not source or not target:
                continue
                
            # Überprüfe, ob diese Verbindung bereits existiert
            if (source.id, target.id) not in existing_pairs and (target.id, source.id) not in existing_pairs:
                suggestion["source_id"] = source.id
                suggestion["target_id"] = target.id
                unique_suggestions.append(suggestion)
                
                # Begrenze die Anzahl der Vorschläge
                if len(unique_suggestions) >= max_suggestions:
                    break
        
        return unique_suggestions
    except Exception as e:
        logger.error(f"Error generating concept map suggestions: {str(e)}")
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
    else:
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
        logger.error(f"Error parsing suggestion response: {str(e)}")
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