#!/usr/bin/env python
"""
Gunicorn-Wrapper für die HackTheStudy-Anwendung

Dieses Skript konfiguriert und startet die Flask-Anwendung mit Gunicorn,
dem WSGI HTTP-Server für die Produktionsumgebung.
"""

import os
import sys
import multiprocessing
import gunicorn.app.base
from gunicorn.six import iteritems

# Stellen sicher, dass das App-Verzeichnis im Python-Pfad ist
sys.path.insert(0, '/app')

# Docker-Logs vorübergehend deaktiviert - verursacht möglicherweise Abstürze
# use_colored_logs = os.environ.get('USE_COLORED_LOGS', 'false').lower() == 'true'
# if use_colored_logs:
#     try:
#         from docker_logs.docker_banner import show_startup_animation
#     except ImportError:
#         print("⚠️ Docker-Logs-Modul konnte nicht importiert werden")

# Importiere Umgebungsvariablen-Handler
try:
    from config.env_handler import load_env
    load_env()
except ImportError:
    print("Warnung: Umgebungsvariablen-Handler konnte nicht importiert werden")

class StandaloneApplication(gunicorn.app.base.BaseApplication):
    """Gunicorn-Anwendungsklasse für das Starten der Flask-App"""

    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        for key, value in iteritems(self.options):
            if key in self.cfg.settings and value is not None:
                self.cfg.set(key.lower(), value)

    def load(self):
        return self.application

if __name__ == '__main__':
    # Flask-Anwendung importieren (wird bereits in app.py initialisiert)
    from app import app
    
    # Gunicorn-Konfiguration
    cpu_count = multiprocessing.cpu_count()
    workers = min(cpu_count * 2 + 1, 8)  # 2-8 Worker je nach CPU-Anzahl
    
    options = {
        'bind': '0.0.0.0:5000',
        'workers': workers,
        'worker_class': 'gevent',
        'timeout': 120,
        'keepalive': 5,
        'loglevel': os.environ.get('LOG_LEVEL', 'info').lower(),
        'accesslog': '-',
        'errorlog': '-',
        'capture_output': True,
        'reload': os.environ.get('FLASK_ENV') == 'development',
    }
    
    # Docker-Logs und Animation vorübergehend deaktiviert
    # if use_colored_logs:
    #     try:
    #         # Serviceprüfung
    #         services = [
    #             ("API-Server", True),
    #             ("PostgreSQL", True),
    #             ("Redis", True)
    #         ]
    #         
    #         # Initialisierungsschritte
    #         init_steps = [
    #             ("Starte Gunicorn mit WSGI", 0.5),
    #             (f"Starte {workers} Worker", 0.5),
    #             ("Registriere API-Endpunkte", 0.5)
    #         ]
    #         
    #         # Zeige Banner-Animation
    #         show_startup_animation("API", services, init_steps)
    #     except Exception as e:
    #         print(f"⚠️ Fehler beim Anzeigen der Startup-Animation: {e}")
    #         print(f"🚀 Starte Gunicorn mit {workers} Workern...")
    # else:
    print(f"🚀 Starte Gunicorn mit {workers} Workern...")
    
    StandaloneApplication(app, options).run() 