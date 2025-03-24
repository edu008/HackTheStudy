"""
Ressourcenverwaltungsmodul für HackTheStudy.
Enthält Funktionen zum Verwalten von Systemressourcen wie Datei-Deskriptoren,
Speicher und Prozessüberwachung.
"""

import os
import sys
import logging
import resource  # Für Ressourcenlimits
import psutil  # Für Prozessüberwachung
import gc  # Garbage Collector

# Logger einrichten
logger = logging.getLogger(__name__)

def check_and_set_fd_limits():
    """
    Überprüft aktuelle Datei-Deskriptor-Limits und erhöht sie bei Bedarf.
    
    Diese Funktion erhöht die Anzahl der erlaubten offenen Dateien,
    um Probleme mit 'Too many open files' zu vermeiden.
    """
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        logger.info(f"Aktuelle Datei-Deskriptor-Limits: soft={soft}, hard={hard}")
        
        # Versuche, das Soft-Limit auf mindestens 4096 oder das Hard-Limit zu setzen
        target_soft = min(max(4096, soft), hard)
        if target_soft > soft:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target_soft, hard))
            new_soft, new_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            logger.info(f"Datei-Deskriptor-Limits angepasst: soft={new_soft}, hard={new_hard}")
        else:
            logger.info("Keine Anpassung der Datei-Deskriptor-Limits notwendig")
    except Exception as e:
        logger.warning(f"Konnte Datei-Deskriptor-Limits nicht anpassen: {e}")

def monitor_file_descriptors():
    """
    Überwacht die aktuelle Anzahl offener Datei-Deskriptoren.
    
    Diese Funktion protokolliert Informationen über aktuelle Ressourcennutzung,
    nützlich für die Diagnose von Ressourcenlecks.
    """
    try:
        process = psutil.Process()
        num_fds = process.num_fds() if hasattr(process, 'num_fds') else 'Nicht verfügbar'
        logger.info(f"Aktuelle Anzahl offener Datei-Deskriptoren: {num_fds}")
        
        # RAM-Nutzung überwachen
        memory_info = process.memory_info()
        logger.info(f"Aktuelle RAM-Nutzung: RSS={memory_info.rss / 1024 / 1024:.2f} MB, VMS={memory_info.vms / 1024 / 1024:.2f} MB")
    except Exception as e:
        logger.warning(f"Fehler bei der Ressourcenüberwachung: {e}")

def cleanup_signal_handler(signum, frame):
    """
    Signal-Handler für saubere Bereinigung beim Beenden.
    
    Diese Funktion wird aufgerufen, wenn das Programm beendet wird,
    und sorgt für eine ordnungsgemäße Ressourcenfreigabe.
    
    Args:
        signum: Die Signalnummer
        frame: Der aktuelle Stack-Frame
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Signal {signum} empfangen, führe Bereinigung durch...")
    
    # Erzwinge Garbage Collection
    gc.collect()
    
    # Schließe alle übrigen Datei-Deskriptoren
    try:
        for fd in range(3, 1024):  # Starte bei 3 (nach stdin, stdout, stderr)
            try:
                os.close(fd)
            except:
                pass
    except Exception as e:
        logger.error(f"Fehler beim Schließen von Datei-Deskriptoren: {e}")
    
    sys.exit(0)

def get_memory_usage():
    """
    Gibt detaillierte Informationen zur aktuellen Speichernutzung zurück.
    
    Returns:
        dict: Ein Dictionary mit Informationen zur Speichernutzung
    """
    try:
        process = psutil.Process()
        memory_info = process.memory_info()
        
        return {
            "rss_mb": memory_info.rss / 1024 / 1024,
            "vms_mb": memory_info.vms / 1024 / 1024,
            "percent": process.memory_percent(),
            "gc_objects": len(gc.get_objects())
        }
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Speichernutzung: {e}")
        return {"error": str(e)} 