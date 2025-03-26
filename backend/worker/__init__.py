"""
HackTheStudy Worker Microservice
"""

__version__ = '1.0.0'

# Deklarative Exporte - die tatsächlichen Importe erfolgen erst, wenn sie verwendet werden
# Dies verhindert Zirkularimporte beim Starten
__all__ = ['celery_app', 'initialize_worker']

# Stelle celery_app und initialize_worker als Importvariablen bereit
# Diese werden erst geladen, wenn sie tatsächlich importiert werden
celery_app = None
initialize_worker = None

def _load_app():
    """Lade die App-Module bei Bedarf"""
    global celery_app, initialize_worker
    try:
        # Importiere erst, wenn benötigt
        from app import celery_app as _celery_app, initialize_worker as _initialize_worker
        celery_app = _celery_app
        initialize_worker = _initialize_worker
        return True
    except ImportError:
        # Falls app.py noch nicht existiert oder nicht korrekt ist
        return False 