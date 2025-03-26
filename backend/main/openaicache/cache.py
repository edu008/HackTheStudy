"""
OpenAI Cache-Implementierung für das Caching von API-Aufrufen.
Dies reduziert Kosten und Latenz durch Wiederverwendung von identischen Anfragen.
"""

import json
import hashlib
import logging
import time
from typing import Any, Dict, Optional, Union, List

from core.redis_client import redis_client

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Singleton-Instanz
_cache_instance = None

def get_cache_instance() -> 'OpenAICache':
    """
    Gibt die Singleton-Instanz des OpenAI-Caches zurück.
    
    Returns:
        OpenAICache-Instanz
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = OpenAICache()
    return _cache_instance

class OpenAICache:
    """
    Cache für OpenAI-API-Aufrufe zur Reduzierung von Kosten und Wartezeiten.
    Verwendet Redis als Backend-Speicher.
    """
    
    def __init__(self, ttl: int = 604800):  # 7 Tage Standard-TTL
        """
        Initialisiert den OpenAI-Cache.
        
        Args:
            ttl: Time-to-Live für Cache-Einträge in Sekunden (Standard: 7 Tage)
        """
        self.ttl = ttl
        self.enabled = True
        logger.info("OpenAI-Cache initialisiert. TTL: {} Sekunden".format(ttl))
    
    def enable(self):
        """Aktiviert den Cache."""
        self.enabled = True
        logger.info("OpenAI-Cache aktiviert")
    
    def disable(self):
        """Deaktiviert den Cache."""
        self.enabled = False
        logger.info("OpenAI-Cache deaktiviert")
    
    def generate_key(self, model: str, messages: List[Dict], temperature: float = 0.7, 
                     max_tokens: Optional[int] = None, **kwargs) -> str:
        """
        Generiert einen Cache-Schlüssel aus den Anfrageparametern.
        
        Args:
            model: OpenAI-Modellname
            messages: Nachrichten-Liste
            temperature: Temperatur für die Antwortgenerierung
            max_tokens: Maximale Token-Anzahl
            **kwargs: Weitere Parameter für die API
            
        Returns:
            Cache-Schlüssel als String
        """
        # Hauptparameter zusammenfassen
        key_data = {
            "model": model,
            "messages": messages,
            "temperature": round(temperature, 2),  # Runden für konsistente Schlüssel
        }
        
        # Optionale Parameter hinzufügen
        if max_tokens is not None:
            key_data["max_tokens"] = max_tokens
        
        # Relevante zusätzliche Parameter
        for param in ["top_p", "frequency_penalty", "presence_penalty", "stop"]:
            if param in kwargs and kwargs[param] is not None:
                key_data[param] = kwargs[param]
        
        # JSON-String erstellen und hashen
        json_str = json.dumps(key_data, sort_keys=True)
        return f"openai:cache:{hashlib.md5(json_str.encode()).hexdigest()}"
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Holt einen Wert aus dem Cache.
        
        Args:
            key: Cache-Schlüssel
            
        Returns:
            Gecachte Antwort oder None, falls nicht im Cache
        """
        if not self.enabled:
            return None
        
        try:
            value = redis_client.get(key, default=None, as_json=True)
            if value:
                logger.debug(f"Cache-Treffer für Schlüssel: {key}")
                return value
        except Exception as e:
            logger.error(f"Fehler beim Lesen aus dem Cache: {str(e)}")
        
        logger.debug(f"Cache-Fehltreffer für Schlüssel: {key}")
        return None
    
    def set(self, key: str, value: Dict[str, Any]) -> bool:
        """
        Speichert einen Wert im Cache.
        
        Args:
            key: Cache-Schlüssel
            value: Zu cachender Wert
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        if not self.enabled:
            return False
        
        try:
            # Wir fügen einen Zeitstempel hinzu, um das Caching-Datum zu verfolgen
            value["_cached_at"] = int(time.time())
            result = redis_client.set(key, value, ex=self.ttl)
            if result:
                logger.debug(f"Wert erfolgreich gecached für Schlüssel: {key}")
            return result
        except Exception as e:
            logger.error(f"Fehler beim Schreiben in den Cache: {str(e)}")
            return False
    
    def invalidate(self, key: str) -> bool:
        """
        Ungültigmacht einen Cache-Eintrag.
        
        Args:
            key: Cache-Schlüssel
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        try:
            result = redis_client.delete(key)
            if result:
                logger.debug(f"Cache-Eintrag ungültig gemacht für Schlüssel: {key}")
            return result
        except Exception as e:
            logger.error(f"Fehler beim Löschen aus dem Cache: {str(e)}")
            return False
    
    def clear(self) -> bool:
        """
        Löscht alle Cache-Einträge mit dem Präfix 'openai:cache:'.
        
        Returns:
            True bei Erfolg, False bei Fehler
        """
        try:
            client = redis_client.get_client()
            keys = client.keys("openai:cache:*")
            if keys:
                client.delete(*keys)
                logger.info(f"{len(keys)} Cache-Einträge gelöscht")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Löschen aller Cache-Einträge: {str(e)}")
            return False 