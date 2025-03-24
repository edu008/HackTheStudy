#!/usr/bin/env python
"""
Watchdog-Service für Celery-Worker
Überwacht Celery-Worker und erkennt defekte oder hängende Worker. Führt automatische Neustarts durch.
"""
import os
import sys
import time
import logging
import signal
import psutil
import subprocess
import threading
import json
import redis
from datetime import datetime, timedelta

# Konfiguriere Logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("watchdog")

# Konfiguration und Umgebungsvariablen
RUN_MODE = os.environ.get('RUN_MODE', 'watchdog')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
LOG_PREFIX = os.environ.get('LOG_PREFIX', '[WATCHDOG] ')
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CHECK_INTERVAL = int(os.environ.get('WATCHDOG_CHECK_INTERVAL', '60'))  # Sekunden
MAX_RESTART_ATTEMPTS = 3  # Maximale Anzahl von Neustarts pro Tag
RESTART_COOLDOWN = 300  # Sekunden bis zum nächsten Neustart nach einem Fehler

# Speicher für Neustart-Statistiken
restart_stats = {
    'last_restart': None,
    'restart_count': 0,
    'restart_attempts': 0,
    'day_restarts': 0,
    'day_start': datetime.now().date()
}

# Redis-Client initialisieren
try:
    redis_client = redis.from_url(REDIS_URL)
    logger.info(f"Redis-Verbindung hergestellt zu {REDIS_URL}")
except Exception as e:
    logger.error(f"Konnte keine Verbindung zu Redis herstellen: {e}")
    redis_client = None

def check_celery_workers():
    """
    Überprüft den Zustand aller Celery-Worker-Prozesse.
    
    Returns:
        dict: Informationen über gesunde und problematische Worker
    """
    results = {
        'healthy': [],
        'problematic': []
    }
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            proc_info = proc.info
            cmdline = proc_info.get('cmdline', [])
            
            # Identifiziere Celery-Worker
            is_celery = False
            for arg in cmdline:
                if isinstance(arg, str) and 'celery' in arg and 'worker' in str(arg):
                    is_celery = True
                    break
            
            if is_celery:
                # Sammle Informationen über den Worker
                pid = proc_info['pid']
                create_time = datetime.fromtimestamp(proc_info['create_time'])
                runtime = datetime.now() - create_time
                
                # CPU und Speichernutzung
                process = psutil.Process(pid)
                cpu_percent = process.cpu_percent(interval=0.5)
                memory_percent = process.memory_percent()
                
                # Sammle Informationen über Datei-Deskriptoren
                try:
                    open_files = len(process.open_files())
                    connections = len(process.connections())
                except Exception as e:
                    logger.warning(f"Konnte Datei-Deskriptoren für PID {pid} nicht zählen: {e}")
                    open_files = -1
                    connections = -1
                
                # Erstelle Worker-Info
                worker_info = {
                    'pid': pid,
                    'create_time': create_time.isoformat(),
                    'runtime': str(runtime),
                    'runtime_seconds': runtime.total_seconds(),
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory_percent,
                    'open_files': open_files,
                    'connections': connections
                }
                
                # Prüfe Worker-Gesundheit
                is_problematic = False
                problems = []
                
                # Länger laufende Worker mit niedrigem CPU-Verbrauch können auf Probleme hindeuten
                if runtime.total_seconds() > 3600 and cpu_percent < 0.5:  # > 1 Stunde und < 0.5% CPU
                    is_problematic = True
                    problems.append("Niedriger CPU-Verbrauch bei langer Laufzeit")
                
                # Sehr hoher CPU-Verbrauch könnte auf Probleme hindeuten
                if cpu_percent > 95:
                    is_problematic = True
                    problems.append("Extrem hohe CPU-Auslastung")
                
                # Hohe Anzahl an Datei-Deskriptoren
                if open_files > 200 or connections > 50:
                    is_problematic = True
                    problems.append(f"Hohe Anzahl offener Deskriptoren: Files={open_files}, Connections={connections}")
                
                # Speichere die Probleme, wenn vorhanden
                if is_problematic:
                    worker_info['problems'] = problems
                    results['problematic'].append(worker_info)
                else:
                    results['healthy'].append(worker_info)
        
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            logger.debug(f"Konnte Prozess nicht überprüfen: {e}")
    
    return results

