"""
Zentrales Ressourcenmanagement für den API-Container.
Verwaltet und überwacht Systemressourcen wie CPU, Speicher und Datei-Deskriptoren.
"""

import logging
import os
import platform
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple

# Versuche das resource-Modul zu importieren, das nur unter Linux/Unix verfügbar ist
try:
    import resource
except ImportError:
    # Mockup für Windows und andere Systeme ohne resource-Modul
    class ResourceMock:
        RLIMIT_AS = 0
        RLIMIT_CPU = 1
        RLIMIT_NOFILE = 2

        @staticmethod
        def getrlimit(resource_type):
            return (0, 0)

        @staticmethod
        def setrlimit(resource_type, limits):
            pass

    resource = ResourceMock()
    logging.getLogger(__name__).warning("resource-Modul nicht verfügbar auf diesem System (vermutlich Windows)")

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

            logger.info("Speicherlimit gesetzt: %sMB (angefordert: %sMB)", f"{new_limit / (1024*1024):.1f}", limit_mb)
            return True
        
        logger.warning("Speicherlimit-Setzung nicht unterstützt auf %s", platform.system())
        return False
    except Exception as e:
        logger.error("Fehler beim Setzen des Speicherlimits: %s", str(e))
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

        logger.info("CPU-Zeitlimit gesetzt: %ss (angefordert: %ss)", new_limit, limit_seconds)
        return True
    except Exception as e:
        logger.error("Fehler beim Setzen des CPU-Zeitlimits: %s", str(e))
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
        except BaseException:
            pass

        return (usage_bytes, percent)
    except ImportError:
        logger.warning("psutil nicht installiert, Speichernutzung nicht verfügbar")
        return (0, 0.0)
    except Exception as e:
        logger.error("Fehler beim Ermitteln der Speichernutzung: %s", str(e))
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
        logger.error("Fehler beim Ermitteln der CPU-Nutzung: %s", str(e))
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
        logger.info("Aktuelle FD-Limits: soft=%s, hard=%s", soft_limit, hard_limit)

        # Wenn das Soft-Limit zu niedrig ist, erhöhen
        desired_soft_limit = 4096  # Gewünschtes Soft-Limit

        if soft_limit < desired_soft_limit and hard_limit >= desired_soft_limit:
            logger.info("Erhöhe Soft-Limit von %s auf %s", soft_limit, desired_soft_limit)
            resource.setrlimit(resource.RLIMIT_NOFILE, (desired_soft_limit, hard_limit))
            soft_limit = desired_soft_limit
            logger.info("FD-Limits angepasst auf: soft=%s, hard=%s", soft_limit, hard_limit)

        return soft_limit, hard_limit
    except Exception as e:
        logger.error("Fehler beim Anpassen der FD-Limits: %s", str(e))
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
                logger.error("Fehler beim Auslesen der Datei-Deskriptoren aus /proc: %s", str(e))

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
            logger.error("Fehler beim Ausführen von lsof: %s", str(e))

        # Fallback: Minimaler Bericht
        return [{"fd": "unknown", "count": "unavailable"}]
    except Exception as e:
        logger.error("Unerwarteter Fehler beim Ermitteln der Datei-Deskriptoren: %s", str(e))
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
                    logger.info("FD-Nutzung: %s/%s (%s%%)", len(fds), soft_limit, f"{usage_percent:.1f}")

                # Warne ab 80% Nutzung
                if usage_percent > 80:
                    logger.warning("Hohe FD-Nutzung: %s/%s (%s%%)", len(fds), soft_limit, f"{usage_percent:.1f}")

                # Kritisch ab 95%
                if usage_percent > 95:
                    logger.error("Kritische FD-Nutzung: %s/%s (%s%%)", len(fds), soft_limit, f"{usage_percent:.1f}")
                    # Hier könnte man Gegenmaßnahmen ergreifen, z.B. GC oder Verbindungen schließen
            except Exception as e:
                logger.error("Fehler in FD-Monitoring: %s", str(e))

            # Warte bis zum nächsten Check
            time.sleep(monitoring_interval)

    # Thread starten
    thread = threading.Thread(target=monitor_loop, daemon=True, name="fd-monitor")
    thread.start()
    logger.info("FD-Monitoring gestartet (Intervall: %ss)", monitoring_interval)

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

    logger.info("Ressourcenüberwachung gestartet: %s aktive Threads", len(_monitoring_threads))
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
                soft_limit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
                fds = get_open_file_descriptors()
                fd_percent = len(fds) / soft_limit * 100 if soft_limit > 0 else 0
                logger.info(f"FD-Nutzung: {len(fds)}/{soft_limit} ({fd_percent:.1f}%)")

                # Weitere Systeminfos
                logger.info(
                    f"Systeminformationen: {platform.system()} {platform.release()}, "
                    f"Python {platform.python_version()}")
            except Exception as e:
                logger.error("Fehler bei periodischer Systemprüfung: %s", str(e))

            # Warte bis zur nächsten Prüfung
            time.sleep(interval)

    # Thread starten
    thread = threading.Thread(target=check_loop, daemon=True, name="resource-check")
    thread.start()
    logger.info("Periodische Ressourcenprüfung gestartet (Intervall: %ss)", interval)

    # Globale Variable initialisieren, falls noch nicht geschehen
    global _monitoring_threads
    if '_monitoring_threads' not in globals():
        _monitoring_threads = {}
        
    # Speichern für spätere Referenz
    _monitoring_threads['resource_check'] = thread

    return thread
