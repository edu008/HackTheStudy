"""
Zentrales Ressourcenmanagement für den API-Container.
Verwaltet und überwacht Systemressourcen wie CPU, Speicher und Datei-Deskriptoren.
"""

import os
import sys
import resource
import logging
import threading
import time
import subprocess
import platform
from typing import Dict, List, Tuple, Optional

# Logger konfigurieren
logger = logging.getLogger(__name__)

#
# Speicher- und CPU-Verwaltung
#

def set_memory_limit(limit_mb: int) -> bool:
    """
    Setzt ein Speicher-Limit für den aktuellen Prozess.
    
    Args:
        limit_mb: Speicherlimit in Megabyte
    
    Returns:
        True bei Erfolg, False bei Fehler
    """
    try:
        # Nur unter Linux verfügbar (RLIMIT_AS)
        if platform.system() == 'Linux':
            limit_bytes = limit_mb * 1024 * 1024
            _, hard_limit = resource.getrlimit(resource.RLIMIT_AS)
            
            # Neue Limits setzen (soft <= hard)
            new_limit = min(limit_bytes, hard_limit) if hard_limit > 0 else limit_bytes
            resource.setrlimit(resource.RLIMIT_AS, (new_limit, hard_limit))
            
            logger.info(f"Speicherlimit gesetzt: {new_limit / (1024*1024):.1f}MB (angefordert: {limit_mb}MB)")
            return True
        else:
            logger.warning(f"Speicherlimit-Setzung nicht unterstützt auf {platform.system()}")
            return False
    except Exception as e:
        logger.error(f"Fehler beim Setzen des Speicherlimits: {str(e)}")
        return False

def set_cpu_limit(limit_seconds: int) -> bool:
    """
    Setzt ein CPU-Zeitlimit für den aktuellen Prozess.
    
    Args:
        limit_seconds: CPU-Zeitlimit in Sekunden
    
    Returns:
        True bei Erfolg, False bei Fehler
    """
    try:
        _, hard_limit = resource.getrlimit(resource.RLIMIT_CPU)
        
        # Neue Limits setzen (soft <= hard)
        new_limit = min(limit_seconds, hard_limit) if hard_limit > 0 else limit_seconds
        resource.setrlimit(resource.RLIMIT_CPU, (new_limit, hard_limit))
        
        logger.info(f"CPU-Zeitlimit gesetzt: {new_limit}s (angefordert: {limit_seconds}s)")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Setzen des CPU-Zeitlimits: {str(e)}")
        return False

def get_memory_usage() -> Tuple[int, float]:
    """
    Ermittelt die aktuelle Speichernutzung des Prozesses.
    
    Returns:
        Tuple aus (Nutzung in Bytes, Nutzung in Prozent des Limits)
    """
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        # RSS = Resident Set Size (physischer Speicher)
        usage_bytes = memory_info.rss
        
        # Prozentuale Nutzung berechnen, falls ein Limit gesetzt ist
        percent = 0.0
        try:
            if platform.system() == 'Linux':
                soft_limit, _ = resource.getrlimit(resource.RLIMIT_AS)
                if soft_limit > 0:
                    percent = usage_bytes / soft_limit * 100
        except:
            pass
        
        return (usage_bytes, percent)
    except ImportError:
        logger.warning("psutil nicht installiert, Speichernutzung nicht verfügbar")
        return (0, 0.0)
    except Exception as e:
        logger.error(f"Fehler beim Ermitteln der Speichernutzung: {str(e)}")
        return (0, 0.0)

def get_cpu_usage() -> float:
    """
    Ermittelt die aktuelle CPU-Nutzung des Prozesses.
    
    Returns:
        CPU-Nutzung in Prozent (0-100)
    """
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.cpu_percent(interval=0.1)
    except ImportError:
        logger.warning("psutil nicht installiert, CPU-Nutzung nicht verfügbar")
        return 0.0
    except Exception as e:
        logger.error(f"Fehler beim Ermitteln der CPU-Nutzung: {str(e)}")
        return 0.0

#
# Datei-Deskriptor-Verwaltung
#

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

#
# Periodische Überwachung
#

_monitoring_threads = {}

def start_resource_monitoring(interval: int = 300) -> Dict[str, threading.Thread]:
    """
    Startet alle Ressourcenüberwachungs-Threads.
    
    Args:
        interval: Standardintervall in Sekunden zwischen Prüfungen
    
    Returns:
        Dictionary mit gestarteten Threads
    """
    global _monitoring_threads
    
    # Datei-Deskriptor-Überwachung starten
    if 'fd_monitor' not in _monitoring_threads or not _monitoring_threads['fd_monitor'].is_alive():
        _monitoring_threads['fd_monitor'] = monitor_file_descriptors(interval)
    
    logger.info(f"Ressourcenüberwachung gestartet: {len(_monitoring_threads)} aktive Threads")
    return _monitoring_threads

def schedule_periodic_check(interval: int = 3600) -> threading.Thread:
    """
    Plant periodische Systemressourcen-Prüfungen.
    
    Args:
        interval: Intervall in Sekunden zwischen kompletten Prüfungen
        
    Returns:
        Thread-Objekt
    """
    def check_loop():
        while True:
            try:
                # Speicherinformationen
                mem_bytes, mem_percent = get_memory_usage()
                logger.info(f"Speichernutzung: {mem_bytes/(1024*1024):.1f}MB ({mem_percent:.1f}%)")
                
                # CPU-Nutzung
                cpu_percent = get_cpu_usage()
                logger.info(f"CPU-Nutzung: {cpu_percent:.1f}%")
                
                # Datei-Deskriptoren
                soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
                fds = get_open_file_descriptors()
                fd_percent = len(fds) / soft_limit * 100 if soft_limit > 0 else 0
                logger.info(f"FD-Nutzung: {len(fds)}/{soft_limit} ({fd_percent:.1f}%)")
                
                # Weitere Systeminfos
                logger.info(f"Systeminformationen: {platform.system()} {platform.release()}, Python {platform.python_version()}")
            except Exception as e:
                logger.error(f"Fehler bei periodischer Systemprüfung: {str(e)}")
            
            # Warte bis zur nächsten Prüfung
            time.sleep(interval)
    
    # Thread starten
    thread = threading.Thread(target=check_loop, daemon=True, name="resource-check")
    thread.start()
    logger.info(f"Periodische Ressourcenprüfung gestartet (Intervall: {interval}s)")
    
    # Speichern für spätere Referenz
    _monitoring_threads['resource_check'] = thread
    
    return thread 