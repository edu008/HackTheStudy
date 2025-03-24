import os
import time
import json
import traceback
from openai import OpenAI
from flask import current_app
from tasks import redis_client
from api.log_utils import AppLogger
from api.token_tracking import count_tokens, calculate_token_cost, deduct_credits, check_credits_available
import logging

class OptimizedOpenAIClient:
    _instance = None
    _api_key = None
    _model_name = None
    
    @classmethod
    def get_instance(cls):
        """Singleton-Pattern für den OpenAI-Client"""
        if cls._instance is None:
            api_key = cls._get_api_key()
            if not api_key:
                return None
                
            cls._api_key = api_key
            cls._instance = OpenAI(api_key=api_key)
            
        return cls._instance
        
    @classmethod
    def _get_api_key(cls):
        """API-Schlüssel aus verschiedenen Quellen mit Caching"""
        if cls._api_key:
            return cls._api_key
            
        # Versuche aus App-Kontext
        try:
            key = current_app.config.get('OPENAI_API_KEY')
            if key:
                return key
        except RuntimeError:
            pass
            
        # Versuche aus Umgebungsvariable
        return os.environ.get('OPENAI_API_KEY')
        
    @classmethod
    def get_model(cls):
        """Modellname abrufen mit Caching"""
        if cls._model_name:
            return cls._model_name
            
        try:
            model = current_app.config.get('OPENAI_MODEL', 'gpt-4o').strip()
        except RuntimeError:
            model = os.environ.get('OPENAI_MODEL', 'gpt-4o').strip()
            
        cls._model_name = model
        return model
        
    @classmethod
    def query(cls, prompt, system_content=None, session_id=None, user_id=None, function_name=None, temperature=0.7, max_tokens=4000):
        """Optimierte OpenAI-Anfrage mit umfassendem Logging und Fehlerbehandlung"""
        client = cls.get_instance()
        if not client:
            error_msg = "OpenAI-Client konnte nicht initialisiert werden"
            if session_id:
                AppLogger.track_error(session_id, "openai_client_error", error_msg)
            raise ValueError(error_msg)
            
        model = cls.get_model()
        
        # System-Content standardisieren
        if not system_content:
            system_content = "You are a helpful assistant that provides concise, accurate information."
            
        # Token-Zählung
        input_tokens = count_tokens(system_content) + count_tokens(prompt)
        
        # Anfrage loggen
        AppLogger.log_openai_request(
            session_id=session_id, 
            model=model,
            system_preview=system_content,
            prompt_preview=prompt,
            tokens_in=input_tokens
        )
        
        # Kredit-Check wenn Benutzer-ID vorhanden
        if user_id:
            estimated_output_tokens = min(4000, input_tokens // 2)
            estimated_cost = calculate_token_cost(
                model=model,
                input_tokens=input_tokens,
                output_tokens=estimated_output_tokens
            )
            
            # Prüfen, ob genügend Credits vorhanden sind
            if not check_credits_available(estimated_cost, user_id):
                error_msg = f"Nicht genügend Credits für diese Operation (benötigt: {estimated_cost})"
                if session_id:
                    AppLogger.track_error(
                        session_id, 
                        "insufficient_credits", 
                        error_msg,
                        diagnostics={"estimated_cost": estimated_cost, "tokens": input_tokens}
                    )
                raise ValueError(error_msg)
                
        # API-Aufruf mit Zeitmessung
        start_time = time.time()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Erfolgreiche Antwort
            duration_ms = int((time.time() - start_time) * 1000)
            response_text = response.choices[0].message.content.strip()
            
            # Response loggen
            AppLogger.log_openai_response(
                session_id=session_id,
                response_preview=response_text,
                tokens_out=response.usage.completion_tokens if hasattr(response, 'usage') else None,
                duration_ms=duration_ms
            )
            
            # Credits abziehen wenn Benutzer-ID vorhanden
            if user_id and hasattr(response, 'usage'):
                actual_cost = calculate_token_cost(
                    model=model,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens
                )
                deduct_credits(
                    user_id, 
                    actual_cost, 
                    session_id=session_id,
                    function_name=function_name
                )
                
            # Antwort in Redis cachen für Diagnose
            if session_id:
                cache_key = f"openai_last_response:{session_id}"
                redis_client.set(
                    cache_key, 
                    json.dumps({
                        "text": response_text[:1000] + "..." if len(response_text) > 1000 else response_text,
                        "tokens_in": response.usage.prompt_tokens if hasattr(response, 'usage') else input_tokens,
                        "tokens_out": response.usage.completion_tokens if hasattr(response, 'usage') else None,
                        "model": model,
                        "timestamp": time.time()
                    }),
                    ex=3600
                )
                
            return response_text
            
        except Exception as e:
            # Fehlerbehandlung mit detailliertem Logging
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            
            if session_id:
                AppLogger.track_error(
                    session_id,
                    "openai_api_error",
                    error_msg,
                    trace=traceback.format_exc(),
                    diagnostics={
                        "model": model,
                        "duration_ms": duration_ms,
                        "input_tokens": input_tokens
                    }
                )
                
            raise 

    def chat_completion(self, prompt, system_content=None, model=None, temperature=0.7, 
                       max_tokens=4000, use_cache=True, user_id=None, session_id=None, 
                       function_name="chat_completion", endpoint=None, max_retries=3):
        logger = logging.getLogger(__name__)
        
        # Ausführliches Logging der OpenAI-Anfrage
        logger.debug(f"OpenAI API-Anfrage gestartet: session_id={session_id}, function={function_name}, model={model}")
        logger.debug(f"Prompt: {prompt[:100]}...")  # Nur Anfang des Prompts loggen
        
        # Überwache Start der Anfrage
        start_time = time.time()
        
        # Import hier, um Zirkelbezüge zu vermeiden
        import traceback
        import json
        
        client = self.get_instance()
        if not client:
            error_msg = "OpenAI-Client konnte nicht initialisiert werden"
            if session_id:
                # In Redis für Debugging speichern
                error_data = {
                    "error_type": "client_initialization",
                    "message": error_msg,
                    "timestamp": time.time(),
                    "function": function_name
                }
                redis_key = f"openai_error:{session_id}"
                try:
                    redis_client.set(redis_key, json.dumps(error_data), ex=3600)
                except Exception as redis_err:
                    logger.error(f"Fehler beim Speichern des OpenAI-Errors in Redis: {str(redis_err)}")
                
                # Auch den processing_status auf "error" setzen
                status_key = f"processing_status:{session_id}"
                redis_client.set(status_key, "error", ex=3600)
                
                # Speichere detaillierte Fehlerinformationen
                error_details_key = f"error_details:{session_id}"
                error_details = {
                    "error_type": "openai_client_error",
                    "message": error_msg,
                    "timestamp": time.time(),
                    "function": function_name
                }
                redis_client.set(error_details_key, json.dumps(error_details), ex=3600)
                
                from api.log_utils import AppLogger
                AppLogger.track_error(session_id, "openai_client_error", error_msg)
            
            raise ValueError(error_msg)
        
        try:
            # Führe OpenAI API-Anfrage durch und protokolliere bei Fehler
            response = client.chat.completions.create(
                model=model or self.get_model(),
                messages=[
                    {"role": "system", "content": system_content or "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Erfolgsfall protokollieren
            end_time = time.time()
            duration = end_time - start_time
            
            logger.debug(f"OpenAI API-Anfrage erfolgreich: session_id={session_id}, dauer={duration:.2f}s")
            
            # Extrahiere und gib Antworttext zurück
            response_text = response.choices[0].message.content.strip()
            
            # Speichere erfolgreiche Antwort in Redis für Debugging
            if session_id:
                response_key = f"openai_last_response:{session_id}"
                response_data = {
                    "text_preview": response_text[:500] + "..." if len(response_text) > 500 else response_text,
                    "model": model or self.get_model(),
                    "tokens_in": response.usage.prompt_tokens if hasattr(response, 'usage') else None,
                    "tokens_out": response.usage.completion_tokens if hasattr(response, 'usage') else None,
                    "duration": duration,
                    "timestamp": time.time()
                }
                try:
                    redis_client.set(response_key, json.dumps(response_data), ex=3600)
                except Exception as redis_err:
                    logger.error(f"Fehler beim Speichern der OpenAI-Antwort in Redis: {str(redis_err)}")
            
            return response_text
            
        except Exception as e:
            # Fehlerbehandlung mit detailliertem Logging
            end_time = time.time()
            duration = end_time - start_time
            error_msg = str(e)
            
            logger.error(f"OpenAI API-Fehler: session_id={session_id}, error={error_msg}, dauer={duration:.2f}s")
            logger.error(traceback.format_exc())
            
            # Details in Redis für Debugging speichern
            if session_id:
                # Speichere Fehlerinformationen
                error_data = {
                    "error": error_msg,
                    "error_type": type(e).__name__,
                    "timestamp": time.time(),
                    "duration": duration,
                    "function": function_name,
                    "traceback": traceback.format_exc()
                }
                error_key = f"openai_error:{session_id}"
                try:
                    redis_client.set(error_key, json.dumps(error_data), ex=3600)
                except Exception as redis_err:
                    logger.error(f"Fehler beim Speichern des OpenAI-Errors in Redis: {str(redis_err)}")
                
                # Setze processing_status auf "error"
                status_key = f"processing_status:{session_id}"
                redis_client.set(status_key, "error", ex=3600)
                
                # Speichere detaillierte Fehlerinformationen für Frontend
                error_details_key = f"error_details:{session_id}"
                error_details = {
                    "error_type": "openai_api_error",
                    "message": f"OpenAI API-Fehler: {error_msg}",
                    "timestamp": time.time(),
                    "function": function_name,
                    "traceback": traceback.format_exc()
                }
                redis_client.set(error_details_key, json.dumps(error_details), ex=3600)
                
                from api.log_utils import AppLogger
                AppLogger.track_error(
                    session_id,
                    "openai_api_error",
                    f"OpenAI API-Fehler: {error_msg}",
                    trace=traceback.format_exc()
                )
            
            # Weitergabe des Fehlers
            raise 