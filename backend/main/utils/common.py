"""
Allgemeine Hilfsfunktionen für die Anwendung.
"""

import os
import logging
import uuid
import random
import string
import tempfile

logger = logging.getLogger(__name__)

def get_upload_dir(session_id=None):
    """
    Gibt das Verzeichnis zurück, in dem hochgeladene Dateien gespeichert werden.
    Mit verbesserter Fehlerbehandlung und Berechtigungsprüfung.
    
    Args:
        session_id (str, optional): Die Session-ID für ein spezifisches Upload-Verzeichnis
        
    Returns:
        str: Der Pfad zum Upload-Verzeichnis
    """
    # Standardverzeichnis für Uploads
    upload_dir = os.environ.get('UPLOAD_DIR', '/tmp/uploads')
    
    # Überprüfen, ob das Verzeichnis existiert, ansonsten erstellen
    try:
        # Stelle sicher, dass das Hauptverzeichnis existiert
        if not os.path.exists(upload_dir):
            logger.info(f"Upload-Verzeichnis wird erstellt: {upload_dir}")
            os.makedirs(upload_dir, exist_ok=True)
            logger.info(f"Upload-Verzeichnis erfolgreich erstellt: {upload_dir}")
        
        # Überprüfe Schreibrechte für das Hauptverzeichnis
        if not os.access(upload_dir, os.W_OK):
            logger.warning(f"Keine Schreibrechte für Upload-Verzeichnis: {upload_dir}")
            # Fallback auf temporäres Verzeichnis
            temp_dir = tempfile.gettempdir()
            upload_dir = os.path.join(temp_dir, 'uploads')
            logger.info(f"Verwende alternatives Upload-Verzeichnis: {upload_dir}")
            
            # Erstelle das alternative Verzeichnis, falls es nicht existiert
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir, exist_ok=True)
                logger.info(f"Alternatives Upload-Verzeichnis erstellt: {upload_dir}")
        
        # Wenn eine Session-ID angegeben ist, erstelle ein Unterverzeichnis
        if session_id:
            session_dir = os.path.join(upload_dir, f"session_{session_id}")
            
            # Erstelle das Session-Verzeichnis, falls es nicht existiert
            if not os.path.exists(session_dir):
                logger.info(f"Session-Verzeichnis wird erstellt: {session_dir}")
                os.makedirs(session_dir, exist_ok=True)
                logger.info(f"Session-Verzeichnis erfolgreich erstellt: {session_dir}")
            
            # Überprüfe Schreibrechte für das Session-Verzeichnis
            if not os.access(session_dir, os.W_OK):
                logger.warning(f"Keine Schreibrechte für Session-Verzeichnis: {session_dir}")
                # Fallback auf temporäres Verzeichnis
                temp_dir = tempfile.gettempdir()
                session_dir = os.path.join(temp_dir, f"session_{session_id}")
                logger.info(f"Verwende alternatives Session-Verzeichnis: {session_dir}")
                
                # Erstelle das alternative Session-Verzeichnis
                if not os.path.exists(session_dir):
                    os.makedirs(session_dir, exist_ok=True)
                    logger.info(f"Alternatives Session-Verzeichnis erstellt: {session_dir}")
            
            # Verzeichnisberechtigungen explizit loggen
            try:
                stats = os.stat(session_dir)
                logger.info(f"Session-Verzeichnis Berechtigungen: {oct(stats.st_mode)}, Besitzer: {stats.st_uid}")
            except Exception as stat_err:
                logger.warning(f"Konnte Verzeichnisberechtigungen nicht abrufen: {stat_err}")
            
            return session_dir
            
        return upload_dir
    except Exception as e:
        logger.error(f"Fehler beim Erstellen des Upload-Verzeichnisses: {str(e)}", exc_info=True)
        # Fallback auf temporäres Verzeichnis
        temp_dir = tempfile.gettempdir()
        logger.info(f"Verwende temporäres Verzeichnis als Fallback: {temp_dir}")
        
        if session_id:
            fallback_dir = os.path.join(temp_dir, f"session_{session_id}")
            try:
                if not os.path.exists(fallback_dir):
                    os.makedirs(fallback_dir, exist_ok=True)
                    logger.info(f"Fallback-Verzeichnis erstellt: {fallback_dir}")
                return fallback_dir
            except Exception as fallback_err:
                logger.error(f"Auch Fallback-Verzeichnis konnte nicht erstellt werden: {fallback_err}")
                # Letzter Fallback: direkt auf das temporäre Verzeichnis
                return temp_dir
        return temp_dir

def generate_random_id(length=8):
    """
    Generiert eine zufällige ID mit der angegebenen Länge.
    
    Args:
        length (int): Die Länge der zu generierenden ID
        
    Returns:
        str: Eine zufällige ID
    """
    # Verwende UUID4 für bessere Eindeutigkeit
    return str(uuid.uuid4())[:length] 