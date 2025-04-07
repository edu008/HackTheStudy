"""
Flask-Erweiterungen für die Anwendung.
Hier werden alle Erweiterungen zentral initialisiert.
"""

import os
from core.models import db
from flask_caching import Cache
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

# JWT-Secret aus Umgebungsvariablen holen
jwt_secret = os.environ.get('JWT_SECRET_KEY', os.environ.get('JWT_SECRET', 'dev-secret-key'))

# Initialisiere weitere Erweiterungen
migrate = Migrate()
cache = Cache()
jwt = JWTManager()
cors = CORS()

# Secret-Key direkt im JWT-Manager setzen (anstatt durch app.config)
if jwt_secret:
    jwt._secret_key = jwt_secret

# Diese Erweiterungen werden in create_app initialisiert
__all__ = ['db', 'migrate', 'cache', 'jwt', 'cors']
