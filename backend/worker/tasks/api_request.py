"""
Task zur Verarbeitung von API-Anfragen
"""
import logging
import traceback
import time
from core import get_flask_app
from utils import log_function_call

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
        
        Args:
            endpoint: Der API-Endpunkt, der aufgerufen werden soll
            method: Die HTTP-Methode (GET, POST, etc.)
            payload: Die Anfragedaten (optional)
            user_id: ID des anfragenden Benutzers (optional)
            
        Returns:
            Das Ergebnis der API-Anfrage
        """
        task_id = self.request.id
        log_api_requests = logger.isEnabledFor(logging.INFO)
        
        if log_api_requests:
            # Reduziere die Payload für Logging
            safe_payload = "[REDUZIERTE PAYLOAD]"
            if payload and isinstance(payload, dict):
                # Kopiere und filtere die Payload
                safe_payload = payload.copy()
                for key in ['password', 'token', 'api_key', 'secret']:
                    if key in safe_payload:
                        safe_payload[key] = '[REDACTED]'
            
            api_request_logger.info(f"Worker verarbeitet API-Anfrage: {method} {endpoint} - User: {user_id} - Payload: {safe_payload}")
        
        try:
            # Eigentliche Verarbeitung der Anfrage
            start_time = time.time()
            result = process_api_task(endpoint, method, payload, user_id)
            processing_time = time.time() - start_time
            
            if log_api_requests:
                api_request_logger.info(f"Worker hat API-Anfrage verarbeitet: {method} {endpoint} - Zeit: {processing_time:.2f}s")
            
            return result
        except Exception as e:
            # Fehlerbehandlung mit Logging
            error_trace = traceback.format_exc()
            logger.error(f"Fehler bei API-Anfragenverarbeitung: {str(e)}")
            logger.error(error_trace)
            
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
    def process_api_task(endpoint, method, payload=None, user_id=None):
        """
        Verarbeitet API-Anfragen und leitet sie an die entsprechenden Endpunkte weiter.
        
        Args:
            endpoint: Der API-Endpunkt, der aufgerufen werden soll
            method: Die HTTP-Methode (GET, POST, etc.)
            payload: Die Anfragedaten (optional)
            user_id: ID des anfragenden Benutzers (optional)
            
        Returns:
            Das Ergebnis der API-Anfrage
        """
        logger.info(f"Verarbeite API-Anfrage: {method} {endpoint}")
        
        try:
            # Erstelle Flask-App-Kontext
            flask_app = get_flask_app()
            
            with flask_app.app_context():
                # Hier würde die Logik stehen, um die Anfrage an den entsprechenden
                # API-Endpunkt weiterzuleiten. In einer vollständigen Implementierung
                # würden wir die Anfrage an die richtige Komponente delegieren.
                
                # Da wir keine vollständige API-Implementierung haben, geben wir einen
                # Platzhalter zurück
                from datetime import datetime
                return {
                    "status": "processed",
                    "endpoint": endpoint,
                    "method": method,
                    "timestamp": datetime.now().isoformat()
                }
        except Exception as e:
            logger.error(f"Fehler bei API-Anfragenverarbeitung: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    # Gib die Task-Funktion zurück, damit sie von außen aufgerufen werden kann
    return process_api_request 