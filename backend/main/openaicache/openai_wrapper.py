"""
OpenAI Wrapper mit Caching-Funktionalität.
Wrapper-Modul für die zentrale Implementierung in core/openai_integration.py.
"""

import logging
from typing import Any, Dict, List, Optional, Union

# Importiere die zentralen Implementierungen
from core.openai_integration import (OpenAICache, chat_completion, clear_cache,
                                     extract_content_from_response,
                                     get_openai_client as core_get_openai_client)

# Logger konfigurieren
logger = logging.getLogger(__name__)


class CachedOpenAI:
    """
    Wrapper-Klasse für OpenAI-API-Aufrufe mit integriertem Caching.
    Delegiert an die zentrale Implementierung.
    """

    @staticmethod
    def get_client():
        """
        Gibt die OpenAI-Client-Instanz zurück.

        Returns:
            OpenAI: Die Client-Instanz
        """
        return core_get_openai_client()

    @staticmethod
    def chat_completion(model: str, messages: List[Dict],
                        user_id: Optional[str] = None,
                        session_id: Optional[str] = None,
                        function_name: Optional[str] = None,
                        use_cache: bool = True, **kwargs) -> Dict[str, Any]:
        """
        Führt eine OpenAI-Chat-Completion mit Caching durch.

        Args:
            model: OpenAI-Modellname
            messages: Liste von Nachrichten
            user_id: ID des Benutzers für Tracking
            session_id: ID der Sitzung für Tracking
            function_name: Name der Funktion für Tracking
            use_cache: Ob der Cache verwendet werden soll
            **kwargs: Weitere Parameter für die OpenAI-API

        Returns:
            Dict: Die OpenAI-Antwort
        """
        return chat_completion(
            model=model,
            messages=messages,
            user_id=user_id,
            session_id=session_id,
            function_name=function_name,
            use_cache=use_cache,
            **kwargs
        )

    @staticmethod
    def get_completion_text(model: str, messages: List[Dict], **kwargs) -> str:
        """
        Führt eine OpenAI-Chat-Completion durch und gibt nur den Text zurück.

        Args:
            model: OpenAI-Modellname
            messages: Liste von Nachrichten
            **kwargs: Weitere Parameter

        Returns:
            str: Der Antworttext
        """
        response = CachedOpenAI.chat_completion(model, messages, **kwargs)
        return extract_content_from_response(response)

    @staticmethod
    def clear_cache(pattern: str = "openai:chat:*") -> int:
        """
        Löscht Einträge aus dem Cache.

        Args:
            pattern: Redis-Suchmuster

        Returns:
            int: Anzahl der gelöschten Einträge
        """
        return clear_cache(pattern)

    @staticmethod
    def clear_all_cache() -> int:
        """
        Löscht alle Cache-Einträge.

        Returns:
            int: Anzahl der gelöschten Einträge
        """
        return CachedOpenAI.clear_cache()

    @staticmethod
    def get_cache_stats() -> Dict[str, Any]:
        """
        Gibt Statistiken über den Cache zurück.

        Returns:
            Dict: Cache-Statistiken
        """
        cache = OpenAICache()
        return cache.get_stats()

# Für einfachen Import - Exportiere die get_openai_client-Funktion der zentralen Implementierung
get_openai_client = core_get_openai_client
