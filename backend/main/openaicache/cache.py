"""
OpenAI Cache-Implementierung für das Caching von API-Aufrufen.
Delegiert an die zentrale Implementation in core/openai_integration.py.
Redis wird exklusiv für diesen OpenAI-Cache verwendet.
"""

import logging
from typing import Any, Dict, List, Optional, Union

# Importiere die zentrale Implementierung
from core.openai_integration import OpenAICache as CentralOpenAICache

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
    # Nutze global für die Singleton-Instanz
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = OpenAICache()
    return _cache_instance


class OpenAICache:
    """
    Cache für OpenAI-API-Aufrufe zur Reduzierung von Kosten und Wartezeiten.
    Delegiert an die zentrale Implementation.
    Redis wird exklusiv für diesen Cache verwendet.
    """

    def __init__(self, ttl: int = 604800):  # 7 Tage Standard-TTL
        """
        Initialisiert den OpenAI-Cache.

        Args:
            ttl: Time-to-Live für Cache-Einträge in Sekunden (Standard: 7 Tage)
        """
        self.ttl = ttl
        self._central_cache = CentralOpenAICache()
        self._central_cache.ttl = ttl
        logger.info("OpenAI-Cache-Wrapper initialisiert. TTL: %s Sekunden", ttl)
        logger.info("Redis wird exklusiv für den OpenAI-Cache verwendet")

    def enable(self):
        """Aktiviert den Cache."""
        self._central_cache.enable()

    def disable(self):
        """Deaktiviert den Cache."""
        self._central_cache.disable()

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
        # Füge temperature und max_tokens zu kwargs hinzu, wenn sie angegeben wurden
        if temperature is not None:
            kwargs['temperature'] = temperature
        if max_tokens is not None:
            kwargs['max_tokens'] = max_tokens

        return self._central_cache.generate_key(model, messages, **kwargs)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Holt einen Wert aus dem Cache.

        Args:
            key: Cache-Schlüssel

        Returns:
            Gecachte Antwort oder None, falls nicht im Cache
        """
        return self._central_cache.get(key)

    def set(self, key: str, value: Dict[str, Any]) -> bool:
        """
        Speichert einen Wert im Cache.

        Args:
            key: Cache-Schlüssel
            value: Zu cachender Wert

        Returns:
            True bei Erfolg, False bei Fehler
        """
        return self._central_cache.set(key, value)

    def invalidate(self, key: str) -> bool:
        """
        Ungültigmacht einen Cache-Eintrag.

        Args:
            key: Cache-Schlüssel

        Returns:
            True bei Erfolg, False bei Fehler
        """
        return self._central_cache.invalidate(key)

    def clear(self) -> bool:
        """
        Löscht alle Cache-Einträge mit dem Präfix 'openai:cache:'.

        Returns:
            True bei Erfolg, False bei Fehler
        """
        count = self._central_cache.clear("openai:cache:*")
        return count > 0
