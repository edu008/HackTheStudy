"""
Direkte Dateihandhabung ohne Textextraktion
---------------------------------------

Dieses Modul stellt Funktionen für die direkte Handhabung von Dateien bereit,
ohne sie in Text umzuwandeln.
"""

import os
import logging
import tempfile
import base64
import time
import json
from typing import BinaryIO, Union, Dict, Any, Optional, Tuple
from openai import OpenAI
import traceback

logger = logging.getLogger(__name__)

def prepare_file_for_openai(file_content: bytes, file_name: str = None) -> str:
    """
    Bereitet eine Datei für die Verwendung mit OpenAI vor, indem sie temporär gespeichert wird.
    
    Args:
        file_content (bytes): Der binäre Inhalt der Datei
        file_name (str, optional): Der Dateiname (für die Ermittlung der Dateiendung)
        
    Returns:
        str: Pfad zur temporären Datei
    """
    # Dateiendung bestimmen
    file_extension = ".pdf"  # Standard-Dateiendung
    if file_name and '.' in file_name:
        file_extension = os.path.splitext(file_name)[1].lower()
    
    # Temporäre Datei erstellen
    temp_file = tempfile.NamedTemporaryFile(suffix=file_extension, delete=False)
    temp_file_path = temp_file.name
    
    try:
        # Dateiinhalt in temporäre Datei schreiben
        with open(temp_file_path, 'wb') as f:
            f.write(file_content)
        
        logger.info(f"Temporäre Datei erstellt: {temp_file_path} ({len(file_content)} Bytes)")
        return temp_file_path
        
    except Exception as e:
        # Bei einem Fehler die temporäre Datei löschen und Exception werfen
        logger.error(f"Fehler beim Erstellen der temporären Datei: {str(e)}")
        try:
            os.unlink(temp_file_path)
        except:
            pass
        raise

def cleanup_temp_file(file_path: str) -> bool:
    """
    Löscht eine temporäre Datei.
    
    Args:
        file_path (str): Pfad zur temporären Datei
        
    Returns:
        bool: True, wenn die Datei erfolgreich gelöscht wurde, sonst False
    """
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
            logger.info(f"Temporäre Datei gelöscht: {file_path}")
            return True
        else:
            logger.warning(f"Temporäre Datei existiert nicht: {file_path}")
            return False
    except Exception as e:
        logger.error(f"Fehler beim Löschen der temporären Datei: {str(e)}")
        return False

def get_file_info(file_path: str) -> Dict[str, Any]:
    """
    Ermittelt Informationen über eine Datei.
    
    Args:
        file_path (str): Der Pfad zur Datei
        
    Returns:
        Dict[str, Any]: Informationen über die Datei
    """
    try:
        stat = os.stat(file_path)
        return {
            'size': stat.st_size,
            'created': stat.st_ctime,
            'modified': stat.st_mtime,
            'extension': os.path.splitext(file_path)[1].lower()
        }
    except Exception as e:
        logger.error(f"Fehler beim Ermitteln der Dateiinformationen für {file_path}: {str(e)}")
        raise

