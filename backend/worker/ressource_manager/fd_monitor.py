"""
Datei-Deskriptor-Überwachung für den Worker-Microservice
"""
import os
import logging
import resource
import psutil
import gc
import signal

# Logger konfigurieren
logger = logging.getLogger(__name__)

def check_and_set_fd_limits():
    """
    Überprüft und setzt das Limit für Datei-Deskriptoren.
    
    Returns:
        tuple: Das aktuelle und maximale Datei-Deskriptor-Limit
    """
    try:
        # Aktuelle Limits abrufen
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        logger.info(f"Aktuelle Datei-Deskriptor-Limits: soft={soft}, hard={hard}")
        
        # Versuche, das Soft-Limit zu erhöhen
        target_soft = min(hard, 65536)  # Setze auf Hard-Limit oder 65536, was niedriger ist
        if soft < target_soft:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target_soft, hard))
            new_soft, new_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            logger.info(f"Datei-Deskriptor-Limits aktualisiert: soft={new_soft}, hard={new_hard}")
            return new_soft, new_hard
        
        return soft, hard
    except Exception as e:
        logger.warning(f"Konnte Datei-Deskriptor-Limits nicht anpassen: {e}")
        return None, None

def monitor_file_descriptors():
    """
    Überwacht die Anzahl der offenen Datei-Deskriptoren und gibt Informationen aus.
    
    Returns:
        int: Die Anzahl der offenen Datei-Deskriptoren oder -1 bei Fehlern
    """
    try:
        process = psutil.Process(os.getpid())
        fds_count = len(process.open_files())
        memory_info = process.memory_info()
        
        logger.info(f"Aktuelle Anzahl offener Datei-Deskriptoren: {fds_count}")
        logger.info(f"Aktuelle RAM-Nutzung: RSS={memory_info.rss / (1024*1024):.2f} MB, VMS={memory_info.vms / (1024*1024):.2f} MB")
        
        # Zusätzliche Überwachung, falls viele Deskriptoren offen sind
        if fds_count > 200:
            logger.warning(f"Hohe Anzahl offener Datei-Deskriptoren: {fds_count}")
            # Liste der offenen Dateien anzeigen
            open_files = [f.path for f in process.open_files()]
            logger.debug(f"Offene Dateien (Top 10): {open_files[:10]}")
            
            # Manuelles Abholen von Garbage Collection
            if fds_count > 500:
                logger.warning("Kritische Anzahl offener Datei-Deskriptoren - führe Garbage Collection durch")
                collected = gc.collect()
                logger.info(f"Garbage Collection abgeschlossen: {collected} Objekte eingesammelt")
                
                # Erneut prüfen nach GC
                new_fds_count = len(process.open_files())
                logger.info(f"Nach GC: {new_fds_count} offene Datei-Deskriptoren (vorher: {fds_count})")
                return new_fds_count
        
        return fds_count
    except ImportError:
        logger.warning("Fehler bei der Überwachung der Datei-Deskriptoren: psutil-Modul nicht verfügbar")
        return -1
    except Exception as e:
        logger.warning(f"Fehler bei der Überwachung der Datei-Deskriptoren: {str(e)}")
        return -1

def schedule_periodic_check(interval=300):
    """
    Planmäßige Überprüfung der Datei-Deskriptoren.
    
    Args:
        interval: Zeit in Sekunden zwischen den Überprüfungen
        
    Returns:
        bool: True bei Erfolg, False bei Fehler
    """
    import threading
    
    def periodic_check():
        """Periodische Überprüfung der Ressourcen"""
        try:
            # Führe Datei-Deskriptor-Überwachung durch
            fd_count = monitor_file_descriptors()
            
            # Wenn mehr als 800 Datei-Deskriptoren offen sind, empfehle Neustart
            if fd_count > 800:
                logger.critical(f"Kritische Anzahl offener Datei-Deskriptoren: {fd_count} - Worker sollte neu gestartet werden")
                # Empfehle Neustart, aber erzwinge ihn nicht
                return
            
            # Plane nächste Überprüfung
            threading.Timer(interval, periodic_check).start()
        except Exception as e:
            logger.error(f"Fehler bei periodischer Ressourcenüberwachung: {e}")
            # Auch bei Fehlern weiter überwachen
            threading.Timer(interval, periodic_check).start()
    
    try:
        # Starte erste Überprüfung nach kurzer Verzögerung
        threading.Timer(60, periodic_check).start()  # Erste Überprüfung nach 1 Minute
        logger.info(f"Periodische Datei-Deskriptor-Überwachung alle {interval} Sekunden geplant")
        return True
    except Exception as e:
        logger.error(f"Konnte periodische Überwachung nicht starten: {e}")
        return False 