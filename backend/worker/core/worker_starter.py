#!/usr/bin/env python
"""
Worker-Starter zum Schutz vor billiard-Absturz mit 'invalid file descriptor'-Fehlern.
"""
import os
import sys
import logging
import time
import threading
import subprocess
import signal
import atexit

# Konfiguriere Logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("worker_starter")

# Globale Variablen
restart_worker = False
worker_process = None
stop_event = threading.Event()

def cleanup():
    """Bereinige beim Beenden."""
    global worker_process
    logger.info("Cleanup wird durchgeführt...")
    if worker_process:
        try:
            worker_process.terminate()
            logger.info("Worker-Prozess wurde beendet")
        except Exception as e:
            logger.error(f"Fehler beim Beenden des Worker-Prozesses: {e}")

# Registriere Cleanup-Funktion
atexit.register(cleanup)

def signal_handler(signum, frame):
    """Signal-Handler für SIGTERM und SIGINT."""
    logger.info(f"Signal {signum} empfangen. Beende Worker...")
    global stop_event
    stop_event.set()
    cleanup()
    sys.exit(0)

# Registriere Signal-Handler
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def get_socket_fd_count():
    """Zähle offene Datei-Deskriptoren für den aktuellen Prozess."""
    try:
        fd_path = f"/proc/{os.getpid()}/fd"
        if not os.path.exists(fd_path):
            return "Nicht verfügbar"
        
        fd_count = len(os.listdir(fd_path))
        return fd_count
    except Exception as e:
        return f"Fehler: {e}"

def monitor_worker(worker_process):
    """Überwache den Worker-Prozess und reagiere auf Probleme."""
    global restart_worker
    
    while not stop_event.is_set() and worker_process.poll() is None:
        # Log Ressourcennutzung
        fd_count = get_socket_fd_count()
        logger.info(f"Worker-Überwachung: PID={worker_process.pid}, FDs={fd_count}")
        
        # Prüfe auf stderr-Ausgabe, die auf Probleme hinweist
        line = worker_process.stderr.readline().decode('utf-8', errors='ignore').strip()
        if line and ('invalid file descriptor' in line or 'ResultHandler' in line):
            logger.error(f"Fehler erkannt: {line}")
            logger.error("Worker scheint Probleme mit Datei-Deskriptoren zu haben. Neustart wird geplant.")
            restart_worker = True
            break
            
        # Weniger häufiges Polling, um CPU-Last zu reduzieren
        for _ in range(15):  # Prüfe alle 3 Sekunden
            if stop_event.is_set() or worker_process.poll() is not None:
                break
            time.sleep(0.2)

def start_worker():
    """Starte den Celery-Worker-Prozess."""
    global worker_process
    
    # Worker-Kommando mit verbesserten Redis-Verbindungsparametern
    command = [
        "celery", "-A", "tasks", "worker",
        "--loglevel=INFO",
        "--pool=solo",
        "--concurrency=1",
        "--max-tasks-per-child=10",
        "--max-memory-per-child=512000",
        "--without-heartbeat",
        "--without-gossip",
        "--without-mingle",
        "--broker-connection-timeout=30",
        "--broker-connection-max-retries=10",
        "--broker-connection-retry"
    ]
    
    # Umgebungsvariablen für den Worker
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    env['C_FORCE_ROOT'] = '1'
    env['CELERY_BROKER_CONNECTION_RETRY'] = 'true'
    env['CELERY_BROKER_CONNECTION_TIMEOUT'] = '30'
    env['CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS'] = 'false'
    
    # Starte den Worker-Prozess
    logger.info(f"Starte Worker mit Kommando: {' '.join(command)}")
    worker_process = subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=False,
        bufsize=0
    )
    
    # Starte Stdout-Leser in einem separaten Thread
    def stdout_reader():
        while not stop_event.is_set() and worker_process.poll() is None:
            line = worker_process.stdout.readline()
            if line:
                sys.stdout.buffer.write(line)
                sys.stdout.flush()
    
    stdout_thread = threading.Thread(target=stdout_reader, daemon=True)
    stdout_thread.start()
    
    return worker_process

def main():
    """Hauptfunktion."""
    global restart_worker, worker_process
    
    logger.info("Worker-Starter wurde initialisiert")
    logger.info(f"Aktuelle Umgebungsvariablen: {dict(os.environ)}")
    
    # Setze Socket-Timeout für bessere Stabilität
    import socket
    socket.setdefaulttimeout(300)  # 5 Minuten Timeout
    
    # Patch für Redis Connection Handling 
    try:
        from redis.connection import Connection
        if hasattr(Connection, 'disconnect'):
            original_disconnect = Connection.disconnect
            def patched_disconnect(self):
                try:
                    return original_disconnect(self)
                except Exception as e:
                    logger.warning(f"Redis disconnect error (ignored): {e}")
                    pass
            Connection.disconnect = patched_disconnect
            logger.info("Redis connection handling patched successfully")
    except ImportError:
        logger.warning("Redis module not available for patching")
    
    # Schleife für automatischen Neustart
    while not stop_event.is_set():
        try:
            logger.info("Starte Celery-Worker...")
            worker_process = start_worker()
            restart_worker = False
            
            # Überwache den Worker
            monitor_thread = threading.Thread(
                target=monitor_worker, 
                args=(worker_process,),
                daemon=True
            )
            monitor_thread.start()
            
            # Warte auf Worker-Beendigung
            exit_code = worker_process.wait()
            logger.info(f"Worker-Prozess beendet mit Exit-Code: {exit_code}")
            
            # Prüfe, ob ein Neustart erforderlich ist
            if stop_event.is_set():
                logger.info("Beendigungssignal erkannt. Stoppe Worker-Starter.")
                break
            elif restart_worker or exit_code != 0:
                logger.warning(f"Worker-Neustart erforderlich. Exit-Code: {exit_code}")
                time.sleep(2)  # Kurze Pause vor dem Neustart
            else:
                logger.info("Worker wurde ordnungsgemäß beendet. Beende Worker-Starter.")
                break
                
        except KeyboardInterrupt:
            logger.info("Tastatur-Interrupt erkannt. Beende Worker-Starter.")
            stop_event.set()
            if worker_process:
                worker_process.terminate()
            break
        except Exception as e:
            logger.error(f"Fehler im Worker-Starter: {e}")
            time.sleep(5)  # Pause vor dem Neustart

if __name__ == "__main__":
    main() 