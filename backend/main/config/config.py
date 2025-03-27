"""
Konfigurationsmodul für die HackTheStudy-Backend-Anwendung.
Vereint die Funktionalität aus app_config.py und env_handler.py.
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from typing import Dict, List, Any, Optional, Union

# Standardlogger für dieses Modul konfigurieren (wird später ordnungsgemäß initialisiert)
logger = logging.getLogger('HackTheStudy.config')

# Flag für Logging-Initialisierung
LOGGING_INITIALIZED = False

class LoggingManager:
    """
    Zentrale Klasse für die Verwaltung aller Logging-Funktionalitäten.
    Vereinheitlicht die Logging-Konfiguration und bietet strukturiertes Logging.
    """
    
    # Singleton-Instanz
    _instance = None
    
    def __new__(cls):
        """Stellt sicher, dass nur eine Instanz existiert (Singleton)."""
        if cls._instance is None:
            cls._instance = super(LoggingManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialisiert den Logging-Manager."""
        if self._initialized:
            return
            
        # Basiseinstellungen
        self.log_level_str = os.environ.get('LOG_LEVEL', 'INFO')
        self.log_level = getattr(logging, self.log_level_str.upper(), logging.INFO)
        self.log_prefix = os.environ.get('LOG_PREFIX', '[API] ')
        self.log_api_requests = os.environ.get('LOG_API_REQUESTS', 'true').lower() == 'true'
        self.run_mode = os.environ.get('RUN_MODE', 'app')
        
        # Logger-Cache
        self._loggers = {}
        
        # Initialisierungsstatus
        self._initialized = True
    
    def setup_logging(self) -> logging.Logger:
        """
        Konfiguriert das Logging-System für die Anwendung.
        
        Returns:
            Logger-Instanz
        """
        global LOGGING_INITIALIZED
        
        # Vermeidet mehrfache Initialisierung
        if LOGGING_INITIALIZED:
            return logging.getLogger('HackTheStudy.app')
        
        # Deaktiviere Pufferung für stdout und stderr
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(line_buffering=True)
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(line_buffering=True)
        
        # Entferne alle bestehenden Handler
        root_logger = logging.getLogger()
        if root_logger.handlers:
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)

        # Angepasstes Logformat mit Präfix
        log_format = f'{self.log_prefix}[%(levelname)s] %(name)s: %(message)s'
        
        # Konfiguriere das Logging-System mit verbessertem Format
        logging.basicConfig(
            level=self.log_level,
            format=log_format,
            handlers=[
                logging.StreamHandler(sys.stdout)
            ],
            force=True
        )
        
        # Logger mit Modul-Namen erstellen
        logger = logging.getLogger('HackTheStudy.app')
        logger.setLevel(self.log_level)
        
        # Verhindere Weiterleitung der Logs an den Root-Logger
        logger.propagate = False
        
        # Spezifische Logger konfigurieren mit gleicher Formatierung
        special_loggers = [
            'openai', 'api.openai_client', 'celery', 'celery.task',
            'werkzeug', 'flask', 'gunicorn', 'gunicorn.error', 'gunicorn.access',
            'openai_api'  # Logger für OpenAI API Anfragen und Antworten
        ]
        
        # Gemeinsamer Handler mit einheitlicher Formatierung
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(log_format)
        handler.setFormatter(formatter)
        
        # Benutzeranpassbare Filterlogik basierend auf RUN_MODE
        if self.run_mode == 'worker':
            # Im Worker-Modus nur Worker-relevante Logger aktivieren
            active_loggers = ['celery', 'celery.task', 'api.openai_client']
            if self.log_api_requests:
                active_loggers.append('api_requests')  # Für API-Anfragen im Worker
            
            for logger_name in special_loggers:
                custom_logger = logging.getLogger(logger_name)
                if logger_name in active_loggers:
                    custom_logger.setLevel(self.log_level)
                else:
                    custom_logger.setLevel(logging.WARNING)  # Andere Logger stumm schalten
                
                # Entferne bestehende Handler
                if custom_logger.handlers:
                    for h in custom_logger.handlers[:]:
                        custom_logger.removeHandler(h)
                
                # Verhindere Weiterleitung an den Root-Logger
                custom_logger.propagate = False
                
                # Füge einheitlichen Handler hinzu
                custom_logger.addHandler(handler)
        else:
            # Im App-Modus normale Konfiguration
            for logger_name in special_loggers:
                custom_logger = logging.getLogger(logger_name)
                custom_logger.setLevel(self.log_level)
                
                # Entferne bestehende Handler
                if custom_logger.handlers:
                    for h in custom_logger.handlers[:]:
                        custom_logger.removeHandler(h)
                
                # Verhindere Weiterleitung an den Root-Logger
                custom_logger.propagate = False
                
                # Füge einheitlichen Handler hinzu
                custom_logger.addHandler(handler)
        
        # API-Request-Logger erstellen
        api_logger = logging.getLogger('api_requests')
        api_logger.setLevel(self.log_level if self.log_api_requests else logging.WARNING)
        api_logger.propagate = False
        api_handler = logging.StreamHandler(sys.stdout)
        api_handler.setFormatter(formatter)
        api_logger.addHandler(api_handler)
        
        # Flag setzen
        LOGGING_INITIALIZED = True
        
        logger.info("Logging-System erfolgreich initialisiert")
        return logger
    
    def force_flush_handlers(self):
        """
        Erzwingt das Leeren aller Log-Handler-Puffer.
        Nützlich vor einem geordneten Shutdown.
        """
        for name, logger in logging.root.manager.loggerDict.items():
            if isinstance(logger, logging.Logger):
                for handler in logger.handlers:
                    if hasattr(handler, 'flush'):
                        try:
                            handler.flush()
                        except:
                            pass
        
        # Auch die Handler des Root-Loggers leeren
        for handler in logging.root.handlers:
            if hasattr(handler, 'flush'):
                try:
                    handler.flush()
                except:
                    pass
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        Gibt einen konfigurierten Logger zurück.
        
        Args:
            name: Name des Loggers
            
        Returns:
            Logger-Instanz
        """
        if name in self._loggers:
            return self._loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(self.log_level)
        
        # Handler hinzufügen, falls noch nicht vorhanden
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter(f'{self.log_prefix}[%(levelname)s] %(name)s: %(message)s'))
            logger.addHandler(handler)
        
        # Keine Weiterleitung an den Root-Logger
        logger.propagate = False
        
        # Im Cache speichern
        self._loggers[name] = logger
        
        return logger
    
    def structured_log(self, level: str, message: str, session_id: Optional[str] = None, 
                     component: Optional[str] = None, **extra):
        """
        Erzeugt strukturierte Logs im JSON-Format für bessere Analysierbarkeit.
        
        Args:
            level: Log-Level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: Log-Nachricht
            session_id: Session-ID (optional)
            component: Komponente (optional)
            **extra: Weitere Attribute für das Log
        """
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "component": component or "backend"
        }
        
        # Wichtige Kontext-Informationen
        if session_id:
            log_data["session_id"] = session_id
            
        # Weitere Attribute hinzufügen
        log_data.update(extra)
        
        # Logger mit passendem Level aufrufen
        log_message = json.dumps(log_data)
        logger = self.get_logger(log_data.get("component", "backend"))
        
        if level == "DEBUG":
            logger.debug(log_message)
        elif level == "INFO":
            logger.info(log_message)
        elif level == "WARNING":
            logger.warning(log_message)
        elif level == "ERROR":
            logger.error(log_message)
        elif level == "CRITICAL":
            logger.critical(log_message)
    
    def track_session_progress(self, session_id: str, progress_percent: int, 
                             message: str, stage: str = "processing"):
        """
        Session-Fortschritt aktualisieren mit Logging.
        
        Args:
            session_id: Session-ID
            progress_percent: Fortschritt in Prozent
            message: Fortschrittsnachricht
            stage: Verarbeitungsstufe
        """
        from core.redis_client import redis_client
        
        details = {
            "stage": stage,
            "message": message,
            "progress": progress_percent,
            "timestamp": time.time()
        }
        
        # In Redis speichern
        redis_client.set(f"processing_progress:{session_id}", json.dumps(details), ex=3600)
        redis_client.set(f"processing_status:{session_id}", stage, ex=3600)
        
        # In Logs schreiben
        self.structured_log(
            "INFO",
            f"Session {session_id}: {message} ({progress_percent}%)",
            session_id=session_id,
            component="progress_tracker",
            progress=progress_percent,
            stage=stage
        )
    
    def track_error(self, session_id: str, error_type: str, message: str, 
                  trace: Optional[str] = None, diagnostics: Optional[Dict] = None):
        """
        Fehler mit strukturiertem Logging und Redis-Speicherung.
        
        Args:
            session_id: Session-ID
            error_type: Fehlertyp
            message: Fehlermeldung
            trace: Stacktrace (optional)
            diagnostics: Diagnosedaten (optional)
        """
        from core.redis_client import redis_client
        
        # Bereinige Traceback für Logs
        if trace and len(trace) > 1500:
            trace_preview = trace[:700] + "\n...[gekürzt]...\n" + trace[-700:]
        else:
            trace_preview = trace
            
        # Log erstellen
        self.structured_log(
            "ERROR",
            f"Fehler in Session {session_id}: {message}",
            session_id=session_id,
            component="error_handler",
            error_type=error_type,
            trace_preview=trace_preview[:200] + "..." if trace_preview and len(trace_preview) > 200 else trace_preview
        )
        
        # Kompletten Fehler in Redis speichern
        error_data = {
            "error_type": error_type,
            "message": message,
            "timestamp": time.time()
        }
        
        if trace:
            error_data["trace"] = trace
            
        if diagnostics:
            error_data["diagnostics"] = diagnostics
            
        # In Redis speichern für Frontend-Zugriff
        redis_client.set(f"error_details:{session_id}", json.dumps(error_data), ex=3600)
        redis_client.set(f"processing_status:{session_id}", "error", ex=3600)

class AppConfig:
    """
    Zentrale Konfigurationsklasse für die HackTheStudy-Anwendung.
    Lädt und verwaltet Umgebungsvariablen, setzt Standardwerte und stellt
    Konfigurationsparameter für verschiedene Umgebungen bereit.
    """
    
    # Singleton-Instanz
    _instance = None
    
    def __new__(cls):
        """Stellt sicher, dass nur eine Instanz existiert (Singleton)."""
        if cls._instance is None:
            cls._instance = super(AppConfig, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialisiert die Konfigurationsinstanz, wenn sie noch nicht initialisiert wurde."""
        if self._initialized:
            return
            
        # Umgebungsvariablen laden
        self.load_env()
        
        # Umgebung ermitteln
        self.environment = os.environ.get('ENVIRONMENT', 'production').lower()
        self.is_production = self.environment == 'production'
        self.is_development = self.environment == 'development'
        self.is_testing = self.environment == 'testing'
        self.is_digital_ocean = bool(os.environ.get('DIGITAL_OCEAN_APP_NAME'))
        
        # Basiseinstellungen
        self.debug = self.is_development or os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
        self.testing = self.is_testing
        self.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-key-please-change-in-production')
        
        # Datenbankverbindung
        self.database_url = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
        self.track_modifications = False
        
        # Redis-Konfiguration
        self.redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        
        # JWT-Konfiguration
        self.jwt_secret_key = os.environ.get('JWT_SECRET', 'jwt-secret-key')
        self.jwt_access_token_expires = timedelta(hours=1)
        self.jwt_refresh_token_expires = timedelta(days=30)
        
        # Allgemeine Einstellungen
        self.api_url = os.environ.get('API_URL', 'https://api.hackthestudy.ch' if self.is_production else 'http://localhost:8080')
        self.frontend_url = os.environ.get('FRONTEND_URL', 'https://www.hackthestudy.ch')
        self.port = int(os.environ.get('PORT', 8080 if self.is_digital_ocean else 5000))
        self.host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
        
        # Log-Level
        self.log_level = os.environ.get('LOG_LEVEL', 'INFO')
        
        # Logging-Manager initialisieren
        self.logging_manager = LoggingManager()
        
        # Produktionsspezifische Einstellungen
        if self.is_production:
            self.session_cookie_secure = True
            self.remember_cookie_secure = True
            self.session_cookie_httponly = True
            self.remember_cookie_httponly = True
            
            # ProxyFix-Einstellungen für Reverse-Proxy
            self.proxy_fix_x_for = int(os.environ.get('PROXY_FIX_X_FOR', 1))
            self.proxy_fix_x_proto = int(os.environ.get('PROXY_FIX_X_PROTO', 1))
            self.proxy_fix_x_host = int(os.environ.get('PROXY_FIX_X_HOST', 1))
            self.proxy_fix_x_port = int(os.environ.get('PROXY_FIX_X_PORT', 1))
            self.proxy_fix_x_prefix = int(os.environ.get('PROXY_FIX_X_PREFIX', 1))
        
        # Entwicklungsspezifische Einstellungen
        if self.is_development:
            self.sqlalchemy_echo = True
            self.explain_template_loading = True
        
        # Flask-Konfiguration für verschiedene Umgebungen
        self.flask_config = self.get_flask_config()
        
        # Umgebungsvariablen protokollieren, wenn gewünscht
        if os.environ.get('LOG_ENV_VARS', 'false').lower() == 'true':
            self.log_env_vars()
        
        # Initialisierung abgeschlossen
        self._initialized = True
    
    def load_env(self, env_file: Optional[str] = None) -> Dict[str, str]:
        """
        Lädt Umgebungsvariablen aus verschiedenen Quellen und setzt Standardwerte wenn nötig.
        Optimiert für DigitalOcean App Platform - vermeidet unnötige .env-Dateisuche in Produktion.
        
        Args:
            env_file: Optionaler Pfad zur .env-Datei
            
        Returns:
            Umgebungsvariablen als Dictionary
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
            "CORS_ORIGINS": "*"  # Verwende Wildcard-Origin für alle API-Aufrufe
        }
        
        # Defaultwerte nur setzen, wenn nicht schon als Umgebungsvariable vorhanden
        for key, default_value in env_defaults.items():
            if key not in os.environ:
                os.environ[key] = default_value
                logger.info(f"⚙️ Standardwert für {key}: {default_value}")
        
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
    
    def get_flask_config(self) -> Dict[str, Any]:
        """
        Erstellt ein Konfigurations-Dictionary für Flask basierend auf der aktuellen Umgebung.
        
        Returns:
            Flask-Konfigurationsdictionary
        """
        config = {
            'DEBUG': self.debug,
            'TESTING': self.testing,
            'SECRET_KEY': self.secret_key,
            'SQLALCHEMY_DATABASE_URI': self.database_url,
            'SQLALCHEMY_TRACK_MODIFICATIONS': self.track_modifications,
            'JWT_SECRET_KEY': self.jwt_secret_key,
            'JWT_ACCESS_TOKEN_EXPIRES': self.jwt_access_token_expires,
            'JWT_REFRESH_TOKEN_EXPIRES': self.jwt_refresh_token_expires
        }
        
        # Produktionsspezifische Konfiguration
        if self.is_production:
            config.update({
                'SESSION_COOKIE_SECURE': True,
                'REMEMBER_COOKIE_SECURE': True,
                'SESSION_COOKIE_HTTPONLY': True,
                'REMEMBER_COOKIE_HTTPONLY': True
            })
        
        # Entwicklungsspezifische Konfiguration
        if self.is_development:
            config.update({
                'SQLALCHEMY_ECHO': True,
                'EXPLAIN_TEMPLATE_LOADING': True
            })
        
        return config
    
    def setup_cors_origins(self) -> List[str]:
        """
        Ermittelt CORS-Origins aus verschiedenen Umgebungsvariablen.
        
        Returns:
            Liste mit erlaubten Origins
        """
        # Wir erlauben immer alle Origins
        logger.info("CORS verwendet Wildcard-Origin (*) für alle API-Aufrufe")
        return ['*']
    
    def log_env_vars(self, censor_sensitive: bool = True) -> None:
        """
        Protokolliert alle relevanten Umgebungsvariablen, zensiert sensible Daten.
        
        Args:
            censor_sensitive: Ob sensible Daten zensiert werden sollen
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
    
    def setup_logging(self) -> logging.Logger:
        """
        Konfiguriert das Logging-System für die Anwendung.
        
        Returns:
            Logger-Instanz
        """
        return self.logging_manager.setup_logging()
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        Gibt einen konfigurierten Logger zurück.
        
        Args:
            name: Name des Loggers
            
        Returns:
            Logger-Instanz
        """
        return self.logging_manager.get_logger(name)
    
    def structured_log(self, level: str, message: str, **kwargs):
        """
        Erzeugt strukturierte Logs im JSON-Format.
        
        Args:
            level: Log-Level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: Log-Nachricht
            **kwargs: Weitere Attribute für das Log
        """
        self.logging_manager.structured_log(level, message, **kwargs)
    
    def track_session_progress(self, session_id: str, progress_percent: int, 
                              message: str, stage: str = "processing"):
        """
        Session-Fortschritt aktualisieren mit Logging.
        
        Args:
            session_id: Session-ID
            progress_percent: Fortschritt in Prozent
            message: Fortschrittsnachricht
            stage: Verarbeitungsstufe
        """
        self.logging_manager.track_session_progress(session_id, progress_percent, message, stage)
    
    def track_error(self, session_id: str, error_type: str, message: str, 
                   trace: Optional[str] = None, diagnostics: Optional[Dict] = None):
        """
        Fehler mit strukturiertem Logging und Redis-Speicherung.
        
        Args:
            session_id: Session-ID
            error_type: Fehlertyp
            message: Fehlermeldung
            trace: Stacktrace (optional)
            diagnostics: Diagnosedaten (optional)
        """
        self.logging_manager.track_error(session_id, error_type, message, trace, diagnostics)
    
    def force_flush_handlers(self):
        """
        Erzwingt das Leeren aller Log-Handler-Puffer.
        
        Nützlich vor einem geordneten Shutdown.
        """
        self.logging_manager.force_flush_handlers()

# Zentrale Konfigurationsinstanz
config = AppConfig()

# Konfiguriere den Logger des Konfigurationsmoduls neu, nachdem die Konfiguration eingerichtet wurde
logger = logging.getLogger('HackTheStudy.config') 