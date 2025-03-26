"""
Konfigurationsklassen für die Flask-Anwendung.
"""
import os
from datetime import timedelta

class Config:
    """Basis-Konfigurationsklasse für die Flask-Anwendung."""
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-key-please-change-in-production')
    
    # Datenbankverbindung
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Redis-Konfiguration
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://10.244.15.188:6379/0')
    
    # JWT-Konfiguration
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET', 'jwt-secret-key')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    
    # Allgemeine Einstellungen
    API_URL = os.environ.get('API_URL', 'https://api.hackthestudy.ch')
    FRONTEND_URL = os.environ.get('FRONTEND_URL', 'https://www.hackthestudy.ch')
    
    # Log-Level
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')


class DevelopmentConfig(Config):
    """Entwicklungsumgebung-Konfiguration."""
    DEBUG = True
    SQLALCHEMY_ECHO = True
    EXPLAIN_TEMPLATE_LOADING = True


class TestingConfig(Config):
    """Test-Umgebungskonfiguration."""
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


class ProductionConfig(Config):
    """Produktionsumgebungskonfiguration."""
    # Produktionsspezifische Einstellungen
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True

    # ProxyFix-Einstellungen für Reverse-Proxy
    PROXY_FIX_X_FOR = int(os.environ.get('PROXY_FIX_X_FOR', 1))
    PROXY_FIX_X_PROTO = int(os.environ.get('PROXY_FIX_X_PROTO', 1))
    PROXY_FIX_X_HOST = int(os.environ.get('PROXY_FIX_X_HOST', 1))
    PROXY_FIX_X_PORT = int(os.environ.get('PROXY_FIX_X_PORT', 1))
    PROXY_FIX_X_PREFIX = int(os.environ.get('PROXY_FIX_X_PREFIX', 1))


# Konfigurationen in einem Dictionary zusammenfassen
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': ProductionConfig
} 