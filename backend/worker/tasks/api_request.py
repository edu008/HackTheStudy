"""
Task zur Verarbeitung von API-Anfragen
"""
import logging
import traceback
import time
import json
import uuid
from core import get_flask_app
from utils import log_function_call
from api.openai_client import call_openai_api, extract_text_from_openai_response
from redis_utils.utils import safe_redis_set, safe_redis_get

# Logger konfigurieren
logger = logging.getLogger(__name__)
api_request_logger = logging.getLogger('api_requests')

def register_task(celery_app):
    """
    Registriert die process_api_request Task bei der Celery-App.
    
    Args:
        celery_app: Die Celery-App-Instanz
    """
    @celery_app.task(
        name="process_api_request", 
        bind=True, 
        max_retries=3,
        acks_late=True,
        reject_on_worker_lost=True,
        soft_time_limit=300,  # 5 Minuten Limit
        time_limit=360        # 6 Minuten hartes Limit
    )
    @log_function_call
    def process_api_request(self, endpoint, method, payload=None, user_id=None):
        """
        Verarbeitet API-Anfragen asynchron und protokolliert sie.
        Diese Funktion entspricht der vom Main-Backend erwarteten Signatur.
        
        Args:
            endpoint: Der API-Endpunkt, der aufgerufen werden soll
            method: Die HTTP-Methode (GET, POST, etc.)
            payload: Die Anfragedaten (optional)
            user_id: ID des anfragenden Benutzers (optional)
            
        Returns:
            Das Ergebnis der API-Anfrage
        """
        # Generiere eine eindeutige Request-ID
        request_id = str(uuid.uuid4())
        
        # Delegiere an die interne Implementierung
        return _process_api_request_internal(self, request_id, method, endpoint, payload, user_id)
    
    def _process_api_request_internal(self, request_id, method, endpoint, data=None, user_id=None):
        """
        Interne Implementierung der API-Anfragenverarbeitung.
        
        Args:
            self: Die Celery-Task-Instanz
            request_id: Eindeutige ID der Anfrage
            method: Die HTTP-Methode
            endpoint: Der API-Endpunkt
            data: Die Anfragedaten (optional)
            user_id: ID des anfragenden Benutzers (optional)
            
        Returns:
            Das Ergebnis der API-Anfrage
        """
        task_id = self.request.id
        log_api_requests = logger.isEnabledFor(logging.INFO)
        
        # Aktualisiere den Status im Redis
        safe_redis_set(f"api_request_status:{request_id}", "processing", ex=3600)
        
        if log_api_requests:
            # Reduziere die Payload für Logging
            safe_payload = "[REDUZIERTE PAYLOAD]"
            if data and isinstance(data, dict):
                # Kopiere und filtere die Payload
                safe_payload = data.copy()
                for key in ['password', 'token', 'api_key', 'secret']:
                    if key in safe_payload:
                        safe_payload[key] = '[REDACTED]'
            
            api_request_logger.info(f"Worker verarbeitet API-Anfrage: {method} {endpoint} - User: {user_id} - Payload: {safe_payload}")
        
        try:
            # Eigentliche Verarbeitung der Anfrage
            start_time = time.time()
            result = process_api_task(request_id, method, endpoint, data, user_id)
            processing_time = time.time() - start_time
            
            # Speichere das Ergebnis in Redis
            safe_redis_set(f"api_request_result:{request_id}", json.dumps(result), ex=3600)
            safe_redis_set(f"api_request_status:{request_id}", "completed", ex=3600)
            
            if log_api_requests:
                api_request_logger.info(f"Worker hat API-Anfrage verarbeitet: {method} {endpoint} - Zeit: {processing_time:.2f}s")
            
            return result
        except Exception as e:
            # Fehlerbehandlung mit Logging
            error_trace = traceback.format_exc()
            logger.error(f"Fehler bei API-Anfragenverarbeitung: {str(e)}")
            logger.error(error_trace)
            
            # Fehlerdetails in Redis speichern
            safe_redis_set(f"api_request_status:{request_id}", "error", ex=3600)
            safe_redis_set(f"api_request_error:{request_id}", json.dumps({
                "error": str(e),
                "traceback": error_trace,
                "timestamp": time.time()
            }), ex=3600)
            
            # Wiederholungsversuche mit exponentieller Backoff-Zeit
            retry_count = self.request.retries
            max_retries = self.max_retries
            
            if retry_count < max_retries:
                backoff = 2 ** retry_count  # Exponentieller Backoff: 1, 2, 4, 8... Sekunden
                logger.info(f"Wiederhole API-Anfrage {method} {endpoint} in {backoff} Sekunden (Versuch {retry_count+1}/{max_retries+1})")
                raise self.retry(exc=e, countdown=backoff)
            else:
                # Maximale Wiederholungsversuche erreicht
                logger.error(f"Maximale Wiederholungsversuche ({max_retries}) für API-Anfrage {method} {endpoint} erreicht. Gebe auf.")
                raise
    
    # Implementierung der Hilfsunktion für die eigentliche API-Verarbeitung
    def process_api_task(request_id, method, endpoint, data=None, user_id=None):
        """
        Verarbeitet API-Anfragen und leitet sie an die entsprechenden Endpunkte weiter.
        
        Args:
            request_id: Eindeutige ID der Anfrage
            method: Die HTTP-Methode (GET, POST, etc.)
            endpoint: Der API-Endpunkt, der aufgerufen werden soll
            data: Die Anfragedaten (optional)
            user_id: ID des anfragenden Benutzers (optional)
            
        Returns:
            Das Ergebnis der API-Anfrage
        """
        logger.info(f"Verarbeite API-Anfrage: {method} {endpoint}")
        
        try:
            # Erstelle Flask-App-Kontext
            flask_app = get_flask_app()
            
            with flask_app.app_context():
                # Router für verschiedene Endpunkte
                if endpoint.startswith('/api/v1/openai'):
                    return process_openai_request(data, user_id)
                elif endpoint.startswith('/api/v1/analyze'):
                    return process_content_analysis(data, user_id)
                elif endpoint.startswith('/api/v1/extract'):
                    return process_content_extraction(data, user_id)
                else:
                    # Generische Verarbeitung für unbekannte Endpunkte
                    return {
                        "status": "processed",
                        "endpoint": endpoint,
                        "method": method,
                        "request_id": request_id,
                        "timestamp": time.time(),
                        "message": "Endpunkt nicht implementiert"
                    }
        except Exception as e:
            logger.error(f"Fehler bei API-Anfragenverarbeitung: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def process_openai_request(data, user_id=None):
        """
        Verarbeitet OpenAI-API-Anfragen.
        
        Args:
            data: Die Anfragedaten
            user_id: ID des anfragenden Benutzers (optional)
            
        Returns:
            Die OpenAI-API-Antwort
        """
        logger.info("Verarbeite OpenAI-Anfrage")
        
        # Extrahiere Parameter aus den Daten
        messages = data.get('messages', [])
        model = data.get('model', 'gpt-4o')  # Default zu GPT-4o
        temperature = data.get('temperature', 0.7)
        max_tokens = data.get('max_tokens')
        
        # Weitere Parameter
        use_cache = data.get('use_cache', True)
        
        # OpenAI-API aufrufen
        response = call_openai_api(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            use_cache=use_cache
        )
        
        # Optional: Einfache Nachbearbeitung
        result = {
            "model": response.get('model', model),
            "content": extract_text_from_openai_response(response),
            "usage": response.get('usage', {}),
            "cached": "_elapsed_time" not in response,  # Wenn keine Ausführungszeit vorhanden, war es ein Cache-Treffer
            "timestamp": time.time()
        }
        
        return result
    
    def process_content_analysis(data, user_id=None):
        """
        Analysiert Inhalte mit Hilfe von OpenAI.
        
        Args:
            data: Die Anfragedaten mit dem zu analysierenden Text
            user_id: ID des anfragenden Benutzers (optional)
            
        Returns:
            Die Analyseergebnisse
        """
        logger.info("Verarbeite Inhaltsanalyse-Anfrage")
        
        text = data.get('text', '')
        language = data.get('language', 'auto')
        analysis_type = data.get('type', 'general')
        
        # Prompt erstellen basierend auf dem Analysetyp
        if analysis_type == 'summary':
            prompt = f"Fasse den folgenden Text zusammen:\n\n{text}"
        elif analysis_type == 'key_points':
            prompt = f"Extrahiere die wichtigsten Punkte aus dem folgenden Text:\n\n{text}"
        elif analysis_type == 'questions':
            prompt = f"Erstelle Lernfragen basierend auf dem folgenden Text:\n\n{text}"
        else:  # general
            prompt = f"Analysiere den folgenden Text und gib eine detaillierte Zusammenfassung, Schlüsselkonzepte und wichtige Erkenntnisse:\n\n{text}"
        
        # OpenAI-API für die Analyse aufrufen
        response = call_openai_api(
            messages=[
                {"role": "system", "content": "Du bist ein hilfreicher Assistent, der Texte analysiert."},
                {"role": "user", "content": prompt}
            ],
            model="gpt-4o",
            temperature=0.3,  # Niedrigere Temperatur für konsistentere Ergebnisse
            use_cache=True
        )
        
        return {
            "text": extract_text_from_openai_response(response),
            "analysis_type": analysis_type,
            "timestamp": time.time()
        }
        
    def process_content_extraction(data, user_id=None):
        """
        Extrahiert strukturierte Informationen aus Text.
        
        Args:
            data: Die Anfragedaten mit dem zu extrahierenden Text
            user_id: ID des anfragenden Benutzers (optional)
            
        Returns:
            Die extrahierten Informationen
        """
        logger.info("Verarbeite Inhaltsextraktions-Anfrage")
        
        text = data.get('text', '')
        extraction_type = data.get('type', 'general')
        
        # Je nach Extraktionstyp unterschiedliche Prompts verwenden
        if extraction_type == 'topics':
            prompt = f"Extrahiere die wichtigsten Themen aus dem folgenden Text als JSON-Array:\n\n{text}"
        elif extraction_type == 'entities':
            prompt = f"Extrahiere die wichtigsten Entitäten (Personen, Orte, Organisationen) aus dem folgenden Text als JSON:\n\n{text}"
        elif extraction_type == 'dates':
            prompt = f"Extrahiere alle Datumsangaben aus dem folgenden Text als JSON-Array:\n\n{text}"
        else:
            prompt = f"Extrahiere die wichtigsten Informationen aus dem folgenden Text als strukturiertes JSON-Objekt:\n\n{text}"
        
        # OpenAI-API für die Extraktion aufrufen
        response = call_openai_api(
            messages=[
                {"role": "system", "content": "Du bist ein hilfreicher Assistent, der strukturierte Informationen aus Text extrahiert. Gib deine Antwort im JSON-Format zurück."},
                {"role": "user", "content": prompt}
            ],
            model="gpt-4o",
            temperature=0.2,  # Sehr niedrige Temperatur für konsistente strukturierte Ausgaben
            use_cache=True
        )
        
        # Versuch, die Antwort als JSON zu parsen
        try:
            extracted_text = extract_text_from_openai_response(response)
            # Extrahiere nur den JSON-Teil, falls die Antwort mehr Text enthält
            if "```json" in extracted_text:
                json_part = extracted_text.split("```json")[1].split("```")[0].strip()
            elif "```" in extracted_text:
                json_part = extracted_text.split("```")[1].strip()
            else:
                json_part = extracted_text
                
            extracted_data = json.loads(json_part)
            return {
                "data": extracted_data,
                "extraction_type": extraction_type,
                "timestamp": time.time()
            }
        except (json.JSONDecodeError, IndexError) as e:
            logger.error(f"Fehler beim Parsen der extrahierten Daten: {str(e)}")
            # Fallback auf Rohtext
            return {
                "text": extract_text_from_openai_response(response),
                "extraction_type": extraction_type,
                "timestamp": time.time(),
                "error": "Could not parse as JSON"
            }
    
    # Gib die Task-Funktion zurück, damit sie von außen aufgerufen werden kann
    return process_api_request 