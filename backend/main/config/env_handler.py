"""
Umgebungsvariablen-Handler für HackTheStudy

Lädt und verwaltet Umgebungsvariablen aus verschiedenen Quellen.
Optimiert für DigitalOcean App Platform.
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Logger für dieses Modul konfigurieren
logger = logging.getLogger('HackTheStudy.config.env_handler')

def setup_cors_origins():
    """
    Ermittelt CORS-Origins aus verschiedenen Umgebungsvariablen.
    Diese Funktion wird beibehalten für API-Logging und Umgebungsvariablen-Setzung,
    aber die eigentliche CORS-Konfiguration erfolgt in app_factory.py.
    """
    # Hinweis: Wir geben immer '*' zurück, aber behalten die Funktion für Logging-Zwecke bei
    logger.info("CORS verwendet jetzt Wildcard-Origin (*) für alle API-Aufrufe")
    
    # Setze die CORS_ORIGINS Umgebungsvariable für andere Komponenten
    os.environ['CORS_ORIGINS'] = '*'
    
    return ['*']

def load_env(env_file=None):
    """
    Lädt Umgebungsvariablen aus verschiedenen Quellen und setzt Standardwerte wenn nötig.
    Optimiert für DigitalOcean App Platform - vermeidet unnötige .env-Dateisuche in Produktion.
    """
    # Prüfe, ob wir in einer DigitalOcean oder Produktionsumgebung sind
    is_digital_ocean = bool(os.environ.get('DIGITAL_OCEAN_APP_NAME'))
    is_production = os.environ.get('ENVIRONMENT', 'production').lower() == 'production'
    
    # .env-Datei nur in Entwicklungsumgebung laden
    if not is_production and not is_digital_ocean:
        # Standardpfad zur .env-Datei
        if env_file is None:
            # Prüfe zunächst im aktuellen Verzeichnis
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            env_file = os.path.join(current_dir, '.env')
        
        # .env-Datei laden, wenn sie existiert
        if Path(env_file).exists():
            logger.info(f"✅ Lade .env-Datei von: {env_file}")
            load_dotenv(env_file)
        else:
            logger.info(f"⚠️ Keine .env-Datei gefunden unter: {env_file} - verwende Umgebungsvariablen")
    else:
        logger.info("🚀 Produktionsumgebung erkannt - verwende DigitalOcean Umgebungsvariablen")
    
    # Standardwerte für kritische Variablen (nur wenn nicht gesetzt)
    env_defaults = {
        "FLASK_APP": "app.py",
        "FLASK_RUN_HOST": "0.0.0.0",
        "PORT": "8080" if is_digital_ocean else "5000",
        "LOG_LEVEL": "INFO",
        "REDIS_URL": "redis://localhost:6379/0",
        "API_URL": "https://api.hackthestudy.ch" if is_production else "http://localhost:8080",
    }
    
    # Defaultwerte nur setzen, wenn nicht schon als Umgebungsvariable vorhanden
    for key, default_value in env_defaults.items():
        if key not in os.environ:
            os.environ[key] = default_value
            logger.info(f"⚙️ Standardwert für {key}: {default_value}")
    
    # CORS-Origins konfigurieren (zentralisiert)
    setup_cors_origins()
    
    # Wenn DigitalOcean-Proxy verwendet wird, setze Proxy-Variablen
    if is_digital_ocean:
        proxy_settings = {
            'PROXY_FIX_X_FOR': "1",
            'PROXY_FIX_X_PROTO': "1",
            'PROXY_FIX_X_HOST': "1",
            'PROXY_FIX_X_PORT': "1",
            'PROXY_FIX_X_PREFIX': "1"
        }
        
        for key, value in proxy_settings.items():
            if key not in os.environ:
                os.environ[key] = value
        
        logger.info("🔄 ProxyFix-Unterstützung für DigitalOcean aktiviert")
    
    return os.environ

def log_env_vars(censor_sensitive=True):
    """
    Protokolliert alle relevanten Umgebungsvariablen, zensiert sensible Daten.
    Optimiert für strukturierte Ausgabe.
    """
    # Wichtige Variablenkategorien
    categories = {
        "Plattform": ["ENVIRONMENT", "DIGITAL_OCEAN_APP_NAME", "CONTAINER_TYPE", "RUN_MODE"],
        "Netzwerk": ["PORT", "FLASK_RUN_HOST", "FLASK_RUN_PORT", "API_URL", "FRONTEND_URL"],
        "Datenbank": ["DATABASE_URL", "POSTGRES_HOST", "POSTGRES_PORT"],
        "Sicherheit": ["FLASK_DEBUG", "JWT_SECRET"],
        "Redis": ["REDIS_URL", "REDIS_HOST"],
        "API": ["OPENAI_API_KEY", "STRIPE_API_KEY", "OPENAI_MODEL"]
    }
    
    logger.info("🔍 Umgebungsvariablen nach Kategorien:")
    
    for category, keys in categories.items():
        found_keys = []
        for key in keys:
            if key in os.environ:
                value = os.environ[key]
                # Zensiere sensible Werte
                if censor_sensitive and any(secret in key.lower() for secret in ["key", "secret", "password", "token", "database_url"]):
                    if len(value) > 8:
                        censored_value = value[:4] + "****" + value[-4:]
                    else:
                        censored_value = "********"
                    found_keys.append(f"{key}={censored_value}")
                else:
                    found_keys.append(f"{key}={value}")
        
        if found_keys:
            logger.info(f"📋 {category}: {', '.join(found_keys)}")

if __name__ == "__main__":
    # Wenn dieses Skript direkt ausgeführt wird
    # Logging konfigurieren
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
    
    load_env()
    log_env_vars() 