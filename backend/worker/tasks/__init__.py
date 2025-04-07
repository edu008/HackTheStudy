"""
Task-Modul-Initialisierung.
Registriert alle Tasks für den Worker.
"""
import logging

logger = logging.getLogger(__name__)

def register_tasks(celery_app):
    """
    Registriert alle Tasks aus den Untermodulen für die Celery-App.
    
    Args:
        celery_app: Die Celery-App-Instanz
        
    Returns:
        dict: Dictionary mit allen registrierten Tasks
    """
    all_registered_tasks = {}

    # Importiere und registriere AI-Tasks
    try:
        from .ai_tasks import register_tasks as register_ai_tasks
        ai_tasks_dict = register_ai_tasks(celery_app)
        all_registered_tasks.update(ai_tasks_dict)
        logger.info(f"AI-Tasks erfolgreich registriert: {list(ai_tasks_dict.keys())}")
    except ImportError as e:
        logger.error(f"Fehler beim Importieren/Registrieren der AI-Tasks: {e}")
    except Exception as e:
        logger.error(f"Unerwarteter Fehler beim Registrieren der AI-Tasks: {e}")
    
    # Importiere und registriere Document-Tasks
    try:
        from .document_tasks import register_tasks as register_document_tasks
        document_tasks_dict = register_document_tasks(celery_app)
        all_registered_tasks.update(document_tasks_dict)
        logger.info(f"Document-Tasks erfolgreich registriert: {list(document_tasks_dict.keys())}")
    except ImportError as e:
        logger.error(f"Fehler beim Importieren/Registrieren der Document-Tasks: {e}")
    except Exception as e:
        logger.error(f"Unerwarteter Fehler beim Registrieren der Document-Tasks: {e}")
        
    # Importiere und registriere Maintenance-Tasks
    try:
        from .maintenance_tasks import register_tasks as register_maintenance_tasks
        maintenance_tasks_dict = register_maintenance_tasks(celery_app)
        all_registered_tasks.update(maintenance_tasks_dict)
        logger.info(f"Maintenance-Tasks erfolgreich registriert: {list(maintenance_tasks_dict.keys())}")
    except ImportError as e:
        logger.error(f"Fehler beim Importieren/Registrieren der Maintenance-Tasks: {e}")
    except Exception as e:
        logger.error(f"Unerwarteter Fehler beim Registrieren der Maintenance-Tasks: {e}")
            
    # --- Die redundante Definition von document.process_upload wird entfernt --- 
    # @celery_app.task(name='document.process_upload', bind=True, max_retries=3)
    # def process_upload(self, task_id, file_path, file_type, options=None):
    #     ...
    
    logger.info(f"Gesamtanzahl registrierter Tasks: {len(all_registered_tasks)}")
    return all_registered_tasks

# Optional: Definiere __all__ für explizite Exporte, falls benötigt
# __all__ = ['register_tasks'] 
