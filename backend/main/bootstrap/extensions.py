"""
Flask-Erweiterungen für die Anwendung.
Hier werden alle Erweiterungen zentral initialisiert.
"""

# Importiere die SQLAlchemy-Instanz aus models.py, um keine doppelte Instanz zu haben
from core.models import db
from flask_caching import Cache
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

# Initialisiere weitere Erweiterungen
migrate = Migrate()
cache = Cache()
jwt = JWTManager()
cors = CORS()

# Diese Erweiterungen werden in create_app initialisiert
__all__ = ['db', 'migrate', 'cache', 'jwt', 'cors']
