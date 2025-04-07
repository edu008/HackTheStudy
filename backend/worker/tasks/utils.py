"""
Hilfsfunktionen für Worker-Tasks
-------------------------------

Dieses Modul enthält gemeinsam genutzte Hilfsfunktionen für die Worker-Tasks.
"""

import logging
import os
import json

logger = logging.getLogger(__name__)

# OpenAI API-Konfiguration
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
DEFAULT_MODEL = os.environ.get('OPENAI_DEFAULT_MODEL', 'gpt-3.5-turbo')


def call_openai_api(model, messages, temperature=0.7, max_tokens=None, **kwargs):
    """
    Ruft die OpenAI-API direkt und synchron auf ohne async/await.

    Args:
        model (str): Das zu verwendende OpenAI-Modell.
        messages (list): Liste der Nachrichtenelemente.
        temperature (float): Temperatur für die Antwortgenerierung.
        max_tokens (int, optional): Maximale Antwortlänge in Tokens.
        **kwargs: Weitere Parameter für die API.

    Returns:
        dict: OpenAI-API-Antwort.
    """
    try:
        # Importiere OpenAI
        import openai
        logger.info(f"OpenAI Version: {openai.__version__ if hasattr(openai, '__version__') else 'unbekannt'}")

        # Überprüfe API-Schlüssel
        if not OPENAI_API_KEY or (not OPENAI_API_KEY.startswith('sk-') and not OPENAI_API_KEY.startswith('sk-proj-')):
            logger.error("Ungültiger oder fehlender OpenAI-API-Schlüssel")
            raise ValueError("Ungültiger oder fehlender OpenAI-API-Schlüssel")

        # Logge die Anfrage
        logger.info("=== OPENAI PROMPT GESENDET ===")
        # Extrahiere System- und Benutzeranweisungen für bessere Lesbarkeit
        for i, msg in enumerate(messages):
            role = msg.get('role', 'unbekannt')
            content = msg.get('content', '')
            # Limitiere die Textlänge im Log für bessere Übersichtlichkeit
            if len(content) > 500:
                content_preview = content[:500] + "... [gekürzt]"
            else:
                content_preview = content
            logger.info(f"Message {i+1} ({role}): {content_preview}")
        
        # Logge weitere Parameter
        logger.info(f"Modell: {model}, Temperatur: {temperature}, Max Tokens: {max_tokens}")

        # API-Schlüssel setzen und Client konfigurieren (neue OpenAI API)
        logger.info("Verwende OpenAI API v1.0.0+")
        client = openai.OpenAI(
            api_key=OPENAI_API_KEY,
            # Explizite Header-Konfiguration
            default_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "assistants=v2"
            }
        )

        # Parameter für die Anfrage vorbereiten
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }

        # Optionale Parameter hinzufügen
        if max_tokens:
            params["max_tokens"] = max_tokens

        for key, value in kwargs.items():
            params[key] = value

        # Direkter API-Aufruf ohne async/await
        response = client.chat.completions.create(**params)
        
        # Konvertiere die Response in ein Dictionary
        if hasattr(response, 'model_dump'):
            # Pydantic v2
            response_dict = response.model_dump()
        elif hasattr(response, 'dict'):
            # Pydantic v1
            response_dict = response.dict()
        else:
            # Manueller Fallback
            response_dict = {
                'id': response.id,
                'model': response.model,
                'choices': [
                    {
                        'index': choice.index,
                        'message': {
                            'role': choice.message.role,
                            'content': choice.message.content
                        },
                        'finish_reason': choice.finish_reason
                    } for choice in response.choices
                ]
            }
        
        # Logge die Antwort
        logger.info("=== OPENAI ANTWORT ERHALTEN ===")
        response_text = ""
        try:
            if 'choices' in response_dict and len(response_dict['choices']) > 0:
                response_text = response_dict['choices'][0]['message']['content']
                if len(response_text) > 500:
                    logger.info(f"Antwort: {response_text[:500]}... [gekürzt]")
                else:
                    logger.info(f"Antwort: {response_text}")
            else:
                logger.info(f"Unerwartetes Antwortformat: {json.dumps(response_dict)[:200]}...")
        except Exception as log_error:
            logger.warning(f"Fehler beim Loggen der Antwort: {str(log_error)}")
            
        return response_dict

    except Exception as e:
        logger.error("Fehler beim OpenAI-API-Aufruf: %s", e)
        # Detaillierte Fehlerausgabe für Authentifizierungsprobleme
        if "authentication" in str(e).lower() or "auth" in str(e).lower() or "bearer" in str(e).lower():
            logger.error("Authentifizierungsfehler bei OpenAI-API: %s", str(e))
            logger.error("API-Key (erste 5 Zeichen): %s...", OPENAI_API_KEY[:5] if OPENAI_API_KEY and len(OPENAI_API_KEY) > 5 else "nicht gesetzt")
        raise


def normalize_text(text):
    """
    Normalisiert einen Text für die Verarbeitung.
    
    Args:
        text (str): Zu normalisierender Text
        
    Returns:
        str: Normalisierter Text
    """
    if not text:
        return ""
        
    # Entferne übermäßige Leerzeichen und Zeilenumbrüche
    normalized = " ".join(text.split())
    return normalized 