"""
OpenAI Wrapper mit Caching-Funktionalität.
Stellt eine einheitliche Schnittstelle für OpenAI-API-Aufrufe bereit.
"""

import logging
import json
import os
import time
from typing import Dict, List, Any, Optional, Union

# Importiere vorhandene Funktionalität aus dem openai_client
from api.openai_client import (
    get_openai_client, 
    chat_completion_with_backoff,
    generate_cache_key,
    get_cached_response,
    cache_response,
    extract_content_from_response,
    calculate_cost,
    invalidate_cache
)

# Logger konfigurieren
logger = logging.getLogger(__name__)

class CachedOpenAI:
    """
    Wrapper-Klasse für OpenAI-API-Aufrufe mit integriertem Caching.
    Stellt eine einheitliche Schnittstelle für verschiedene Teile der Anwendung bereit.
    """
    
    @staticmethod
    def get_client():
        """
        Gibt die OpenAI-Client-Instanz zurück.
        
        Returns:
            OpenAI: Die Client-Instanz
        """
        return get_openai_client()
    
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
        return chat_completion_with_backoff(
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
        return invalidate_cache(pattern)
    
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
        from core.redis_client import redis_client
        
        try:
            client = redis_client.get_client()
            keys = client.keys("openai:chat:*")
            total_size = 0
            
            # Stichprobe für die durchschnittliche Größe
            sample_size = min(len(keys), 10)
            if sample_size > 0:
                sample_keys = keys[:sample_size]
                for key in sample_keys:
                    size = len(client.get(key) or b'')
                    total_size += size
                
                avg_size = total_size / sample_size
                estimated_total_size = avg_size * len(keys)
            else:
                avg_size = 0
                estimated_total_size = 0
            
            return {
                "total_entries": len(keys),
                "sample_size": sample_size,
                "avg_entry_size_bytes": int(avg_size),
                "estimated_total_size_kb": int(estimated_total_size / 1024),
                "estimated_total_size_mb": round(estimated_total_size / (1024 * 1024), 2)
            }
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Cache-Statistiken: {e}")
            return {
                "error": str(e),
                "total_entries": 0
            }

# Für einfachen Import
def get_openai_client():
    """
    Gibt die OpenAI-Client-Instanz zurück.
    
    Returns:
        OpenAI: Die Client-Instanz
    """
    return CachedOpenAI.get_client() 