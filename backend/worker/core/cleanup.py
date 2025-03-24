#!/usr/bin/env python
"""
Bereinigungsskript für Datei-Deskriptoren.
Kann manuell oder automatisiert bei Problemen ausgeführt werden.
"""
import os
import sys
import gc
import time
import logging
import signal
import psutil
import resource

# Konfiguriere Logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("cleanup")

def get_fd_count():
    """Ermittelt die Anzahl offener Datei-Deskriptoren für den aktuellen Prozess."""
    try:
        process = psutil.Process(os.getpid())
        open_files = process.open_files()
        open_connections = process.connections()
        return len(open_files) + len(open_connections)
    except Exception as e:
        logger.error(f"Fehler beim Zählen der Datei-Deskriptoren: {e}")
        return -1

def list_all_fds():
    """Listet alle offenen Datei-Deskriptoren für alle Prozesse auf."""
    try:
        logger.info("Liste alle offenen Datei-Deskriptoren auf...")
        
        for proc in psutil.process_iter(['pid', 'name', 'username']):
            try:
                proc_info = proc.info
                pid = proc_info['pid']
                name = proc_info['name']
                
                # Nur für Prozesse, die mit Python oder Celery zu tun haben
                if 'python' in name.lower() or 'celery' in name.lower():
                    process = psutil.Process(pid)
                    open_files = process.open_files()
                    connections = process.connections()
                    
                    logger.info(f"Prozess {pid} ({name}) hat {len(open_files)} offene Dateien und {len(connections)} Verbindungen")
                    
                    # Detaillierte Auflistung
                    if len(open_files) > 10:
                        logger.info(f"  Offene Dateien (Auswahl): {', '.join([f.path for f in open_files[:10]])}")
                    elif open_files:
                        logger.info(f"  Offene Dateien: {', '.join([f.path for f in open_files])}")
                        
                    if connections:
                        logger.info(f"  Verbindungen (Auswahl): {', '.join([f'{c.laddr.ip}:{c.laddr.port}' for c in connections[:5]])}")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception as e:
        logger.error(f"Fehler beim Auflisten der Datei-Deskriptoren: {e}")

def check_redis_connections():
    """Überprüft Redis-Verbindungen."""
    try:
        # Importiere redis-Bibliothek nur bei Bedarf
        import redis
        import os
        
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        logger.info(f"Prüfe Redis-Verbindung zu {redis_url}")
        
        client = redis.from_url(redis_url)
        info = client.info()
        
        # Log wichtige Redis-Metriken
        clients = info.get('clients', {})
        connected_clients = clients.get('connected_clients', 0)
        client_recent_max_input_buffer = clients.get('client_recent_max_input_buffer', 0)
        client_recent_max_output_buffer = clients.get('client_recent_max_output_buffer', 0)
        blocked_clients = clients.get('blocked_clients', 0)
        
        logger.info(f"Redis: {connected_clients} verbundene Clients, {blocked_clients} blockierte Clients")
        logger.info(f"Redis Buffer: Max Input: {client_recent_max_input_buffer}, Max Output: {client_recent_max_output_buffer}")
        
        # Schließe die Verbindung explizit
        client.close()
        logger.info("Redis-Verbindung erfolgreich geschlossen")
        
    except Exception as e:
        logger.error(f"Fehler bei der Redis-Überprüfung: {e}")

def cleanup_processes():
    """Bereinigt hängengebliebene Worker-Prozesse."""
    try:
        logger.info("Suche nach hängengebliebenen Celery-Worker-Prozessen...")
        
        # Sammle Informationen über laufende Prozesse
        worker_processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                proc_info = proc.info
                cmdline = proc_info.get('cmdline', [])
                
                # Suche nach Celery-Workern mit ResultHandler in ihren Kommandozeilenargumenten
                is_celery = False
                for arg in cmdline:
                    if 'celery' in str(arg) and 'worker' in str(arg):
                        is_celery = True
                
                if is_celery:
                    worker_processes.append(proc)
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        if worker_processes:
            logger.info(f"Gefunden: {len(worker_processes)} Celery-Worker-Prozesse")
            
            for proc in worker_processes:
                pid = proc.pid
                cpu_percent = proc.cpu_percent(interval=1.0)
                memory_percent = proc.memory_percent()
                
                logger.info(f"  PID {pid}: CPU {cpu_percent}%, RAM {memory_percent:.2f}%")
                
                # Überprüfe, ob der Prozess hängt (wenig CPU aber lange laufend)
                if cpu_percent < 0.1 and proc.create_time() < (time.time() - 3600):
                    logger.warning(f"  PID {pid} scheint inaktiv zu sein (CPU < 0.1%, läuft seit > 1h)")
        else:
            logger.info("Keine Celery-Worker-Prozesse gefunden")
            
    except Exception as e:
        logger.error(f"Fehler bei der Prozessbereinigung: {e}")

