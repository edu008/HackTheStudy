"""
Umgebungsvariablen-Handler für HackTheStudy

Lädt und verwaltet Umgebungsvariablen aus verschiedenen Quellen.
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
    Ermittelt CORS-Origins aus verschiedenen Umgebungsvariablen und fasst sie zusammen.
    Gibt eine normalisierte Liste von Ursprüngen zurück.
    """
    cors_origins = []
    sources = []
    
    # 1. Prüfe die primäre CORS_ORIGINS Variable
    if 'CORS_ORIGINS' in os.environ:
        raw_origins = os.environ['CORS_ORIGINS']
        # Trenne die Ursprünge anhand von Kommas und entferne führende/nachfolgende Leerzeichen
        origins = [origin.strip() for origin in raw_origins.split(',') if origin.strip()]
        if origins:
            cors_origins.extend(origins)
            sources.append('CORS_ORIGINS')
            logger.info(f"CORS-Origins aus CORS_ORIGINS-Umgebungsvariable: {', '.join(origins)}")
    
    # 2. Prüfe FRONTEND_URL als Fallback
    if 'FRONTEND_URL' in os.environ and os.environ['FRONTEND_URL']:
        frontend_url = os.environ['FRONTEND_URL'].strip()
        if frontend_url and frontend_url not in cors_origins:
            cors_origins.append(frontend_url)
            sources.append('FRONTEND_URL')
            logger.info(f"CORS-Origin aus FRONTEND_URL-Umgebungsvariable: {frontend_url}")
            
            # Füge auch die non-www Version oder www-Version hinzu
            if 'www.' in frontend_url:
                non_www = frontend_url.replace('www.', '')
                if non_www not in cors_origins:
                    cors_origins.append(non_www)
                    logger.info(f"Non-www CORS-Origin hinzugefügt: {non_www}")
            elif frontend_url.startswith('https://') or frontend_url.startswith('http://'):
                protocol = frontend_url.split('://')[0]
                domain = frontend_url.split('://')[1]
                www_version = f"{protocol}://www.{domain}"
                if www_version not in cors_origins:
                    cors_origins.append(www_version)
                    logger.info(f"WWW CORS-Origin hinzugefügt: {www_version}")
                
            # Füge die HTTP/HTTPS-Varianten hinzu
            if frontend_url.startswith('https://'):
                http_version = frontend_url.replace('https://', 'http://')
                if http_version not in cors_origins:
                    cors_origins.append(http_version)
                    logger.info(f"HTTP CORS-Origin hinzugefügt: {http_version}")
            elif frontend_url.startswith('http://'):
                https_version = frontend_url.replace('http://', 'https://')
                if https_version not in cors_origins:
                    cors_origins.append(https_version)
                    logger.info(f"HTTPS CORS-Origin hinzugefügt: {https_version}")
    
    # 3. Füge die API_URL hinzu, falls vorhanden (für lokale Entwicklung nützlich)
    if 'API_URL' in os.environ and os.environ['API_URL']:
        api_url = os.environ['API_URL'].strip()
        if api_url and api_url not in cors_origins:
            cors_origins.append(api_url)
            sources.append('API_URL')
            logger.info(f"CORS-Origin aus API_URL-Umgebungsvariable: {api_url}")
            
    # 4. Füge localhost hinzu für Entwicklungszwecke
    dev_origins = [
        'http://localhost:8080',
        'http://localhost:3000',
        'http://localhost:5000',
        'http://127.0.0.1:8080',
        'http://127.0.0.1:3000',
        'http://127.0.0.1:5000'
    ]
    
    for dev_origin in dev_origins:
        if dev_origin not in cors_origins:
            cors_origins.append(dev_origin)
            logger.info(f"Entwicklungs-CORS-Origin hinzugefügt: {dev_origin}")
    
    # 5. Wenn keine Origins gefunden wurden, füge den Wildcard-Ursprung hinzu (nur für Entwicklung)
    if not cors_origins:
        if os.environ.get('FLASK_ENV') == 'development' or os.environ.get('FLASK_DEBUG') == 'true':
            cors_origins.append('*')
            sources.append('Entwicklungsmodus-Wildcard')
            logger.info("CORS-Wildcard (*) wird im Entwicklungsmodus verwendet")
        else:
            # In Produktion fügen wir eine sichere Standard-Domain hinzu
            cors_origins.append('https://www.hackthestudy.ch')
            sources.append('Produktions-Standard')
            logger.info("Standard-CORS-Origin für Produktion verwendet: https://www.hackthestudy.ch")
    
    # Setze die zusammengeführten Origins zurück in die Umgebungsvariable, 
    # damit andere Teile der Anwendung darauf zugreifen können
    # Verwende Leerzeichen nach den Kommas für bessere Kompatibilität
    os.environ['CORS_ORIGINS'] = ', '.join(cors_origins)
    
    logger.info(f"CORS-Konfiguration abgeschlossen. Quellen: {', '.join(sources)}")
    logger.info(f"Finale CORS-Origins: {os.environ['CORS_ORIGINS']}")
    
    return cors_origins

