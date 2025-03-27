"""
Upload-Funktionalität für das Backend - WRAPPER
---------------------------------------------

WARNUNG: Diese Datei wird aus Gründen der Abwärtskompatibilität beibehalten.
Für neue Implementierungen verwenden Sie bitte das Modul `api.uploads`.

Diese Datei importiert alle nötigen Funktionen aus dem neuen modularen Upload-Modul,
um Abwärtskompatibilität mit bestehendem Code zu gewährleisten.
"""

# Importiere alle öffentlichen Komponenten aus dem neuen modularen System
from api.uploads import *

# Logger, der Verwendung der alten API dokumentiert
import logging
logger = logging.getLogger(__name__)
logger.warning(
    "Die Datei upload.py wird verwendet, die aus Gründen der Abwärtskompatibilität beibehalten wird. "
    "Bitte verwenden Sie für neue Implementierungen das api.uploads-Modul."
)

"""
Implementierung der Upload-Verarbeitungslogik für den Worker.
"""
import os
import logging
import json
import traceback
from typing import Dict, List, Any, Optional, Tuple, Union

from redis_utils.client import get_redis_client
from redis_utils.utils import safe_redis_set, safe_redis_get
from utils.text_extraction import extract_text_from_file
from utils.text_processing import clean_and_normalize_text
from utils.language import detect_language
from utils.topic_extraction import extract_topics
from utils.ai_analysis import generate_content_structure

def process_upload_files(session_id: str, 
                        files_data: List[Tuple[str, str]], 
                        user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Verarbeitet hochgeladene Dateien für den Upload-Task.
    
    Args:
        session_id: ID der Upload-Session
        files_data: Liste von Tupeln mit Dateinamen und -inhalt (als Hex)
        user_id: ID des Benutzers, falls angemeldet
    
    Returns:
        Dict mit Ergebnissen der Verarbeitung
    """
    logger.info(f"Upload-Verarbeitung für Session {session_id} mit {len(files_data)} Dateien gestartet")
    
    redis_client = get_redis_client()
    results = {
        "session_id": session_id,
        "user_id": user_id,
        "files_count": len(files_data),
        "processed_files": [],
        "success": False,
        "errors": []
    }
    
    try:
        # Fortschritt initialisieren
        safe_redis_set(f"processing_status:{session_id}", "extracting_text")
        safe_redis_set(f"progress_percent:{session_id}", "5")
        
        all_extracted_text = ""
        processed_files = []
        
        # Extrahiere Text aus allen Dateien
        for idx, (filename, file_content) in enumerate(files_data):
            try:
                # Fortschritt aktualisieren
                progress_pct = int(5 + (idx / len(files_data)) * 40)
                safe_redis_set(f"progress_percent:{session_id}", str(progress_pct))
                safe_redis_set(f"progress:{session_id}", json.dumps({
                    "current_file": filename,
                    "current_step": "text_extraction",
                    "files_processed": idx,
                    "total_files": len(files_data)
                }))
                
                # Text extrahieren
                extracted_text = extract_text_from_file(filename, file_content)
                cleaned_text = clean_and_normalize_text(extracted_text)
                
                # Metadaten erfassen
                file_info = {
                    "filename": filename,
                    "text_length": len(cleaned_text),
                    "success": True
                }
                
                # Füge zum Gesamttext hinzu
                all_extracted_text += f"\n\n--- DATEI: {filename} ---\n\n{cleaned_text}"
                processed_files.append(file_info)
                
                logger.info(f"Text erfolgreich aus Datei {filename} extrahiert ({len(cleaned_text)} Zeichen)")
            
            except Exception as e:
                error_msg = f"Fehler bei Textextraktion aus {filename}: {str(e)}"
                logger.error(error_msg)
                logger.error(traceback.format_exc())
                
                results["errors"].append({
                    "file": filename,
                    "error": str(e),
                    "step": "text_extraction"
                })
                
                # Füge Datei mit Fehler hinzu
                processed_files.append({
                    "filename": filename,
                    "success": False,
                    "error": str(e)
                })
        
        # Status aktualisieren
        results["processed_files"] = processed_files
        safe_redis_set(f"processing_status:{session_id}", "analyzing_content")
        safe_redis_set(f"progress_percent:{session_id}", "50")
        
        # Wenn kein Text extrahiert wurde, Fehler zurückgeben
        if not all_extracted_text.strip():
            error_msg = "Keine Textinhalte konnten aus den Dateien extrahiert werden"
            logger.error(error_msg)
            results["errors"].append({
                "error": error_msg,
                "step": "text_validation"
            })
            
            safe_redis_set(f"processing_status:{session_id}", "failed")
            safe_redis_set(f"error_details:{session_id}", json.dumps({
                "message": error_msg,
                "error_type": "no_text_extracted"
            }))
            
            return results
        
        # Textanalyse durchführen
        language = detect_language(all_extracted_text)
        topics = extract_topics(all_extracted_text)
        
        # Status aktualisieren
        safe_redis_set(f"processing_status:{session_id}", "generating_content")
        safe_redis_set(f"progress_percent:{session_id}", "70")
        
        # AI-basierte Inhaltsstrukturierung
        content_structure = generate_content_structure(all_extracted_text, language, topics)
        
        # Speichere Ergebnisse in Redis für spätere Nutzung
        safe_redis_set(f"extracted_text:{session_id}", all_extracted_text, ex=86400)  # 24h TTL
        safe_redis_set(f"content_structure:{session_id}", json.dumps(content_structure), ex=86400)
        safe_redis_set(f"processing_status:{session_id}", "completed")
        safe_redis_set(f"progress_percent:{session_id}", "100")
        
        # Ergebnisse zusammenstellen
        results.update({
            "success": True,
            "language": language,
            "topics": topics,
            "content_structure": content_structure,
            "text_length": len(all_extracted_text)
        })
        
        logger.info(f"Upload-Verarbeitung für Session {session_id} erfolgreich abgeschlossen")
        
    except Exception as e:
        error_msg = f"Fehler bei Upload-Verarbeitung für Session {session_id}: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        
        results["errors"].append({
            "error": str(e),
            "step": "general_processing"
        })
        
        # Fehler in Redis speichern
        safe_redis_set(f"processing_status:{session_id}", "failed")
        safe_redis_set(f"error_details:{session_id}", json.dumps({
            "message": str(e),
            "error_type": "processing_error",
            "traceback": traceback.format_exc()
        }))
    
    return results 