def close_unused_fds():
    """Schließt ungenutzte Datei-Deskriptoren."""
    try:
        logger.info("Schließe ungenutzte Datei-Deskriptoren...")
        
        # In Linux können wir über /proc/self/fd iterieren
        fd_dir = '/proc/self/fd'
        if os.path.isdir(fd_dir):
            fd_list = os.listdir(fd_dir)
            logger.info(f"Anzahl der offenen Datei-Deskriptoren: {len(fd_list)}")
            
            skipped_fds = [0, 1, 2]  # stdin, stdout, stderr
            
            for fd_str in fd_list:
                try:
                    fd = int(fd_str)
                    if fd in skipped_fds:
                        continue
                        
                    # Versuche, den Datei-Deskriptor zu schließen
                    try:
                        os.close(fd)
                        logger.info(f"  Geschlossen: fd {fd}")
                    except OSError:
                        # Ignoriere Fehler beim Schließen
                        pass
                except (ValueError, OSError) as e:
                    logger.debug(f"  Konnte fd {fd_str} nicht schließen: {e}")
        else:
            # Alternative Methode für nicht-Linux-Plattformen
            logger.info("Verwende alternative Methode für Nicht-Linux-Plattformen")
            # Versuche, einige hohe Datei-Deskriptoren zu schließen
            for fd in range(3, 1024):  # Starte bei 3 (nach stdin, stdout, stderr)
                try:
                    os.close(fd)
                except OSError:
                    # Ignoriere Fehler beim Schließen
                    pass
        
    except Exception as e:
        logger.error(f"Fehler beim Schließen von FDs: {e}")

def cleanup_locks():
    """Sucht und bereinigt alle hängenden Locks im Redis."""
    try:
        # Verbindung zu Redis herstellen
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        logger.info(f"Prüfe Redis-Verbindung zu {redis_url}")
        
        client = redis.from_url(redis_url)
        info = client.info()
        
        # Log wichtige Redis-Metriken
        clients = info.get('clients', {})
        connected_clients = clients.get('connected_clients', 0)
        client_recent_max_input_buffer = clients.get('client_recent_max_input_buffer', 0)
        client_recent_max_output_buffer = clients.get('client_recent_max_output_buffer', 0)
        blocked_clients = clients.get('blocked_clients', 0)
        
        logger.info(f"Redis: {connected_clients} verbundene Clients, {blocked_clients} blockierte Clients")
        logger.info(f"Redis Buffer: Max Input: {client_recent_max_input_buffer}, Max Output: {client_recent_max_output_buffer}")
        
        # Schließe die Verbindung explizit
        client.close()
        logger.info("Redis-Verbindung erfolgreich geschlossen")
        
    except Exception as e:
        logger.error(f"Fehler bei der Redis-Überprüfung: {e}")

def main():
    """Hauptfunktion."""
    logger.info("===== Datei-Deskriptor-Bereinigung gestartet =====")
    
    # Erhöhe die Datei-Deskriptor-Limits
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        logger.info(f"Aktuelle FD-Limits: soft={soft}, hard={hard}")
        
        target_soft = min(hard, 65536)
        if soft < target_soft:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target_soft, hard))
            new_soft, new_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            logger.info(f"Neue FD-Limits: soft={new_soft}, hard={new_hard}")
    except Exception as e:
        logger.error(f"Konnte FD-Limits nicht anpassen: {e}")
    
    # Führe alle Bereinigungsfunktionen aus
    fd_count_before = get_fd_count()
    logger.info(f"Aktuelle FD-Anzahl: {fd_count_before}")
    
    list_all_fds()
    check_redis_connections()
    cleanup_processes()
    
    # Führe Garbage Collection durch
    logger.info("Führe Garbage Collection durch...")
    gc.collect()
    
    # Schließe ungenutzte Datei-Deskriptoren
    close_unused_fds()
    
    # Überprüfe Ergebnis
    fd_count_after = get_fd_count()
    logger.info(f"FD-Anzahl nach Bereinigung: {fd_count_after}")
    
    if fd_count_before > 0 and fd_count_after > 0:
        reduction = ((fd_count_before - fd_count_after) / fd_count_before) * 100
        logger.info(f"Reduktion um {reduction:.1f}%")
    
    logger.info("===== Datei-Deskriptor-Bereinigung abgeschlossen =====")

if __name__ == "__main__":
    main() 