def load_env(env_file=None):
    """
    Lädt Umgebungsvariablen aus verschiedenen Quellen und setzt Standardwerte wenn nötig.
    Berücksichtigt DigitalOcean App Platform-spezifische Umgebungsvariablen.
    """
    # Standardpfad zur .env-Datei
    if env_file is None:
        env_file = "/app/.env"
    
    # .env-Datei laden, wenn sie existiert
    if Path(env_file).exists():
        logger.info(f"Lade .env-Datei von: {env_file}")
        load_dotenv(env_file)
    else:
        logger.info(f"Keine .env-Datei gefunden unter: {env_file}")
    
    # Standardwerte für kritische Variablen
    env_defaults = {
        "FLASK_APP": "app.py",
        "FLASK_RUN_HOST": "0.0.0.0",
        "FLASK_RUN_PORT": "5000",
        "PORT": "5000",  # DigitalOcean App Platform setzt PORT
        "LOG_LEVEL": "INFO",
        "USE_COLORED_LOGS": "false",
        "REDIS_URL": "redis://localhost:6379/0",
        # URL-Konfigurationen mit endgültigen Domains als Fallback
        "API_URL": "https://api.hackthestudy.ch",
        "FRONTEND_URL": "https://www.hackthestudy.ch",
        # DigitalOcean-spezifische Werte
        "APP_VERSION": "1.0.0"
    }
    
    # Defaultwerte nur setzen, wenn nicht schon als Umgebungsvariable vorhanden
    for key, default_value in env_defaults.items():
        if key not in os.environ:
            os.environ[key] = default_value
            logger.info(f"Setze Standardwert für {key}: {default_value}")
    
    # DigitalOcean App Platform PORT-Handling
    if 'PORT' in os.environ and os.environ.get('PORT') != os.environ.get('FLASK_RUN_PORT'):
        logger.info(f"PORT ({os.environ['PORT']}) und FLASK_RUN_PORT ({os.environ.get('FLASK_RUN_PORT')}) sind unterschiedlich. "
                 f"Setze FLASK_RUN_PORT auf PORT-Wert.")
        os.environ['FLASK_RUN_PORT'] = os.environ['PORT']
    
    # CORS-Origins konfigurieren (zentralisiert)
    setup_cors_origins()
    
    # Wenn DigitalOcean-Proxy verwendet wird, setze Proxy-Variablen
    if os.environ.get('DIGITAL_OCEAN_APP_NAME'):
        os.environ['PROXY_FIX_X_FOR'] = "1"
        os.environ['PROXY_FIX_X_PROTO'] = "1"
        os.environ['PROXY_FIX_X_HOST'] = "1"
        os.environ['PROXY_FIX_X_PORT'] = "1"
        os.environ['PROXY_FIX_X_PREFIX'] = "1"
        logger.info("ProxyFix-Unterstützung für DigitalOcean aktiviert")
    
    # Prüfe auf fehlende kritische Variablen
    critical_envs = ["DATABASE_URL", "JWT_SECRET"]
    missing_envs = [env for env in critical_envs if env not in os.environ]
    
    if missing_envs:
        logger.warning(f"Folgende kritische Umgebungsvariablen fehlen: {', '.join(missing_envs)}")
        logger.warning("Die Anwendung könnte möglicherweise nicht korrekt funktionieren!")
    
    return os.environ

def log_env_vars(censor_sensitive=True):
    """
    Protokolliert alle relevanten Umgebungsvariablen, zensiert sensible Daten.
    """
    logger.info("Aktuelle Umgebungsvariablen (sensible Daten zensiert):")
    for key, value in sorted(os.environ.items()):
        # Zeige keine Systemvariablen
        if key.startswith(("PATH", "PS", "TERM", "HOME", "USER", "_", "LS_")):
            continue
            
        # Zensiere sensible Werte
        if censor_sensitive and any(secret in key.lower() for secret in ["key", "secret", "password", "token", "url"]):
            censored_value = value[:3] + "***" if len(value) > 3 else "***"
            logger.info(f"{key}={censored_value}")
        else:
            logger.info(f"{key}={value}")

if __name__ == "__main__":
    # Wenn dieses Skript direkt ausgeführt wird
    # Logging konfigurieren
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
    
    load_env()
    log_env_vars() 