#!/usr/bin/env python
"""
App-Wrapper für verbesserte Docker-Logs
--------------------------------------
Dieser Wrapper importiert und konfiguriert die verbessertes Logging, 
bevor die eigentliche Flask-App gestartet wird.
"""

import os
import sys
import time

# Füge den Verzeichnispfad zum Python-Pfad hinzu
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importiere zuerst das Docker-Logging, damit es vor anderen Imports geladen wird
try:
    import docker_logs
    from docker_logs.docker_banner import show_startup_animation
    # Zeigt an, dass das verbesserte Logging erfolgreich geladen wurde
    print(f"\033[0;32m✅ Verbessertes Logging aktiviert\033[0m")
except ImportError as e:
    print(f"\033[0;33m⚠️ Verbessertes Logging konnte nicht geladen werden: {e}\033[0m")
    # Fallback-Animation
    def show_startup_animation():
        print("HackTheStudy API wird gestartet...")

# DB-Logging-Patch wird automatisch vom docker_logs-Paket geladen

# Führe die Startanimation aus
show_startup_animation()

# Importiere und starte die eigentliche Flask-App
try:
    from app import create_app
    
    app = create_app()
    
    if __name__ == "__main__":
        # Nur starten, wenn direkt ausgeführt (nicht importiert)
        app.run(host="0.0.0.0", debug=False)
except Exception as e:
    print(f"\033[0;31m❌ Fehler beim Starten der App: {e}\033[0m")
    raise 