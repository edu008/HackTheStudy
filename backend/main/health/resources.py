"""
Ressourcenüberwachungsfunktionen für das Health-Monitoring-System.
Enthält Funktionen zur Überwachung von Speicher, CPU und Dateideskriptoren.
"""

import os
import logging
import platform
from typing import Tuple, List

# Logger konfigurieren
logger = logging.getLogger(__name__)

def get_memory_usage() -> Tuple[int, float]:
    """
    Ermittelt den aktuellen Speicherverbrauch des Prozesses.
    
    Returns:
        Tuple: (Speicherverbrauch in Bytes, Prozentsatz des Systemspeichers)
    """
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        memory_bytes = memory_info.rss
        
        # Prozentsatz berechnen
        total_memory = psutil.virtual_memory().total
        memory_percent = (memory_bytes / total_memory) * 100
        
        return memory_bytes, memory_percent
    except ImportError:
        logger.warning("psutil nicht installiert, kann Speichernutzung nicht ermitteln")
        return 0, 0
    except Exception as e:
        logger.error(f"Fehler bei der Ermittlung des Speicherverbrauchs: {str(e)}")
        return 0, 0

def get_cpu_usage() -> float:
    """
    Ermittelt die aktuelle CPU-Nutzung des Prozesses.
    
    Returns:
        float: CPU-Nutzung in Prozent
    """
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.cpu_percent(interval=0.1)
    except ImportError:
        logger.warning("psutil nicht installiert, kann CPU-Nutzung nicht ermitteln")
        return 0
    except Exception as e:
        logger.error(f"Fehler bei der Ermittlung der CPU-Nutzung: {str(e)}")
        return 0

def get_open_file_descriptors() -> List[int]:
    """
    Gibt die offenen Dateideskriptoren des aktuellen Prozesses zurück.
    
    Returns:
        List[int]: Liste von Dateideskriptoren
    """
    try:
        import psutil
        process = psutil.Process(os.getpid())
        
        if platform.system() == 'Windows':
            # Auf Windows keine detaillierten Dateideskriptoren verfügbar
            return list(range(process.num_handles()))
        else:
            # Auf Unix-Systemen können wir die tatsächlichen Dateien auflisten
            return process.open_files()
    except ImportError:
        logger.warning("psutil nicht installiert, kann offene Dateien nicht zählen")
        return []
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der offenen Dateideskriptoren: {str(e)}")
        return []

def get_system_info() -> dict:
    """
    Sammelt allgemeine Systeminformationen.
    
    Returns:
        dict: Systeminformationen
    """
    try:
        system_info = {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "pid": os.getpid()
        }
        
        # Erweiterte Informationen mit psutil, falls verfügbar
        try:
            import psutil
            memory = psutil.virtual_memory()
            system_info.update({
                "total_memory_mb": memory.total / (1024 * 1024),
                "available_memory_mb": memory.available / (1024 * 1024),
                "memory_percent": memory.percent,
                "cpu_count": psutil.cpu_count(),
                "cpu_percent": psutil.cpu_percent(interval=0.1)
            })
        except ImportError:
            pass
        
        return system_info
    except Exception as e:
        logger.error(f"Fehler beim Sammeln von Systeminformationen: {str(e)}")
        return {"error": str(e)} 