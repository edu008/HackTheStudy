"""
Task-Dispatcher für die Kommunikation mit dem Worker-Container.
Sendet Tasks an den Worker über Celery und verfolgt ihren Status.
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional, Union, List, Tuple
from celery import Celery
import redis as redis_lib

from .task_definitions import UploadTask, APIRequestTask

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Redis-Client konfigurieren
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
redis_client = redis_lib.from_url(redis_url)

# Celery-Client zum Senden von Tasks an den Worker
celery_app = Celery('api', broker=redis_url, backend=redis_url)

def dispatch_task(task_type: str, *args, **kwargs) -> Dict[str, Any]:
    """
    Sendet einen Task an den Worker-Container.
    
    Args:
        task_type: Art des Tasks ('process_upload' oder 'process_api_request')
        *args, **kwargs: Argumente für den spezifischen Task-Typ
    
    Returns:
        Dict mit Status und Task-ID
    """
    try:
        if task_type == 'process_upload':
            return _dispatch_upload_task(*args, **kwargs)
        elif task_type == 'process_api_request':
            return _dispatch_api_request_task(*args, **kwargs)
        else:
            raise ValueError(f"Unbekannter Task-Typ: {task_type}")
    except Exception as e:
        logger.error(f"Fehler beim Dispatchen des Tasks {task_type}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "task_type": task_type
        }

def _dispatch_upload_task(session_id: str, files_data: List[Tuple[str, str]], user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Sendet einen Upload-Verarbeitungs-Task an den Worker.
    
    Args:
        session_id: ID der Upload-Session
        files_data: Liste von Tupeln mit Dateinamen und -inhalt (als Hex)
        user_id: ID des Benutzers, falls angemeldet
    
    Returns:
        Dict mit Status und Task-ID
    """
    # Task-Objekt erstellen
    task = UploadTask(session_id, files_data, user_id)
    
    # Für große Datensätze: Speichere Dateidaten in Redis
    redis_client.set(
        f"upload_files_data:{session_id}", 
        json.dumps(files_data),
        ex=3600  # 1 Stunde Gültigkeit
    )
    
    # Task an Worker senden
    celery_task = celery_app.send_task(
        'process_upload',
        args=[session_id, files_data, user_id],
        kwargs={}
    )
    
    # Task-ID in Redis speichern
    redis_client.set(f"task_id:{session_id}", celery_task.id, ex=3600)
    
    logger.info(f"Upload-Task für Session {session_id} gesendet, Task-ID: {celery_task.id}")
    
    return {
        "success": True,
        "task_id": celery_task.id,
        "session_id": session_id
    }

def _dispatch_api_request_task(endpoint: str, method: str, payload: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Sendet einen API-Anfragen-Task an den Worker.
    
    Args:
        endpoint: Der API-Endpunkt, der aufgerufen werden soll
        method: Die HTTP-Methode (GET, POST, etc.)
        payload: Die Anfragedaten (optional)
        user_id: ID des anfragenden Benutzers (optional)
    
    Returns:
        Dict mit Status und Task-ID
    """
    # Task-Objekt erstellen
    task = APIRequestTask(endpoint, method, payload, user_id)
    
    # Task an Worker senden
    celery_task = celery_app.send_task(
        'process_api_request',
        args=[endpoint, method, payload, user_id],
        kwargs={}
    )
    
    logger.info(f"API-Request-Task für {method} {endpoint} gesendet, Task-ID: {celery_task.id}")
    
    return {
        "success": True,
        "task_id": celery_task.id,
        "endpoint": endpoint,
        "method": method
    }

def get_task_status(task_id: str = None, session_id: str = None) -> Dict[str, Any]:
    """
    Prüft den Status eines Tasks.
    
    Args:
        task_id: Die Celery-Task-ID
        session_id: Alternativ kann die Session-ID angegeben werden, 
                    um die zugehörige Task-ID aus Redis zu holen
    
    Returns:
        Dict mit Status-Informationen
    """
    if not task_id and not session_id:
        raise ValueError("Entweder task_id oder session_id muss angegeben werden")
    
    # Falls nur session_id angegeben wurde, versuche die task_id aus Redis zu holen
    if not task_id and session_id:
        task_id = redis_client.get(f"task_id:{session_id}")
        if task_id:
            task_id = task_id.decode('utf-8')
        else:
            return {
                "success": False,
                "error": "Keine Task-ID für diese Session gefunden",
                "session_id": session_id
            }
    
    # Task-Status über Celery abfragen
    task_result = celery_app.AsyncResult(task_id)
    
    status = {
        "task_id": task_id,
        "status": task_result.status,
        "success": task_result.successful() if task_result.ready() else None,
        "ready": task_result.ready()
    }
    
    # Falls ein Session-ID angegeben wurde, füge weitere Informationen hinzu
    if session_id:
        status["session_id"] = session_id
        
        # Fortschritt aus Redis holen
        progress = redis_client.get(f"progress_percent:{session_id}")
        progress_info = redis_client.get(f"progress:{session_id}")
        processing_status = redis_client.get(f"processing_status:{session_id}")
        error_details = redis_client.get(f"error_details:{session_id}")
        
        if progress:
            status["progress_percent"] = int(progress.decode('utf-8'))
        
        if progress_info:
            try:
                status["progress_info"] = json.loads(progress_info.decode('utf-8'))
            except json.JSONDecodeError:
                status["progress_info"] = progress_info.decode('utf-8')
        
        if processing_status:
            status["processing_status"] = processing_status.decode('utf-8')
        
        if error_details:
            try:
                status["error_details"] = json.loads(error_details.decode('utf-8'))
            except json.JSONDecodeError:
                status["error_details"] = error_details.decode('utf-8')
    
    return status 