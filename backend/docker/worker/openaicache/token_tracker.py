"""
Token-Tracking-System für OpenAI-API-Aufrufe
"""

import logging
import time
import json
from datetime import datetime, timedelta
import redis
from flask import current_app, g
import os

logger = logging.getLogger(__name__)

def update_token_usage(user_id, usage_type, prompt_tokens, completion_tokens, model_name, metadata=None):
    """
    Aktualisiert die Token-Nutzung eines Benutzers.
    Wrapper-Funktion für Abwärtskompatibilität mit altem Tracking-System.
    
    Args:
        user_id: ID des Benutzers
        usage_type: Art der Nutzung (z.B. 'chat', 'image', etc.)
        prompt_tokens: Anzahl der Tokens in der Anfrage
        completion_tokens: Anzahl der Tokens in der Antwort
        model_name: Name des verwendeten Modells
        metadata: Zusätzliche Metadaten zur Nutzung (optional)
        
    Returns:
        dict: Trackinginformationen oder None bei Fehler
    """
    try:
        # Verbindung zu Redis herstellen
        redis_url = current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')
        redis_client = redis.from_url(redis_url)
        
        # Erstelle TokenTracker-Instanz
        tracker = TokenTracker(redis_client=redis_client)
        
        # Führe das Tracking durch
        return tracker.track_usage(
            user_id=user_id,
            usage_type=usage_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model_name=model_name,
            metadata=metadata
        )
    except Exception as e:
        logger.error(f"Fehler beim Token-Tracking: {str(e)}")
        return None

