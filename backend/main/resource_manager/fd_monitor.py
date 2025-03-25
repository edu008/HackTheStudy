"""
Überwachung und Verwaltung von Datei-Deskriptoren.
"""

import os
import resource
import logging
import threading
import time
import subprocess
from typing import Dict, List, Tuple

# Logger konfigurieren
logger = logging.getLogger(__name__)

def check_and_set_fd_limits() -> Tuple[int, int]:
    """
    Überprüft die aktuellen Datei-Deskriptor-Limits und erhöht sie bei Bedarf.
    
    Returns:
        Tuple mit (soft_limit, hard_limit) nach Anpassung
    """
    try:
        # Aktuelle Limits holen
        soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
        logger.info(f"Aktuelle FD-Limits: soft={soft_limit}, hard={hard_limit}")
        
        # Wenn das Soft-Limit zu niedrig ist, erhöhen
        desired_soft_limit = 4096  # Gewünschtes Soft-Limit
        
        if soft_limit < desired_soft_limit and hard_limit >= desired_soft_limit:
            logger.info(f"Erhöhe Soft-Limit von {soft_limit} auf {desired_soft_limit}")
            resource.setrlimit(resource.RLIMIT_NOFILE, (desired_soft_limit, hard_limit))
            soft_limit = desired_soft_limit
            logger.info(f"FD-Limits angepasst auf: soft={soft_limit}, hard={hard_limit}")
        
        return soft_limit, hard_limit
    except Exception as e:
        logger.error(f"Fehler beim Anpassen der FD-Limits: {str(e)}")
        return resource.getrlimit(resource.RLIMIT_NOFILE)

def get_open_file_descriptors() -> List[Dict]:
    """
    Ermittelt die aktuell geöffneten Datei-Deskriptoren für den laufenden Prozess.
    
    Returns:
        Liste mit Informationen zu den offenen Datei-Deskriptoren
    """
    try:
        pid = os.getpid()
        fd_info = []
        
        # Linux: /proc/[pid]/fd/ auslesen
        if os.path.exists(f"/proc/{pid}/fd"):
            try:
                for fd in os.listdir(f"/proc/{pid}/fd"):
                    try:
                        target = os.readlink(f"/proc/{pid}/fd/{fd}")
                        fd_info.append({
                            "fd": int(fd),
                            "target": target
                        })
                    except (FileNotFoundError, PermissionError):
                        pass
                
                return fd_info
            except Exception as e:
                logger.error(f"Fehler beim Auslesen der Datei-Deskriptoren aus /proc: {str(e)}")
        
        # Alternative: lsof verwenden (für macOS, etc.)
        try:
            output = subprocess.check_output(['lsof', '-p', str(pid)], text=True)
            lines = output.strip().split('\n')[1:]  # Header überspringen
            
            for line in lines:
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        fd_info.append({
                            "fd": parts[3],
                            "target": parts[8] if len(parts) > 8 else parts[7]
                        })
                    except (IndexError, ValueError):
                        pass
            
            return fd_info
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.error(f"Fehler beim Ausführen von lsof: {str(e)}")
        
        # Fallback: Minimaler Bericht
        return [{"fd": "unknown", "count": "unavailable"}]
    except Exception as e:
        logger.error(f"Unerwarteter Fehler beim Ermitteln der Datei-Deskriptoren: {str(e)}")
        return []

def monitor_file_descriptors(monitoring_interval: int = 300) -> threading.Thread:
    """
    Startet einen Thread zur Überwachung der Datei-Deskriptoren.
    
    Args:
        monitoring_interval: Intervall in Sekunden zwischen Prüfungen
    
    Returns:
        Thread-Objekt
    """
    def monitor_loop():
        while True:
            try:
                # Aktuelle Limits holen
                soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
                
                # Offene Deskriptoren zählen
                fds = get_open_file_descriptors()
                
                # Nutzung berechnen
                usage_percent = len(fds) / soft_limit * 100 if soft_limit > 0 else 0
                
                # Logge nur bei hoher Nutzung oder im Debug-Modus
                if usage_percent > 70 or logger.isEnabledFor(logging.DEBUG):
                    logger.info(f"FD-Nutzung: {len(fds)}/{soft_limit} ({usage_percent:.1f}%)")
                    
                # Warne ab 80% Nutzung
                if usage_percent > 80:
                    logger.warning(f"Hohe FD-Nutzung: {len(fds)}/{soft_limit} ({usage_percent:.1f}%)")
                    
                # Kritisch ab 95%
                if usage_percent > 95:
                    logger.error(f"Kritische FD-Nutzung: {len(fds)}/{soft_limit} ({usage_percent:.1f}%)")
                    # Hier könnte man Gegenmaßnahmen ergreifen, z.B. GC oder Verbindungen schließen
            except Exception as e:
                logger.error(f"Fehler in FD-Monitoring: {str(e)}")
            
            # Warte bis zum nächsten Check
            time.sleep(monitoring_interval)
    
    # Thread starten
    thread = threading.Thread(target=monitor_loop, daemon=True, name="fd-monitor")
    thread.start()
    logger.info(f"FD-Monitoring gestartet (Intervall: {monitoring_interval}s)")
    
    return thread 