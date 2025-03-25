"""
Signal-Handler für den Worker-Microservice
"""
import os
import sys
import signal
import logging
import traceback
import gc
import time

# Logger konfigurieren
logger = logging.getLogger(__name__)

def cleanup_signal_handler(signum, frame):
    """
    Handler für Terminierungssignale (SIGINT, SIGTERM)
    Führt eine geordnete Bereinigung durch.
    
    Args:
        signum: Die Signalnummer
        frame: Der aktuelle Stack-Frame
    """
    # Bestimme, welches Signal empfangen wurde
    signal_name = next((s for s, num in signal.__dict__.items() 
                         if num == signum and s.startswith('SIG')), f"Signal {signum}")
    
    logger.warning(f"Signal {signal_name} empfangen - führe geordnete Bereinigung durch")
    
    try:
        # 1. Versuche, alle offenen Datei-Deskriptoren zu schließen
        try:
            import psutil
            process = psutil.Process(os.getpid())
            open_files = process.open_files()
            
            if open_files:
                logger.info(f"Schließe {len(open_files)} offene Dateien")
                for file in open_files:
                    try:
                        if hasattr(file, 'fd') and file.fd > 2:  # Nicht stdin/stdout/stderr schließen
                            os.close(file.fd)
                    except Exception as file_error:
                        logger.debug(f"Fehler beim Schließen von Datei {file}: {str(file_error)}")
        except ImportError:
            logger.warning("psutil nicht verfügbar - kann offene Dateien nicht automatisch schließen")
        except Exception as e:
            logger.error(f"Fehler beim Schließen offener Dateien: {str(e)}")
        
        # 2. Manuelles Garbage Collection erzwingen
        logger.info("Führe explizite Garbage Collection durch")
        collected = gc.collect()
        logger.info(f"Garbage Collection: {collected} Objekte eingesammelt")
        
        # 3. Redis-Ressourcen freigeben, falls vorhanden
        try:
            from redis import redis_client
            if redis_client is not None:
                logger.info("Schließe Redis-Verbindung")
                redis_client.close()
        except Exception as redis_error:
            logger.error(f"Fehler beim Schließen der Redis-Verbindung: {str(redis_error)}")
        
        # 4. Celery Worker beenden, falls vorhanden
        try:
            from celery.worker import state
            if state.is_active():
                logger.info("Beende Celery Worker")
                state.should_stop = True
                state.should_terminate = True
        except Exception as celery_error:
            logger.error(f"Fehler beim Beenden des Celery Workers: {str(celery_error)}")
        
        # 5. Stelle sicher, dass alle Logs ausgegeben werden
        logging.shutdown()
        
        logger.warning(f"Bereinigung abgeschlossen - beende Prozess mit Exit-Code 0")
    except Exception as e:
        logger.critical(f"Fehler während der Bereinigung: {str(e)}")
        logger.critical(traceback.format_exc())
    
    # Beende den Prozess ohne weitere Verzögerung
    os._exit(0)

def register_signal_handlers():
    """
    Registriert alle benötigten Signal-Handler für den Worker.
    
    Returns:
        bool: True bei Erfolg, False bei Fehler
    """
    try:
        # Registriere Handler für verschiedene Beendigungssignale
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, cleanup_signal_handler)
            
        # Bei Unix-Systemen auch SIGHUP behandeln
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, cleanup_signal_handler)
            
        logger.info("Signal-Handler erfolgreich registriert")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Registrieren der Signal-Handler: {str(e)}")
        return False

def handle_worker_timeout(task_id, task_name, execution_time, traceback=None):
    """
    Erzeugt detaillierte Diagnose-Informationen bei Worker-Timeout (kritisches Problem)
    
    Args:
        task_id: ID der fehlgeschlagenen Task
        task_name: Name der Task-Funktion
        execution_time: Wie lange die Task lief bevor sie abgebrochen wurde
        traceback: Optional der Traceback des Fehlers
        
    Returns:
        dict: Diagnose-Informationen
    """
    try:
        import psutil
        import json
        import socket
        from datetime import datetime
        from redis import get_redis_client, safe_redis_set
        
        # Aktuelle System-Ressourcen
        process = psutil.Process(os.getpid())
        
        # Systemdiagnose sammeln
        diagnostics = {
            "timestamp": datetime.now().isoformat(),
            "task": {
                "id": task_id,
                "name": task_name,
                "execution_time_seconds": execution_time,
                "timeout_threshold": os.environ.get('CELERY_TASK_TIME_LIMIT', '3600')
            },
            "system": {
                "hostname": socket.gethostname(),
                "pid": os.getpid(),
                "memory_usage_percent": process.memory_percent(),
                "cpu_percent": process.cpu_percent(interval=1.0),
                "open_files": len(process.open_files()),
                "connections": len(process.connections()),
                "threads": process.num_threads(),
                "uptime_seconds": time.time() - process.create_time()
            }
        }
        
        # Speicherverbrauch in Detail
        try:
            mem_info = process.memory_full_info()
            diagnostics["system"]["memory_detail"] = {
                "rss": mem_info.rss / (1024 * 1024),  # MB
                "vms": mem_info.vms / (1024 * 1024),  # MB
                "shared": getattr(mem_info, 'shared', 0) / (1024 * 1024),  # MB
                "text": getattr(mem_info, 'text', 0) / (1024 * 1024),  # MB
                "data": getattr(mem_info, 'data', 0) / (1024 * 1024)   # MB
            }
        except Exception as mem_error:
            diagnostics["memory_error"] = str(mem_error)
        
        # Aktuelle Tasks in Redis speichern für Analyse
        try:
            # Speichere Diagnose in Redis für 24 Stunden
            redis_client = get_redis_client()
            safe_redis_set(
                f"worker:timeout:{task_id}", 
                diagnostics,
                ex=86400  # 24 Stunden
            )
            
            # Füge zur Timeout-Liste hinzu
            redis_client.lpush("worker:timeouts", task_id)
            redis_client.ltrim("worker:timeouts", 0, 99)  # Behalte nur die letzten 100
        except Exception as redis_error:
            diagnostics["redis_error"] = str(redis_error)
        
        # Log erzeugen
        logger.error(f"⚠️ KRITISCH: Worker-Timeout bei Task {task_name} (ID: {task_id}) nach {execution_time}s")
        logger.error(f"Diagnose: CPU {diagnostics['system']['cpu_percent']}%, "
                    f"RAM {diagnostics['system']['memory_usage_percent']}%, "
                    f"Threads {diagnostics['system']['threads']}")
        
        # Traceback loggen, falls vorhanden
        if traceback:
            logger.error(f"Traceback für {task_id}:\n{traceback}")
        
        return diagnostics
    except Exception as e:
        logger.error(f"Fehler bei der Timeout-Diagnose: {str(e)}")
        return {
            "error": str(e),
            "task_id": task_id,
            "task_name": task_name
        } 