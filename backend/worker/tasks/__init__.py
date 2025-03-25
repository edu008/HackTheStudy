"""
Task-Definitionen für den Worker-Microservice
"""
from backend.worker.tasks.process_upload import register_task as register_process_upload
from backend.worker.tasks.api_request import register_task as register_api_request

def register_tasks(celery_app):
    """
    Registriert alle verfügbaren Tasks bei der Celery-App.
    
    Args:
        celery_app: Die Celery-App-Instanz
    """
    # Registriere die process_upload Task
    process_upload = register_process_upload(celery_app)
    
    # Registriere die process_api_request Task
    process_api_request = register_api_request(celery_app)
    
    # Hier können weitere Tasks registriert werden...
    
    # Gib die registrierten Tasks zurück
    return {
        'process_upload': process_upload,
        'process_api_request': process_api_request
    }

__all__ = ['register_tasks'] 