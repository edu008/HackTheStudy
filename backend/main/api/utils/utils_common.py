"""
Gemeinsame Hilfsfunktionen für verschiedene API-Module.
Diese Funktionen sind allgemein nützlich und gehören nicht zu den anderen spezialisierten Modulen.
"""

import logging
import json
import time
import hashlib
import uuid
import re
from core.redis_client import redis_client

logger = logging.getLogger(__name__)

def generate_unique_id():
    """
    Generiert eine eindeutige ID.
    
    Returns:
        str: Eine eindeutige ID
    """
    return str(uuid.uuid4())

def generate_hash(content):
    """
    Generiert einen Hash für einen Inhalt.
    
    Args:
        content: Der Inhalt, für den ein Hash generiert werden soll
        
    Returns:
        str: Der generierte Hash
    """
    if isinstance(content, str):
        content = content.encode('utf-8')
    return hashlib.md5(content).hexdigest()

def store_in_redis(key, value, expiration=86400):
    """
    Speichert einen Wert in Redis.
    
    Args:
        key: Der Schlüssel
        value: Der zu speichernde Wert
        expiration: Die Ablaufzeit in Sekunden (Standard: 24 Stunden)
        
    Returns:
        bool: True, wenn erfolgreich, sonst False
    """
    try:
        # Konvertiere den Wert in einen String, falls nötig
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        elif not isinstance(value, str):
            value = str(value)
            
        # Speichere in Redis
        redis_client.set(key, value, ex=expiration)
        return True
    except Exception as e:
        logger.error(f"Fehler beim Speichern in Redis: {str(e)}")
        return False

def get_from_redis(key, as_json=False):
    """
    Holt einen Wert aus Redis.
    
    Args:
        key: Der Schlüssel
        as_json: Ob der Wert als JSON geparst werden soll
        
    Returns:
        Der Wert aus Redis oder None, wenn nicht gefunden
    """
    try:
        value = redis_client.get(key)
        
        if value is None:
            return None
            
        # Konvertiere von Bytes zu String
        value = value.decode('utf-8')
        
        # Parse als JSON, falls gewünscht
        if as_json:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.warning(f"Konnte Wert für Schlüssel {key} nicht als JSON parsen")
                return value
                
        return value
    except Exception as e:
        logger.error(f"Fehler beim Abrufen aus Redis: {str(e)}")
        return None

def format_timestamp(timestamp=None, format_string="%Y-%m-%d %H:%M:%S"):
    """
    Formatiert einen Zeitstempel als lesbaren String.
    
    Args:
        timestamp: Der Zeitstempel (Unix-Zeit) oder None für die aktuelle Zeit
        format_string: Das Format für den String
        
    Returns:
        str: Der formatierte Zeitstempel
    """
    from datetime import datetime
    
    if timestamp is None:
        timestamp = time.time()
        
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime(format_string)

def sanitize_filename(filename):
    """
    Bereinigt einen Dateinamen, um ungültige Zeichen zu entfernen.
    
    Args:
        filename: Der zu bereinigende Dateiname
        
    Returns:
        str: Der bereinigte Dateiname
    """
    # Entferne ungültige Zeichen für Dateinamen
    sanitized = re.sub(r'[\\/*?:"<>|]', '', filename)
    
    # Entferne führende/abschließende Leerzeichen und Punkte
    sanitized = sanitized.strip('. ')
    
    # Falls der Name leer ist, verwende einen Standardnamen
    if not sanitized:
        sanitized = "unnamed_file"
        
    return sanitized

def truncate_text(text, max_length=100, add_ellipsis=True):
    """
    Kürzt einen Text auf eine bestimmte Länge.
    
    Args:
        text: Der zu kürzende Text
        max_length: Die maximale Länge
        add_ellipsis: Ob Auslassungspunkte hinzugefügt werden sollen
        
    Returns:
        str: Der gekürzte Text
    """
    if not text or len(text) <= max_length:
        return text
        
    truncated = text[:max_length]
    if add_ellipsis:
        truncated += "..."
        
    return truncated

def parse_bool(value):
    """
    Parst einen booleschen Wert aus verschiedenen Formaten.
    
    Args:
        value: Der zu parsende Wert (String, Boolean, Integer)
        
    Returns:
        bool: Der geparste boolesche Wert
    """
    if isinstance(value, bool):
        return value
        
    if isinstance(value, int):
        return value != 0
        
    if isinstance(value, str):
        value = value.lower()
        if value in ('true', 'yes', 'y', '1', 'on'):
            return True
        if value in ('false', 'no', 'n', '0', 'off'):
            return False
            
    return False 