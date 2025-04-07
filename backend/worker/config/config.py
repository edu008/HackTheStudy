"""
Zentrale Konfiguration für den Worker.

Dieses Modul stellt Konfigurationswerte und Funktionen bereit.
"""
import os
import logging
import logging.config
import sys
from typing import Dict, Any, Optional
from urllib.parse import urlparse # Import für URL-Parsing

# Logger auf Modulebene definieren
logger = logging.getLogger(__name__)

# Basisverzeichnis des Workers - relativ zum Speicherort dieser Datei
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class WorkerConfig:
    """Zentrale Konfigurationsklasse für den Worker."""
    
    def __init__(self):
        """Initialisiert die Konfiguration aus Umgebungsvariablen und Dateien."""
        # Umgebung bestimmen (Standard: 'dev')
        self.umgebung = os.environ.get('UMGEBUNG', 'dev').lower()
        print(f"Konfiguration: Lade Einstellungen für Umgebung: '{self.umgebung}'")
        logger.info(f"Lade Konfiguration für Umgebung: {self.umgebung}")

        # --- Datenbank-Konfiguration ---
        db_url_env = os.environ.get("DATABASE_URL")
        local_db_default = "postgresql://postgres:YOUR_LOCAL_PASSWORD@localhost:5432/hackthestudy" 

        if self.umgebung == 'prod':
            if db_url_env:
                self.database_url = db_url_env
                print(f"Datenbank-Konfiguration (prod): Verwende DATABASE_URL aus Umgebung: {self.database_url[:30]}...")
                logger.info("Verwende DATABASE_URL aus Umgebungsvariable (prod).")
            else:
                logger.error("FATAL: DATABASE_URL nicht in Produktionsumgebung gefunden!")
                # Hier sollte ggf. ein Fehler ausgelöst oder ein Exit erfolgen
                self.database_url = None # Setze auf None, um Fehler zu signalisieren
        else: # dev oder anderer Wert
            if db_url_env:
                 self.database_url = db_url_env
                 print(f"Datenbank-Konfiguration (dev): Verwende DATABASE_URL aus Umgebung/lokaler .env: {self.database_url[:30]}...")
                 logger.info("Verwende DATABASE_URL aus Umgebung/lokaler .env (dev).")
            else:
                self.database_url = local_db_default
                print(f"Datenbank-Konfiguration (dev): Verwende lokalen Default: {self.database_url}")
                logger.warning(f"DATABASE_URL nicht in Umgebungsvariablen gefunden. Verwende lokalen Default (dev): {self.database_url}")
        
        if not self.database_url:
             logger.error("Datenbank-URL konnte nicht ermittelt werden.")

        # --- Redis-Konfiguration ---
        redis_url_env = os.environ.get('REDIS_URL')
        local_redis_host = os.environ.get('REDIS_HOST', 'localhost') # Default für lokal
        local_redis_port = os.environ.get('REDIS_PORT', '6379')
        local_redis_password = os.environ.get('REDIS_PASSWORD') # Kein Default für lokales Passwort
        local_redis_db = os.environ.get('REDIS_DB', '0')
        
        if self.umgebung == 'prod':
            if redis_url_env:
                self.redis_url = redis_url_env
                log_redis_url = self._mask_redis_password(self.redis_url)
                print(f"Redis-Konfiguration (prod): Verwende REDIS_URL aus Umgebung: {log_redis_url}")
                logger.info(f"Verwende REDIS_URL aus Umgebungsvariable (prod).")
                self._parse_redis_url() # Extrahiere Host/Port etc. aus URL
            else:
                logger.error("FATAL: REDIS_URL nicht in Produktionsumgebung gefunden!")
                self.redis_url = None
                self.redis_host = None
        else: # dev oder anderer Wert
            if redis_url_env:
                 self.redis_url = redis_url_env
                 log_redis_url = self._mask_redis_password(self.redis_url)
                 print(f"Redis-Konfiguration (dev): Verwende REDIS_URL aus Umgebung/lokaler .env: {log_redis_url}")
                 logger.info("Verwende REDIS_URL aus Umgebung/lokaler .env (dev).")
                 self._parse_redis_url()
            else:
                # Baue lokale URL zusammen
                logger.warning("REDIS_URL nicht gesetzt, baue aus lokalen Defaults/Env-Vars (dev).")
                self.redis_host = local_redis_host
                self.redis_port = local_redis_port
                self.redis_password = local_redis_password
                self.redis_db = local_redis_db
                pw_part = f":{self.redis_password}@" if self.redis_password else ""
                self.redis_url = f"redis://{pw_part}{self.redis_host}:{self.redis_port}/{self.redis_db}"
                log_redis_url = self._mask_redis_password(self.redis_url)
                print(f"Redis-Konfiguration (dev): Verwende lokale Defaults/Env-Vars: {log_redis_url}")
                logger.info(f"Verwende lokale Redis-Konfiguration. Host: {self.redis_host}")

        if not self.redis_url:
             logger.error("Redis-URL konnte nicht ermittelt werden.")

        # API-Konfiguration (kann meist Standard bleiben oder spezifisch gesetzt werden)
        self.api_url = os.environ.get("API_URL", "http://localhost:8080") # Default auf Main API Port
        self.api_key = os.environ.get("API_KEY", "")

        # OpenAI-Konfiguration (API Key MUSS über Env Var/Secret kommen)
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not self.openai_api_key:
             logger.warning("OPENAI_API_KEY nicht gefunden! OpenAI-Funktionen werden fehlschlagen.")
        self.openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o")

        # Worker-Konfiguration
        self.worker_concurrency = int(os.environ.get("WORKER_CONCURRENCY", "1" if self.umgebung == 'dev' else "4")) # Default je nach Env
        self.worker_prefetch_multiplier = int(os.environ.get("CELERY_WORKER_PREFETCH_MULTIPLIER", "1"))
        self.worker_max_tasks_per_child = int(os.environ.get("CELERY_MAX_TASKS_PER_CHILD", "10"))
        # Celery Pool (optional, Default ist prefork)
        self.celery_pool = os.environ.get("CELERY_POOL", "prefork") 

        # Logging-Konfiguration
        self.logging_level = os.environ.get("LOGGING_LEVEL", "DEBUG" if self.umgebung == 'dev' else "INFO") # Default je nach Env
        self.logging_format = os.environ.get(
            "LOGGING_FORMAT", 
            "[%(asctime)s] [%(levelname)s] [%(name)s.%(funcName)s:%(lineno)d] %(message)s"
        )
        
        # Python-Pfad-Konfiguration
        self._configure_python_path()
    
    def _parse_redis_url(self):
        """Hilfsmethode zum Parsen der Redis URL."""
        if not self.redis_url:
            return
        try:
            parsed = urlparse(self.redis_url)
            self.redis_host = parsed.hostname
            self.redis_port = parsed.port or 6379
            self.redis_password = parsed.password
            db_path = parsed.path
            self.redis_db = db_path.lstrip('/') if db_path else '0'
            logger.info(f"Redis URL geparst: Host={self.redis_host}, Port={self.redis_port}, DB={self.redis_db}")
        except Exception as e:
            logger.warning(f"Konnte Redis URL nicht vollständig parsen ('{self.redis_url}'): {e}")
            # Setze einige Attribute auf Defaults, wenn Parsen fehlschlägt
            if not hasattr(self, 'redis_host') or not self.redis_host:
                 self.redis_host = "unknown_host_from_url"
            if not hasattr(self, 'redis_port') or not self.redis_port:
                 self.redis_port = 6379
            if not hasattr(self, 'redis_db') or not self.redis_db:
                 self.redis_db = "0"

    def _mask_redis_password(self, url: Optional[str]) -> str:
        """Maskiert das Passwort in einer Redis URL für Log-Ausgaben."""
        if not url:
            return "N/A"
        try:
            parsed = urlparse(url)
            if parsed.password:
                return url.replace(f":{parsed.password}@", ":****@")
            return url
        except Exception:
            return "Error masking URL"

    def _configure_python_path(self) -> None:
        """Konfiguriert den Python-Pfad für bessere Modulfindung."""
        # Füge das Verzeichnis des Workers zum Python-Pfad hinzu
        if BASE_DIR not in sys.path:
            sys.path.insert(0, BASE_DIR)
        
        # Füge das übergeordnete Verzeichnis für Backend-Zugriff hinzu
        parent_dir = os.path.abspath(os.path.join(BASE_DIR, ".."))
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
    
    def setup_logging(self, logger_name: str = "worker") -> Optional[logging.Logger]:
        """
        Konfiguriert das Logging-System und gibt den Logger zurück.
        
        Args:
            logger_name: Name des Loggers
            
        Returns:
            Konfigurierter Logger oder None bei Fehler
        """
        try:
            # Logging-Konfiguration
            logging_config = {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "standard": {
                        "format": self.logging_format
                    },
                },
                "handlers": {
                    "console": {
                        "class": "logging.StreamHandler",
                        "level": self.logging_level,
                        "formatter": "standard",
                        "stream": "ext://sys.stdout"
                    },
                },
                "loggers": {
                    "": {  # Root-Logger
                        "handlers": ["console"],
                        "level": self.logging_level,
                        "propagate": True
                    },
                    logger_name: {
                        "handlers": ["console"],
                        "level": self.logging_level,
                        "propagate": False
                    }
                }
            }
            
            # Konfiguration anwenden
            logging.config.dictConfig(logging_config)
            logger = logging.getLogger(logger_name)
            logger.debug(f"Logging für {logger_name} konfiguriert mit Level {self.logging_level}")
            return logger
        
        except Exception as e:
            print(f"Fehler bei der Logging-Konfiguration: {e}")
            return None
    
    def get_celery_config(self) -> Dict[str, Any]:
        """
        Gibt die Celery-Konfiguration zurück.
        """
        return {
            "broker_url": self.redis_url,
            "result_backend": self.redis_url,
            "task_serializer": "json",
            "accept_content": ["json"],
            "result_serializer": "json",
            "timezone": "Europe/Zurich", # Zeitzone angepasst
            "enable_utc": True,
            "task_track_started": True,
            "task_time_limit": 3600,  # 1 Stunde
            "worker_prefetch_multiplier": self.worker_prefetch_multiplier,
            "worker_max_tasks_per_child": self.worker_max_tasks_per_child,
            "task_acks_late": True,
            "task_reject_on_worker_lost": True, # Wichtig bei task_acks_late
            "worker_concurrency": self.worker_concurrency,
            "worker_pool": self.celery_pool # Pool dynamisch setzen
            # Weitere Celery-Optionen nach Bedarf...
        }


# Singleton-Instanz der Konfiguration
config = WorkerConfig()

# Exportiere Konstanten für einfacheren Zugriff
REDIS_URL = config.redis_url
DATABASE_URL = config.database_url
API_URL = config.api_url
OPENAI_API_KEY = config.openai_api_key

# Prüfen, ob die Konfiguration korrekt erstellt wurde
if __name__ == "__main__":
    print("Redis URL:", config.redis_url)
    print("API URL:", config.api_url)
    print("Log Level:", config.logging_level) 