def extract_text_from_temp_file(file_path: str) -> str:
    """
    Extrahiert Text aus einer temporären Datei.
    
    Args:
        file_path (str): Der Pfad zur temporären Datei
        
    Returns:
        str: Der extrahierte Text
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Fehler beim Lesen der temporären Datei {file_path}: {str(e)}")
        raise

def save_file_for_processing(file_content: bytes, file_name: str) -> str:
    """
    Speichert eine Datei temporär für die Verarbeitung.
    
    Args:
        file_content: Binäre Dateiinhalte
        file_name: Name der Originaldatei
        
    Returns:
        Pfad zur temporären Datei
    """
    logger.info("="*50)
    logger.info(f"TEMPORÄRE DATEI WIRD ERSTELLT: {file_name}")
    
    try:
        # Dateiendung beibehalten
        file_extension = os.path.splitext(file_name)[1]
        
        # Temporäre Datei erstellen
        temp_dir = tempfile.gettempdir()
        temp_file_fd, temp_file_path = tempfile.mkstemp(suffix=file_extension, dir=temp_dir)
        
        # Datei schreiben und schließen
        with os.fdopen(temp_file_fd, 'wb') as temp_file:
            temp_file.write(file_content)
        
        logger.info(f"Temporäre Datei erstellt: {temp_file_path} ({len(file_content)} Bytes)")
        logger.info(f"Datei '{file_name}' wurde erfolgreich für die Verarbeitung vorbereitet")
        return temp_file_path
        
    except Exception as e:
        logger.error(f"Fehler beim Erstellen der temporären Datei: {e}")
        logger.error(traceback.format_exc())
        raise

def send_file_to_openai(file_content: bytes, file_name: str) -> Tuple[str, int]:
    """
    Bereitet eine Datei für OpenAI vor und extrahiert den Text.
    Je nach Dateityp wird der Inhalt unterschiedlich verarbeitet.
    
    Args:
        file_content: Binäre Dateiinhalte
        file_name: Name der Originaldatei
        
    Returns:
        Tuple mit (extrahiertem Text, Anzahl der Tokens)
    """
    logger.info("="*50)
    logger.info(f"BEREITE DATEI FÜR OpenAI VOR: {file_name}")
    
    temp_file_path = None
    extracted_text = ""
    tokens = 0
    
    try:
        # Speichere die Datei temporär
        temp_file_path = save_file_for_processing(file_content, file_name)
        file_extension = os.path.splitext(file_name)[1].lower()
        
        # Text je nach Dateityp extrahieren
        if file_extension == '.pdf':
            from utils.text_extraction import extract_text_from_pdf
            extracted_text, chunks = extract_text_from_pdf(temp_file_path)
            logger.info(f"Text aus PDF extrahiert: {len(extracted_text)} Zeichen, {len(chunks)} Chunks")
            
        elif file_extension == '.docx':
            from utils.text_extraction import extract_text_from_docx
            extracted_text, chunks = extract_text_from_docx(temp_file_path)
            logger.info(f"Text aus DOCX extrahiert: {len(extracted_text)} Zeichen, {len(chunks)} Chunks")
            
        elif file_extension == '.txt':
            # TXT-Dateien direkt lesen
            with open(temp_file_path, 'r', encoding='utf-8', errors='replace') as f:
                extracted_text = f.read()
            logger.info(f"Text aus TXT gelesen: {len(extracted_text)} Zeichen")
            
        else:
            # Bei unbekanntem Dateityp: Versuche direkt zu dekodieren
            extracted_text = file_content.decode('utf-8', errors='replace')
            logger.info(f"Binärdaten direkt dekodiert: {len(extracted_text)} Zeichen")
        
        # Textlänge begrenzen (OpenAI-Limit)
        max_chars = 250000  # ca. 62.500 Tokens
        if len(extracted_text) > max_chars:
            logger.warning(f"Text zu lang ({len(extracted_text)} Zeichen), wird auf {max_chars} Zeichen begrenzt")
            extracted_text = extracted_text[:max_chars] + "\n\n[Text wurde aufgrund der Längenbeschränkung gekürzt]"
        
        # Grobe Token-Schätzung (4 Zeichen ≈ 1 Token)
        tokens = len(extracted_text) // 4
        logger.info(f"Geschätzte Token-Anzahl: ~{tokens}")
        logger.info("="*50)
        
        return extracted_text, tokens
        
    except Exception as e:
        logger.error(f"Fehler bei der Dateiverarbeitung für OpenAI: {e}")
        logger.error(traceback.format_exc())
        return "", 0
        
    finally:
        # Temporäre Datei aufräumen
        if temp_file_path:
            cleanup_temp_file(temp_file_path)

# Exportierte Funktionen
__all__ = ['prepare_file_for_openai', 'cleanup_temp_file', 'get_file_info', 'save_file_for_processing', 'extract_text_from_temp_file', 'send_file_to_openai'] 