def check_redis_health():
    """
    Überprüft den Zustand von Redis und identifiziert mögliche Worker-Probleme.
    
    Returns:
        dict: Informationen über den Redis-Zustand
    """
    result = {
        'status': 'unknown',
        'problems': []
    }
    
    if not redis_client:
        result['status'] = 'error'
        result['problems'].append('Redis-Client nicht verfügbar')
        return result
    
    try:
        # Redis-Info abrufen
        info = redis_client.info()
        result['status'] = 'ok'
        result['clients'] = info.get('clients', {}).get('connected_clients', 0)
        result['used_memory'] = info.get('memory', {}).get('used_memory_human', 'unbekannt')
        
        # Prüfe auf Worker-spezifische Probleme
        try:
            # Suche nach ResultHandler-Absturz-Markierungen in Redis
            keys = redis_client.keys('celery:*')
            if len(keys) > 1000:
                result['problems'].append(f'Hohe Anzahl an Celery-Keys: {len(keys)}')
            
            # Suche nach Task-Keys
            task_keys = redis_client.keys('celery-task-meta-*')
            if len(task_keys) > 500:
                result['problems'].append(f'Hohe Anzahl an Task-Meta-Keys: {len(task_keys)}')
            
            # Prüfe auf lange inaktive aber nicht abgeschlossene Tasks
            now = datetime.now()
            stale_tasks = 0
            
            for key in redis_client.scan_iter('celery-task-meta-*', count=100):
                try:
                    task_data = redis_client.get(key)
                    if task_data:
                        task = json.loads(task_data)
                        if task.get('status') not in ('SUCCESS', 'FAILURE'):
                            # Prüfe, ob dieser Task veraltet ist
                            if 'date_done' in task:
                                date_str = task['date_done']
                                try:
                                    date_done = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                    if (now - date_done) > timedelta(hours=1):
                                        stale_tasks += 1
                                except (ValueError, TypeError):
                                    pass
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
            
            if stale_tasks > 10:
                result['problems'].append(f'{stale_tasks} veraltete Tasks gefunden')
            
        except Exception as e:
            result['problems'].append(f'Fehler bei der Task-Analyse: {str(e)}')
        
        return result
        
    except Exception as e:
        result['status'] = 'error'
        result['problems'].append(f'Redis-Fehler: {str(e)}')
        return result

def should_restart_workers(worker_status, redis_status):
    """
    Entscheidet, ob die Worker neu gestartet werden sollten.
    
    Args:
        worker_status: Ergebnis von check_celery_workers()
        redis_status: Ergebnis von check_redis_health()
        
    Returns:
        tuple: (restart, reason)
    """
    global restart_stats
    
    # Prüfe, ob heute bereits zu viele Neustarts versucht wurden
    today = datetime.now().date()
    if today != restart_stats['day_start']:
        restart_stats['day_start'] = today
        restart_stats['day_restarts'] = 0
    
    if restart_stats['day_restarts'] >= MAX_RESTART_ATTEMPTS:
        return False, "Maximale Anzahl an Neustarts für heute erreicht"
    
    # Prüfe Abkühlphase
    if (restart_stats['last_restart'] and 
        (datetime.now() - restart_stats['last_restart']).total_seconds() < RESTART_COOLDOWN):
        return False, "Abkühlphase nach letztem Neustart noch nicht abgelaufen"
    
    # Automatische Neustart-Entscheidungen
    reasons = []
    
    # Wenn problematische Worker gefunden wurden
    if worker_status['problematic']:
        num_problematic = len(worker_status['problematic'])
        reasons.append(f"{num_problematic} problematische Worker gefunden")
    
    # Wenn Redis-Probleme erkannt wurden
    if redis_status['problems']:
        reasons.append(f"Redis-Probleme: {', '.join(redis_status['problems'])}")
    
    # Keine Worker gefunden
    if not worker_status['healthy'] and not worker_status['problematic']:
        reasons.append("Keine Celery-Worker gefunden")
    
    # Entscheidung basierend auf gesammelten Gründen
    if reasons:
        reason_text = "; ".join(reasons)
        return True, reason_text
    
    return False, "Keine Neustart-Bedingungen erfüllt"

