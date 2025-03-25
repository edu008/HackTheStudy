"""
Definitionen der Tasks, die an den Worker-Container gesendet werden.
Diese Definitionen dienen als Vertragsschnittstelle zwischen API und Worker.
"""

from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime

class UploadTask:
    """
    Definition für den Upload-Verarbeitungs-Task.
    
    Attribute:
        session_id (str): ID der Upload-Session
        files_data (List[Tuple[str, str]]): Liste von Tupeln mit Dateinamen und -inhalt (als Hex)
        user_id (Optional[str]): ID des Benutzers, falls angemeldet
    """
    
    def __init__(self, session_id: str, files_data: List[Tuple[str, str]], user_id: Optional[str] = None):
        self.session_id = session_id
        self.files_data = files_data
        self.user_id = user_id
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert die Task-Definition in ein Dictionary für die Übertragung."""
        return {
            'session_id': self.session_id,
            'files_data': self.files_data,
            'user_id': self.user_id
        }

class APIRequestTask:
    """
    Definition für den API-Anfragen-Task.
    
    Attribute:
        endpoint (str): Der API-Endpunkt, der aufgerufen werden soll
        method (str): Die HTTP-Methode (GET, POST, etc.)
        payload (Optional[Dict]): Die Anfragedaten (optional)
        user_id (Optional[str]): ID des anfragenden Benutzers (optional)
    """
    
    def __init__(self, endpoint: str, method: str, payload: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None):
        self.endpoint = endpoint
        self.method = method
        self.payload = payload
        self.user_id = user_id
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert die Task-Definition in ein Dictionary für die Übertragung."""
        return {
            'endpoint': self.endpoint,
            'method': self.method,
            'payload': self.payload,
            'user_id': self.user_id
        }

# Weitere Task-Definitionen können hier hinzugefügt werden 