class TokenTracker:
    """
    Verfolgt den Token-Verbrauch für OpenAI-API-Aufrufe.
    Speichert Nutzungsstatistiken in Redis und bietet Methoden zur Abrechnung.
    """
    
    def __init__(self, redis_client=None):
        """
        Initialisiert den TokenTracker.
        
        Args:
            redis_client: Redis-Client für die Speicherung der Token-Nutzung
        """
        if redis_client:
            self.redis = redis_client
        else:
            # Versuche, eine Redis-Verbindung aus der Anwendungskonfiguration zu holen
            try:
                # Prüfe, ob Redis deaktiviert ist
                if os.environ.get('DISABLE_REDIS') == 'true':
                    logger.warning("Redis ist deaktiviert, Token-Tracking ist eingeschränkt")
                    self.redis = None
                    return
                    
                redis_url = current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')
                
                # Prüfe, ob memory:// als URL verwendet wird (Dummy-Modus)
                if redis_url.startswith('memory://'):
                    logger.warning("Redis ist im Memory-Modus, Token-Tracking ist eingeschränkt")
                    self.redis = None
                    return
                    
                self.redis = redis.from_url(redis_url, socket_connect_timeout=2.0, socket_timeout=2.0)
                # Ping-Test, um sicherzustellen, dass die Verbindung funktioniert
                self.redis.ping()
            except Exception as e:
                logger.warning(f"Redis-Verbindung konnte nicht hergestellt werden: {e}")
                self.redis = None
    
    def track_usage(self, user_id, usage_type, prompt_tokens, completion_tokens, model_name, metadata=None):
        """
        Verfolgt die Token-Nutzung eines Benutzers.
        
        Args:
            user_id: ID des Benutzers
            usage_type: Art der Nutzung (z.B. 'chat', 'image', etc.)
            prompt_tokens: Anzahl der Tokens in der Anfrage
            completion_tokens: Anzahl der Tokens in der Antwort
            model_name: Name des verwendeten Modells
            metadata: Zusätzliche Metadaten zur Nutzung (optional)
            
        Returns:
            dict: Trackinginformationen
        """
        if not self.redis:
            logger.warning("Redis nicht verfügbar - Token-Nutzung wird nicht verfolgt")
            return None
        
        timestamp = datetime.utcnow().isoformat()
        total_tokens = prompt_tokens + completion_tokens
        
        # Berechne die Kosten basierend auf dem Modell
        cost = self.calculate_token_cost(model_name, prompt_tokens, completion_tokens)
        
        # Erstelle den Tracking-Eintrag
        usage_entry = {
            'user_id': user_id,
            'timestamp': timestamp,
            'usage_type': usage_type,
            'model': model_name,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens,
            'cost': cost
        }
        
        if metadata:
            usage_entry['metadata'] = metadata
        
        # Speichere die Nutzungsdaten in Redis
        try:
            # Eindeutige ID für diesen Eintrag
            entry_id = f"{user_id}:{int(time.time() * 1000)}"
            self.redis.hset(f"token_usage:{entry_id}", mapping=usage_entry)
            
            # Füge zur Liste der Nutzungen des Benutzers hinzu
            self.redis.lpush(f"user_token_usage:{user_id}", entry_id)
            
            # Begrenze die Anzahl der gespeicherten Einträge pro Benutzer
            self.redis.ltrim(f"user_token_usage:{user_id}", 0, 999)  # Speichere maximal 1000 Einträge
            
            # Aktualisiere die Tagesstatistik
            day_key = datetime.utcnow().strftime("%Y-%m-%d")
            self.redis.hincrby(f"daily_token_usage:{day_key}", f"{user_id}:prompt", prompt_tokens)
            self.redis.hincrby(f"daily_token_usage:{day_key}", f"{user_id}:completion", completion_tokens)
            self.redis.hincrby(f"daily_token_usage:{day_key}", f"{user_id}:cost", int(cost * 1000000))  # Speichere in Mikro-Dollar
            
            # Setze ein Ablaufdatum für die täglichen Statistiken (90 Tage)
            self.redis.expire(f"daily_token_usage:{day_key}", 60 * 60 * 24 * 90)
            
            return usage_entry
            
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Token-Nutzung: {str(e)}")
            return None
    
    def get_user_usage(self, user_id, days=30, limit=100):
        """
        Ruft die Token-Nutzungshistorie eines Benutzers ab.
        
        Args:
            user_id: ID des Benutzers
            days: Anzahl der Tage in die Vergangenheit (Standard: 30)
            limit: Maximale Anzahl der zurückgegebenen Einträge
            
        Returns:
            list: Liste der Nutzungseinträge
        """
        if not self.redis:
            return []
        
        try:
            # Hole die neuesten Einträge
            entry_ids = self.redis.lrange(f"user_token_usage:{user_id}", 0, limit - 1)
            
            # Wenn keine Einträge gefunden wurden, leere Liste zurückgeben
            if not entry_ids:
                return []
            
            # Hole die Detaildaten für jeden Eintrag
            result = []
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            for entry_id in entry_ids:
                if isinstance(entry_id, bytes):
                    entry_id = entry_id.decode('utf-8')
                
                entry_data = self.redis.hgetall(f"token_usage:{entry_id}")
                
                # Konvertiere von Bytes zu Strings
                data = {k.decode('utf-8'): v.decode('utf-8') for k, v in entry_data.items()}
                
                # Überprüfe das Datum
                try:
                    entry_date = datetime.fromisoformat(data.get('timestamp', ''))
                    if entry_date < cutoff_date:
                        continue
                except (ValueError, TypeError):
                    # Bei Datumsproblemen den Eintrag überspringen
                    continue
                
                # Zahlen konvertieren
                for numeric_key in ['prompt_tokens', 'completion_tokens', 'total_tokens', 'cost']:
                    if numeric_key in data:
                        try:
                            data[numeric_key] = float(data[numeric_key])
                        except (ValueError, TypeError):
                            pass
                
                result.append(data)
            
            # Sortiere nach Zeitstempel, neueste zuerst
            result.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            return result
            
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Token-Nutzung: {str(e)}")
            return []
    
    def get_daily_usage_stats(self, user_id, days=30):
        """
        Ruft tägliche Nutzungsstatistiken für einen Benutzer ab.
        
        Args:
            user_id: ID des Benutzers
            days: Anzahl der Tage in die Vergangenheit
            
        Returns:
            dict: Tägliche Nutzungsstatistiken
        """
        if not self.redis:
            return {}
        
        try:
            result = {}
            current_date = datetime.utcnow()
            
            # Sammle Daten für jeden Tag
            for day_offset in range(days):
                day_date = current_date - timedelta(days=day_offset)
                day_key = day_date.strftime("%Y-%m-%d")
                
                # Hole die Daten für diesen Tag
                prompt_tokens = self.redis.hget(f"daily_token_usage:{day_key}", f"{user_id}:prompt")
                completion_tokens = self.redis.hget(f"daily_token_usage:{day_key}", f"{user_id}:completion")
                cost_micro = self.redis.hget(f"daily_token_usage:{day_key}", f"{user_id}:cost")
                
                # Wenn Daten gefunden wurden, zum Ergebnis hinzufügen
                if prompt_tokens or completion_tokens or cost_micro:
                    result[day_key] = {
                        'prompt_tokens': int(prompt_tokens or 0),
                        'completion_tokens': int(completion_tokens or 0),
                        'total_tokens': int(prompt_tokens or 0) + int(completion_tokens or 0),
                        'cost': float(cost_micro or 0) / 1000000  # Konvertiere von Mikro-Dollar zu Dollar
                    }
            
            return result
            
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der täglichen Statistiken: {e}")
            return {}
    
    @staticmethod
    def calculate_token_cost(model_name, prompt_tokens, completion_tokens):
        """
        Berechnet die Kosten für Token basierend auf dem Modell.
        
        Args:
            model_name: Name des verwendeten Modells
            prompt_tokens: Anzahl der Tokens in der Anfrage
            completion_tokens: Anzahl der Tokens in der Antwort
            
        Returns:
            float: Kosten in USD
        """
        # Preisliste für verschiedene Modelle (Stand März 2024)
        pricing = {
            # GPT-3.5 Modelle
            'gpt-3.5-turbo': {'prompt': 0.0000005, 'completion': 0.0000015},  # $0.50/1M Prompt, $1.50/1M Completion
            'gpt-3.5-turbo-16k': {'prompt': 0.000001, 'completion': 0.000002},  # $1.00/1M Prompt, $2.00/1M Completion
            
            # GPT-4 Modelle
            'gpt-4': {'prompt': 0.00003, 'completion': 0.00006},  # $30.00/1M Prompt, $60.00/1M Completion
            'gpt-4-turbo': {'prompt': 0.00001, 'completion': 0.00003},  # $10.00/1M Prompt, $30.00/1M Completion
            'gpt-4-32k': {'prompt': 0.00006, 'completion': 0.00012},  # $60.00/1M Prompt, $120.00/1M Completion
            
            # Claude Modelle (falls verwendet)
            'claude-instant-1': {'prompt': 0.000001, 'completion': 0.000004},  # $1.00/1M Prompt, $4.00/1M Completion
            'claude-2': {'prompt': 0.000008, 'completion': 0.000024},  # $8.00/1M Prompt, $24.00/1M Completion
        }
        
        # Standardpreise verwenden, wenn das Modell nicht bekannt ist
        model_pricing = pricing.get(model_name.lower(), pricing['gpt-3.5-turbo'])
        
        # Berechne die Kosten
        prompt_cost = prompt_tokens * model_pricing['prompt']
        completion_cost = completion_tokens * model_pricing['completion']
        
        return prompt_cost + completion_cost 