def restart_workers():
    """
    Führt einen Neustart der Celery-Worker durch.
    
    Returns:
        bool: True bei Erfolg, False bei Fehler
    """
    global restart_stats
    
    try:
        logger.warning("STARTE WORKER-NEUSTART...")
        
        # Aktualisiere Neustart-Statistiken
        restart_stats['last_restart'] = datetime.now()
        restart_stats['restart_attempts'] += 1
        
        # Sammle alle Celery-Worker-Prozesse
        worker_pids = []
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', [])
                is_celery = False
                for arg in cmdline:
                    if 'celery' in str(arg) and 'worker' in str(arg):
                        is_celery = True
                        break
                
                if is_celery:
                    worker_pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # Beende alle Worker-Prozesse
        for pid in worker_pids:
            try:
                process = psutil.Process(pid)
                logger.info(f"Beende Worker-Prozess {pid}")
                process.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.warning(f"Konnte Prozess {pid} nicht beenden: {e}")
        
        # Warte kurz, dann prüfe, ob alle Prozesse beendet wurden
        time.sleep(5)
        
        # Überprüfe, ob alle Prozesse beendet wurden
        for pid in worker_pids:
            try:
                process = psutil.Process(pid)
                logger.warning(f"Prozess {pid} läuft noch, versuche zu killen")
                process.kill()
            except psutil.NoSuchProcess:
                pass  # Prozess bereits beendet
            except psutil.AccessDenied as e:
                logger.error(f"Konnte Prozess {pid} nicht killen: {e}")
        
        # Starte die Worker neu über den Worker-Starter
        logger.info("Starte Worker-Prozesse neu...")
        
        # Führe den Worker-Starter aus
        try:
            subprocess.Popen(
                ["python", "-m", "core.worker_starter"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd="/app"
            )
            logger.info("Worker-Starter erfolgreich gestartet")
        except Exception as e:
            logger.error(f"Fehler beim Starten des Worker-Starters: {e}")
            return False
        
        # Aktualisiere den Neustartzähler bei Erfolg
        restart_stats['restart_count'] += 1
        restart_stats['day_restarts'] += 1
        
        return True
        
    except Exception as e:
        logger.error(f"Fehler beim Neustart der Worker: {e}")
        return False

def watchdog_loop():
    """Hauptüberwachungsschleife."""
    logger.info("Watchdog-Service gestartet")
    
    while True:
        try:
            # Sammle Statusinformationen
            logger.info("Überprüfe Worker-Status...")
            worker_status = check_celery_workers()
            redis_status = check_redis_health()
            
            # Logge Status
            total_workers = len(worker_status['healthy']) + len(worker_status['problematic'])
            logger.info(f"Status: {total_workers} Worker gefunden ({len(worker_status['healthy'])} gesund, {len(worker_status['problematic'])} problematisch)")
            
            if worker_status['problematic']:
                for i, worker in enumerate(worker_status['problematic']):
                    logger.warning(f"Problematischer Worker {i+1}: PID {worker['pid']}, Probleme: {', '.join(worker.get('problems', ['Unbekannt']))}")
            
            if redis_status['problems']:
                logger.warning(f"Redis-Probleme: {', '.join(redis_status['problems'])}")
                
            # Entscheide, ob ein Neustart nötig ist
            should_restart, reason = should_restart_workers(worker_status, redis_status)
            
            if should_restart:
                logger.warning(f"NEUSTART ERFORDERLICH: {reason}")
                restart_success = restart_workers()
                
                if restart_success:
                    logger.info("Worker-Neustart erfolgreich durchgeführt")
                else:
                    logger.error("Worker-Neustart fehlgeschlagen")
            else:
                logger.info(f"Kein Neustart erforderlich: {reason}")
            
            # Logge Statistiken
            logger.info(f"Neustart-Statistik: {restart_stats['restart_count']} erfolgreich, {restart_stats['day_restarts']}/{MAX_RESTART_ATTEMPTS} heute")
            
        except Exception as e:
            logger.error(f"Fehler in der Watchdog-Schleife: {e}")
        
        # Warte bis zur nächsten Überprüfung
        logger.info(f"Warte {CHECK_INTERVAL} Sekunden bis zur nächsten Überprüfung...")
        time.sleep(CHECK_INTERVAL)

def handle_signal(signum, frame):
    """Signal-Handler für sauberes Beenden."""
    logger.info(f"Signal {signum} empfangen, beende Watchdog...")
    sys.exit(0)

def main():
    """Hauptfunktion."""
    # Registriere Signal-Handler
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    
    # Starte die Überwachungsschleife
    watchdog_loop()

if __name__ == "__main__":
    main() 