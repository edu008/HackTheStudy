"""
OpenAI API Utility für Worker-Tasks
----------------------------------

Dieses Modul stellt Funktionen für den Aufruf der OpenAI API bereit.
"""

import os
import json
import logging
import time
from typing import Dict, List, Optional, Any, Union

# Logger konfigurieren
logger = logging.getLogger(__name__)

# OpenAI API-Konfiguration aus Umgebungsvariablen
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
DEFAULT_MODEL = os.environ.get('OPENAI_DEFAULT_MODEL', 'gpt-3.5-turbo')
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # Exponentieller Backoff-Faktor

def call_openai_api(
    model: str = DEFAULT_MODEL,
    messages: List[Dict[str, str]] = None,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    response_format: Dict[str, str] = None,
    default_headers: Dict[str, str] = None
) -> Dict[str, Any]:
    """
    Ruft die OpenAI API mit Retry-Mechanismus auf (SYNCHRONE VERSION).
    
    Args:
        model: Das zu verwendende OpenAI-Modell
        messages: Liste von Message-Objekten mit 'role' und 'content'
        temperature: Temperatur für die Kreativität (0.0-1.0)
        max_tokens: Maximale Token-Anzahl für die Antwort
        response_format: Format der Antwort (optional, z.B. {"type": "json_object"})
        default_headers: Zusätzliche Header für die API-Anfrage
        
    Returns:
        Dict: API-Antwort als Dictionary
    """
    # Importiere den synchronen OpenAI-Client
    # Stelle sicher, dass die korrekte OpenAI-Bibliothek installiert ist (v1.x+)
    try:
         from openai import OpenAI
    except ImportError:
         logger.error("OpenAI-Bibliothek (openai>=1.0) nicht gefunden. Bitte installieren.")
         return {"error": "OpenAI library not found"}
    
    if not messages:
        messages = [{"role": "user", "content": "Hallo"}]
    
    if not OPENAI_API_KEY:
        logger.error("Kein OpenAI API-Schlüssel konfiguriert")
        return {
            "error": "Kein API-Schlüssel konfiguriert",
            "choices": [{"message": {"content": "Fehler: OpenAI API nicht verfügbar"}}]
        }
    
    # Parameter für die Anfrage
    params = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    
    # Optional: response_format hinzufügen (für JSON-Antworten)
    if response_format:
        params["response_format"] = response_format
    
    # Default-Header
    headers = {
        "OpenAI-Beta": "assistants=v2"
    }
    
    # Zusätzliche Header hinzufügen
    if default_headers:
        headers.update(default_headers)
    
    # API-Client initialisieren (ist standardmäßig synchron)
    client = OpenAI(
        api_key=OPENAI_API_KEY,
        default_headers=headers
    )
    
    # API-Anfrage mit Retry-Logik
    retry_count = 0
    last_error = None
    
    while retry_count <= MAX_RETRIES:
        try:
            logger.debug(f"Starte SYNC OpenAI API-Anfrage...")
            # Führe die API-Anfrage durch (OHNE await)
            completion = client.chat.completions.create(**params)
            
            # Konvertiere die Antwort in ein Dictionary
            result = {
                "model": completion.model,
                "choices": [
                    {
                        "message": {
                            "role": completion.choices[0].message.role,
                            "content": completion.choices[0].message.content
                        },
                        "index": 0,
                        "finish_reason": completion.choices[0].finish_reason
                    }
                ],
                "usage": {
                    "prompt_tokens": completion.usage.prompt_tokens,
                    "completion_tokens": completion.usage.completion_tokens,
                    "total_tokens": completion.usage.total_tokens
                }
            }
            
            logger.debug(f"OpenAI API-Antwort erhalten (sync)...")
            return result
        
        except Exception as e:
            retry_count += 1
            last_error = str(e)
            
            if retry_count > MAX_RETRIES:
                logger.error(f"Maximale Anzahl an Versuchen ({MAX_RETRIES}) überschritten: {e}")
                break
            
            # Exponentieller Backoff
            wait_time = RETRY_BACKOFF_BASE ** retry_count
            logger.warning(f"Fehler bei OpenAI-Anfrage (Versuch {retry_count}/{MAX_RETRIES}): {e}")
            logger.warning(f"Warte {wait_time} Sekunden vor dem nächsten Versuch...")
            time.sleep(wait_time)
    
    # Wenn alle Versuche fehlschlagen
    logger.error(f"OpenAI API-Anfrage nach {MAX_RETRIES} Versuchen fehlgeschlagen: {last_error}")
    return {
        "error": f"API-Anfrage fehlgeschlagen: {last_error}",
        "choices": [{"message": {"content": f"Fehler: {last_error}"}}]
    }

def extract_json_from_response(response_content: str) -> Any:
    """
    Extrahiert JSON aus einer Antwort-Zeichenkette.
    
    Args:
        response_content: Die API-Antwort als Text
        
    Returns:
        Der extrahierte JSON-Inhalt oder die unveränderte Antwort
    """
    try:
        # Versuche direktes Parsen
        data = json.loads(response_content)
        
        # Prüfen auf verschiedene Formate und normalisieren
        if isinstance(data, dict):
            # Fall 1: Direktes Array von Karten im "cards"-Feld
            if "cards" in data and isinstance(data["cards"], list):
                return data
                
            # Fall 2: Falsch formatiert mit "question" als Hauptschlüssel und "answer" als Array
            if "question" in data and "answer" in data and isinstance(data["answer"], list):
                logger.warning("Falsch formatierte Antwort erkannt: 'question' und 'answer' auf oberster Ebene")
                return data["answer"]  # Gib direkt das Answer-Array zurück
                
            # Fall 3: Falscher Schlüsselname, z.B. "flashcards" statt "cards"
            for key in ["flashcards", "lernkarten", "results"]:
                if key in data and isinstance(data[key], list):
                    logger.warning(f"Alternativer Schlüssel gefunden: '{key}'")
                    return {
                        "cards": data[key]
                    }
            
            # Fall 4: Direkt ein Objekt mit "question"/"answer" (einzelne Karte)
            if "question" in data and "answer" in data and not isinstance(data["answer"], list):
                logger.warning("Einzelne Karte erkannt, konvertiere zu Array")
                return [data]
        
        # Wenn es bereits eine Liste ist, behalte es bei
        return data
    except json.JSONDecodeError:
        # Suche nach JSON in Code-Blöcken
        import re
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_content)
        if json_match:
            try:
                return extract_json_from_response(json_match.group(1))  # Rekursiver Aufruf mit extrahiertem JSON
            except json.JSONDecodeError:
                pass
        
        # Suche nach JSON-Array
        json_array_match = re.search(r'\[([\s\S]*)\]', response_content)
        if json_array_match:
            try:
                return json.loads(f"[{json_array_match.group(1)}]")
            except json.JSONDecodeError:
                pass
        
        # Wenn kein JSON gefunden wurde, gib den Text zurück
        return response_content 