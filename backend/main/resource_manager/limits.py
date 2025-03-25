"""
Verwaltung von Systemressourcen-Limits.
"""

import os
import sys
import resource
import logging
import platform
from typing import Optional, Tuple

# Logger konfigurieren
logger = logging.getLogger(__name__)

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