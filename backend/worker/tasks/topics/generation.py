"""
Extraktion von Themen aus Dokumenten mit OpenAI.
"""
import json
import logging
import os
from typing import Dict, List, Any, Optional
import hashlib # Import hashlib

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Absolute Imports verwenden statt relativer Imports
from utils.call_openai import call_openai_api, extract_json_from_response
from config.prompts import get_system_prompt, get_user_prompt
from redis_utils.client import get_redis_client

def extract_topics_with_openai(
    extracted_text: str,
    max_topics: int = 8, 
    language: str = 'de', 
    **options
) -> Dict[str, Any]:
    """
    Extrahiert Hauptthemen mit OpenAI (SYNCHRONE VERSION).
    Erhält den Text als Argument.
    Args:
        extracted_text (str): Der Text.
        max_topics (int): Maximale Anzahl Themen.
        language (str): Sprachcode.
        **options: Weitere Optionen (model).
    Returns:
        dict: Enthält {"topics_data": Dict, "usage": Dict} oder leeres Dict bei Fehler.
    """
    model = options.get('model', os.environ.get('OPENAI_DEFAULT_MODEL', 'gpt-3.5-turbo'))
    logger.info("="*50)
    logger.info(f"THEMEN-EXTRAKTION (SYNC) GESTARTET")
    logger.info(f"Konfiguration: Bis zu {max_topics} Themen, Sprache: {language}, Modell: {model}")
    logger.info("="*50)

    content = extracted_text
    if not content:
        logger.error("[TOPICS] Kein Text zur Verarbeitung übergeben.")
        return {"topics_data": {'main_topic': {}, 'subtopics': []}, "usage": None}

    # Cache-Prüfung (bleibt ähnlich)
    response_content = None
    usage = None
    cache_key = None
    CACHE_TTL = 86400 * 7 # 7 Tage
    try:
        content_hash_part = content[:20000] 
        params_str = f"max:{max_topics}-lang:{language}-model:{model}"
        combined_key_material = f"{content_hash_part}-{params_str}"
        # Cache-Key spezifisch für Themen
        cache_key = f"openai_cache:topics:{hashlib.sha256(combined_key_material.encode('utf-8')).hexdigest()}"
        
        cached_response = get_redis_client().get(cache_key)
        if cached_response:
            response_content = cached_response.decode('utf-8')
            logger.info(f"[CACHE HIT] Antwort aus Redis-Cache geladen für Key: {cache_key}")
        else:
            logger.info(f"[CACHE MISS] Kein Cache-Eintrag gefunden für Key: {cache_key}")

    except Exception as cache_err:
        logger.warning(f"[THEMEN] Fehler bei Cache-Prüfung: {cache_err}")

    # Nur wenn kein Cache-Hit, die API aufrufen
    if response_content is None:
        # Prompts vorbereiten
        system_prompt = get_system_prompt("topics", language=language, max_topics=max_topics)
        user_prompt = get_user_prompt("topics", content)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # OpenAI-API aufrufen (SYNCHRON)
        logger.info(f"[TOPICS] Schritt 4: Sende SYNC Anfrage an OpenAI API ({model})")
        response = call_openai_api(
            model=model,
            messages=messages,
            temperature=0.5,  # Niedrigere Temperatur für konsistentere Ergebnisse
            max_tokens=1500,
            response_format={"type": "json_object"}
        )
        response_content = response.get('choices', [{}])[0].get('message', {}).get('content', '{}')
        usage = response.get('usage')
        logger.info(f"[TOPICS] OpenAI-Antwort erhalten. Usage: {usage}")

        # Cache speichern (bleibt gleich)
        if response_content and response_content != '{}' and cache_key:
            try:
                get_redis_client().set(cache_key, response_content, ex=CACHE_TTL)
                logger.info(f"[CACHE SET] Antwort in Redis gespeichert (Key: {cache_key}, TTL: {CACHE_TTL // 86400} Tage)")
            except Exception as cache_set_err:
                logger.warning(f"[THEMEN] Fehler beim Speichern der Antwort im Cache: {cache_set_err}")

    # Antwort parsen & Themen extrahieren/normalisieren (bleibt gleich)
    topics_result = {'main_topic': {}, 'subtopics': []}
    try:
        topics_data = extract_json_from_response(response_content)
        logger.info(f"[THEMEN] JSON erfolgreich geparst: {len(str(topics_data))} Zeichen")
        logger.info(f"[THEMEN] JSON-Struktur: {type(topics_data)} - Vorschau: {str(topics_data)[:300]}...")

        # SCHRITT 7: Struktur normalisieren
        logger.info(f"[THEMEN] Schritt 7: Normalisiere Themen-Struktur")

        # Verschiedene Formate erkennen und verarbeiten
        
        # Format 1: Standard-Format mit main_topic und subtopics
        if isinstance(topics_data, dict) and 'main_topic' in topics_data and 'subtopics' in topics_data:
            logger.info(f"[THEMEN] Format 1: Standardformat mit main_topic und subtopics erkannt")
            topics_result['main_topic'] = topics_data.get('main_topic', {})
            topics_result['subtopics'] = topics_data.get('subtopics', [])
        
        # Format 2: Alternatives Format mit 'topics' als Array
        elif isinstance(topics_data, dict) and 'topics' in topics_data and isinstance(topics_data['topics'], list):
            logger.info(f"[THEMEN] Format 2: Alternatives Format mit 'topics'-Array erkannt")
            topics_list = topics_data['topics']
            if topics_list:
                topics_result['main_topic'] = topics_list[0]
                topics_result['subtopics'] = topics_list[1:] if len(topics_list) > 1 else []
        
        # Format 3: Array von Themen
        elif isinstance(topics_data, list) and topics_data:
            logger.info(f"[THEMEN] Format 3: Array von Themen erkannt")
            topics_result['main_topic'] = topics_data[0]
            topics_result['subtopics'] = topics_data[1:] if len(topics_data) > 1 else []
        
        # Format 4: Alternatives Feld
        elif isinstance(topics_data, dict):
            for field in ["results", "items", "data", "theme", "subjects"]:
                if field in topics_data and isinstance(topics_data[field], list) and topics_data[field]:
                    logger.info(f"[THEMEN] Format 4: Alternatives Feld '{field}' erkannt")
                    themes_list = topics_data[field]
                    topics_result['main_topic'] = themes_list[0]
                    topics_result['subtopics'] = themes_list[1:] if len(themes_list) > 1 else []
                    break
        
        # SCHRITT 8: Struktur standardisieren
        logger.info(f"[THEMEN] Schritt 8: Standardisiere Feldnamen")
        
        # Hauptthema standardisieren
        if isinstance(topics_result['main_topic'], dict):
            # Typische Feldnamen-Konvertierungen
            mapping = {
                'name': 'title',
                'content': 'description',
                'text': 'description',
                'summary': 'description'
            }
            
            # Felder standardisieren
            for old_key, new_key in mapping.items():
                if old_key in topics_result['main_topic'] and new_key not in topics_result['main_topic']:
                    topics_result['main_topic'][new_key] = topics_result['main_topic'].pop(old_key)
            
            logger.info(f"[THEMEN] Hauptthema: {topics_result['main_topic'].get('title', 'Unbekannt')}")
        else:
            logger.warning(f"[THEMEN] Hauptthema hat unerwartetes Format: {type(topics_result['main_topic'])}")
            # Fallback für nicht-Dictionary-Hauptthema
            if isinstance(topics_result['main_topic'], str):
                topics_result['main_topic'] = {
                    'title': topics_result['main_topic'],
                    'description': 'Automatisch generierte Beschreibung'
                }
            else:
                topics_result['main_topic'] = {
                    'title': 'Hauptthema',
                    'description': 'Konnte kein Hauptthema extrahieren'
                }
        
        # Unterthemen standardisieren
        standardized_subtopics = []
        for i, subtopic in enumerate(topics_result['subtopics']):
            if isinstance(subtopic, dict):
                # Felder standardisieren
                for old_key, new_key in mapping.items():
                    if old_key in subtopic and new_key not in subtopic:
                        subtopic[new_key] = subtopic.pop(old_key)
                
                # Sicherstellen, dass Titel und Beschreibung vorhanden sind
                if 'title' in subtopic:
                    if 'description' not in subtopic:
                        subtopic['description'] = f"Unterthema zu {topics_result['main_topic'].get('title', 'Hauptthema')}"
                    
                    standardized_subtopics.append(subtopic)
                    logger.info(f"[THEMEN] Unterthema {i+1}: {subtopic.get('title')}")
            elif isinstance(subtopic, str):
                # String zu Dictionary konvertieren
                standardized_subtopics.append({
                    'title': subtopic,
                    'description': f"Unterthema zu {topics_result['main_topic'].get('title', 'Hauptthema')}"
                })
                logger.info(f"[THEMEN] Unterthema {i+1} (aus String): {subtopic}")
        
        topics_result['subtopics'] = standardized_subtopics
        
        # SCHRITT 9: Abschluss
        logger.info("="*50)
        logger.info(f"[THEMEN] EXTRAKTION (SYNC) ABGESCHLOSSEN")
        logger.info(f"[THEMEN] Hauptthema und {len(topics_result['subtopics'])} Unterthemen extrahiert")
        logger.info("="*50)
        
        return {"topics_data": topics_result, "usage": usage}

    except Exception as e:
        logger.error(f"[THEMEN] Fehler bei der Verarbeitung der Antwort: {e}")
        logger.error(f"[THEMEN] Antwortinhalt, der zum Fehler führte: {response_content[:500]}...")
        logger.error(f"[THEMEN] Vollständiger Fehler-Trace:", exc_info=True)
        # Fallback bei Verarbeitungsfehler
        return {"topics_data": {'main_topic': {'title': 'Fehler', 'description': f'Verarbeitungsfehler: {e}'}, 'subtopics': []}, "usage": None} 