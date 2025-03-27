"""
Cache-Verwaltungsfunktionen für das Admin-Modul.
Enthält Funktionen zur Verwaltung und Überwachung des Redis-Caches.
"""

import logging
from flask import jsonify
from openaicache.openai_wrapper import CachedOpenAI as OpenAICacheManager

# Logger konfigurieren
logger = logging.getLogger(__name__)

def get_cache_stats():
    """
    Gibt Statistiken zum Redis-Cache für OpenAI-API-Anfragen zurück.
    """
    try:
        cache_stats = OpenAICacheManager.get_cache_stats()
        
        return jsonify({
            "success": True,
            "data": cache_stats
        })
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Cache-Statistiken: {str(e)}")
        return jsonify({
            "success": False,
            "error": {"code": "CACHE_ERROR", "message": str(e)}
        }), 500

def clear_cache():
    """
    Löscht den Redis-Cache für OpenAI-API-Anfragen.
    """
    try:
        deleted = OpenAICacheManager.clear_all_cache()
        
        return jsonify({
            "success": True,
            "data": {
                "deleted_entries": deleted,
                "message": f"{deleted} Cache-Einträge wurden gelöscht."
            }
        })
        
    except Exception as e:
        logger.error(f"Fehler beim Löschen des Caches: {str(e)}")
        return jsonify({
            "success": False,
            "error": {"code": "CACHE_ERROR", "message": str(e)}
        }), 500

def get_cache_key(key_pattern, limit=100):
    """
    Ruft Schlüssel aus dem Redis-Cache ab, die einem bestimmten Muster entsprechen.
    
    Args:
        key_pattern: Das Muster für die Schlüssel (z.B. "openai:*")
        limit: Die maximale Anzahl von Schlüsseln, die zurückgegeben werden sollen
        
    Returns:
        dict: Die Schlüssel und ihre Werte
    """
    try:
        keys = OpenAICacheManager.get_cache_keys(key_pattern, limit)
        values = {}
        
        for key in keys:
            value = OpenAICacheManager.get_from_cache(key)
            if value:
                values[key] = value
        
        return jsonify({
            "success": True,
            "data": {
                "keys": keys,
                "values": values,
                "count": len(keys)
            }
        })
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Cache-Schlüssel: {str(e)}")
        return jsonify({
            "success": False,
            "error": {"code": "CACHE_ERROR", "message": str(e)}
        }), 500 