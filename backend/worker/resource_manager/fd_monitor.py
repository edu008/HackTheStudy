"""
Modul zur Überwachung der offenen Dateideskriptoren.
"""
import os
import sys
import time
import logging
import signal
import threading
import psutil

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Prozess-Objekt für später
process = None

# Shutdown-Flag
shutdown_requested = False

def check_file_descriptors():
    """
    Überprüft die aktuelle Anzahl offener Dateideskriptoren.
    
    Returns:
        int: Anzahl der offenen Datei-Deskriptoren
    """
    global process
    
    # Initialisiere das Prozess-Objekt, falls noch nicht geschehen
    if process is None:
        process = psutil.Process(os.getpid())
    
    try:
        # Anzahl der offenen Datei-Deskriptoren ermitteln
        # Dies funktioniert nur unter Linux/Unix
        if hasattr(process, 'num_fds'):
            return process.num_fds()
        else:
            # Unter Windows versuchen wir es mit handles
            if hasattr(process, 'num_handles'):
                return process.num_handles()
            else:
                logger.warning("Konnte offene Datei-Deskriptoren nicht ermitteln - nicht unterstützt auf dieser Plattform")
                return 0
    except Exception as e:
        logger.error(f"Fehler beim Ermitteln der offenen Datei-Deskriptoren: {str(e)}")
        return 0

def check_and_set_fd_limits(soft_limit=None, hard_limit=None):
    """
    Überprüft und setzt die Limits für offene Dateideskriptoren.
    
    Args:
        soft_limit: Gewünschtes Soft-Limit (oder None für Systemwert)
        hard_limit: Gewünschtes Hard-Limit (oder None für Systemwert)
    
    Returns:
        tuple: (soft_limit, hard_limit) nach dem Setzen
    """
    try:
        import resource
        
        # Aktuelles Limit abrufen
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        logger.info(f"Aktuelle Datei-Deskriptor-Limits: soft={soft}, hard={hard}")
        
        # Limits anpassen, falls angefordert
        if soft_limit is not None or hard_limit is not None:
            # Verwende aktuelle Werte, wenn nicht explizit angegeben
            new_soft = soft_limit if soft_limit is not None else soft
            new_hard = hard_limit if hard_limit is not None else hard
            
            # Hard-Limit kann nicht höher als das System-Hard-Limit sein
            new_hard = min(new_hard, hard)
            
            # Soft-Limit kann nicht höher als Hard-Limit sein
            new_soft = min(new_soft, new_hard)
            
            # Neue Limits setzen
            resource.setrlimit(resource.RLIMIT_NOFILE, (new_soft, new_hard))
            logger.info(f"Neue Datei-Deskriptor-Limits gesetzt: soft={new_soft}, hard={new_hard}")
            
            return new_soft, new_hard
        
        return soft, hard
    except ImportError:
        logger.warning("Das Modul 'resource' ist nicht verfügbar (wahrscheinlich Windows)")
        return None, None
    except Exception as e:
        logger.error(f"Fehler beim Setzen der Datei-Deskriptor-Limits: {str(e)}")
        return None, None

def monitor_file_descriptors():
    """
    Überwacht die Anzahl der offenen Dateideskriptoren und loggt sie.
    """
    try:
        # Offene Datei-Deskriptoren zählen
        fd_count = check_file_descriptors()
        logger.info(f"Aktuelle Anzahl offener Datei-Deskriptoren: {fd_count}")
        
        # RAM-Nutzung überwachen
        global process
        if process is None:
            process = psutil.Process(os.getpid())
        
        # RAM-Nutzung in MB
        rss = process.memory_info().rss / (1024 * 1024)
        vms = process.memory_info().vms / (1024 * 1024)
        logger.info(f"Aktuelle RAM-Nutzung: RSS={rss:.2f} MB, VMS={vms:.2f} MB")
        
        return {
            'fd_count': fd_count,
            'rss_mb': rss,
            'vms_mb': vms,
            'timestamp': time.time()
        }
    except Exception as e:
        logger.error(f"Fehler bei der Ressourcenüberwachung: {str(e)}")
        return None

def schedule_periodic_check(interval_seconds=300):
    """
    Plant eine periodische Überprüfung der Ressourcennutzung.
    
    Args:
        interval_seconds: Anzahl der Sekunden zwischen den Überprüfungen
    """
    global shutdown_requested
    
    def run_periodic_check():
        while not shutdown_requested:
            monitor_file_descriptors()
            # Schlafe bis zum nächsten Intervall oder bis zum Shutdown
            for _ in range(interval_seconds):
                if shutdown_requested:
                    break
                time.sleep(1)
    
    logger.info(f"Periodische Datei-Deskriptor-Überwachung alle {interval_seconds} Sekunden geplant")
    thread = threading.Thread(target=run_periodic_check, daemon=False)
    thread.start()
    return thread

def signal_handler(signum, frame):
    """
    Behandelt Signale wie SIGTERM und SIGINT.
    """
    global shutdown_requested
    logger.info(f"Signal {signum} empfangen, Herunterfahren...")
    shutdown_requested = True

# Wenn als eigenständiges Skript ausgeführt
if __name__ == "__main__":
    # Konfiguriere Logging, wenn nicht bereits geschehen
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format='[FD-MONITOR] %(levelname)s: %(message)s')
    
    # Signal-Handler registrieren
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("Dateisystem-Monitor gestartet")
    
    # Limits setzen und aktuelle Nutzung prüfen
    check_and_set_fd_limits()
    monitor_file_descriptors()
    
    # Periodische Überprüfung starten
    monitor_thread = schedule_periodic_check(interval_seconds=60)
    
    logger.info("Dateisystem-Monitor läuft im Vordergrund. Drücken Sie Strg+C zum Beenden.")
    
    # Hauptschleife, um den Prozess am Leben zu halten
    try:
        while not shutdown_requested:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Tastatur-Interrupt empfangen, Herunterfahren...")
        shutdown_requested = True
        
    # Warte, bis der Monitor-Thread beendet ist
    if monitor_thread.is_alive():
        monitor_thread.join(timeout=5)
        
    logger.info("Dateisystem-Monitor-Prozess beendet") 