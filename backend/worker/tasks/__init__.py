"""
Celery-Tasks für den Worker.
"""
# System-Imports
import logging
from importlib import import_module
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Liste aller Task-Module, die automatisch geladen werden sollen
TASK_MODULES = [
    'tasks.document_tasks',    # Dokumentenverarbeitung
    'tasks.ai_tasks',          # KI-Generierung
    'tasks.maintenance_tasks'  # Wartungsaufgaben
]


def register_tasks(celery_app) -> Dict[str, Any]:
    """
    Registriert alle definierten Tasks mit der Celery-App.

    Args:
        celery_app: Die Celery-App-Instanz.

    Returns:
        dict: Registrierte Tasks und ihre Funktionen.
    """
    registered_tasks = {}

    # Durchgehe alle Task-Module und registriere Tasks
    for module_name in TASK_MODULES:
        try:
            # Importiere das Modul
            module = import_module(module_name)

            # Prüfe, ob das Modul eine register_tasks-Funktion hat
            if hasattr(module, 'register_tasks'):
                module_tasks = module.register_tasks(celery_app)
                registered_tasks.update(module_tasks)
                logger.info("Tasks aus %s registriert: %s", module_name, list(module_tasks.keys()))
            else:
                logger.warning("Modul %s hat keine register_tasks-Funktion", module_name)
        except ImportError as e:
            logger.warning("Konnte Modul %s nicht importieren: %s", module_name, e)
        except Exception as e:
            logger.error("Fehler beim Registrieren von Tasks aus %s: %s", module_name, e)

    # Log-Zusammenfassung
    task_count = len(registered_tasks)
    if task_count > 0:
        logger.info("Insgesamt %s Tasks registriert: %s", task_count, list(registered_tasks.keys()))
    else:
        logger.warning("Keine Tasks registriert!")

    return registered_tasks


# Manueller Import der Haupt-Task-Module, um sicherzustellen, dass sie beim Import verfügbar sind
try:
    from tasks import ai_tasks, document_tasks, maintenance_tasks
except ImportError as e:
    logger.warning("Konnte einige Task-Module nicht importieren: %s", e)
