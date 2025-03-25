"""
Minimale Modeldefinitionen für den Worker-Microservice.
Diese Datei enthält einfache Stubklassen, die als Ersatz für die vollständigen 
Modelle im Hauptserver dienen.
"""
import logging

logger = logging.getLogger(__name__)
logger.info("Worker-spezifische models.py geladen")

# Minimaler SQLAlchemy DB-Stub
class DummyDB:
    """
    Dummy-DB-Klasse für den Worker, der keine vollständige DB-Verbindung benötigt.
    """
    def init_app(self, app):
        logger.info("Dummy DB-Initialisierer aufgerufen")
        pass

    def create_all(self):
        logger.info("Dummy create_all aufgerufen")
        pass

# Erstelle eine Dummy-Instanz
db = DummyDB()

# Grundlegende Modeldefinitionen, die der Worker benötigen könnte
class User:
    """Dummy User-Klasse für Worker-Tasks, die User-Informationen benötigen."""
    id = None
    username = None
    email = None
    
    def __init__(self, id=None, username=None, email=None):
        self.id = id
        self.username = username
        self.email = email

class Task:
    """Dummy Task-Klasse für Worker-Tasks, die Task-Informationen benötigen."""
    id = None
    name = None
    status = None
    user_id = None
    
    def __init__(self, id=None, name=None, status="pending", user_id=None):
        self.id = id
        self.name = name
        self.status = status
        self.user_id = user_id

# Hilfsfunktionen zum Simulieren von DB-Operationen
def get_dummy_user(user_id):
    """
    Gibt einen Dummy-User zurück.
    """
    return User(id=user_id, username=f"user_{user_id}", email=f"user_{user_id}@example.com")

def get_dummy_task(task_id):
    """
    Gibt einen Dummy-Task zurück.
    """
    return Task(id=task_id, name=f"task_{task_id}", status="pending", user_id=1) 