#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Start-Skript für die HackTheStudy Backend API mit Gunicorn oder Waitress.
Dieses Skript kann direkt mit Python ausgeführt werden und startet die API mit dem
geeigneten Server für die jeweilige Plattform.
"""

import os
import subprocess
import sys
import platform
import importlib.util

def setup_environment():
    """Umgebungsvariablen einrichten, falls nicht vorhanden."""
    # Wichtige Standardwerte setzen
    os.environ.setdefault("PORT", "8080")
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    os.environ.setdefault("FLASK_APP", "app.py")
    os.environ.setdefault("LOG_LEVEL", "INFO")
    
    # Debug-Modus für die Entwicklung aktivieren, sofern nicht anders konfiguriert
    if "FLASK_DEBUG" not in os.environ:
        os.environ["FLASK_DEBUG"] = "1"
    
    # Stelle sicher, dass Redis-URL gesetzt ist
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    
    print(f"Umgebungsvariablen konfiguriert:")
    print(f"PORT: {os.environ.get('PORT')}")
    print(f"FLASK_APP: {os.environ.get('FLASK_APP')}")
    print(f"FLASK_DEBUG: {os.environ.get('FLASK_DEBUG')}")
    print(f"LOG_LEVEL: {os.environ.get('LOG_LEVEL')}")
    print(f"Betriebssystem: {platform.system()}")

def is_package_installed(package_name):
    """Prüft, ob ein Python-Paket installiert ist."""
    return importlib.util.find_spec(package_name) is not None

def run_waitress():
    """Startet die Flask-App mit Waitress (für Windows)."""
    if not is_package_installed("waitress"):
        print("❌ Waitress ist nicht installiert. Installiere es mit:")
        print("pip install waitress")
        sys.exit(1)
    
    print("✅ Waitress ist installiert.")
    
    # Importiere Waitress und die Flask-App
    from waitress import serve
    import importlib.util
    
    # Dynamisch die app.py laden
    spec = importlib.util.spec_from_file_location("app", "app.py")
    app_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_module)
    
    # Hole die Flask-App vom Modul
    flask_app = app_module.app
    
    # Starte den Waitress-Server
    port = int(os.environ.get("PORT", 8080))
    print(f"Starte Waitress-Server auf http://0.0.0.0:{port}")
    serve(flask_app, host="0.0.0.0", port=port, threads=8)

def run_gunicorn():
    """Startet die API mit Gunicorn (für Linux/macOS)."""
    # Prüfe, ob Gunicorn installiert ist
    try:
        subprocess.run([sys.executable, "-m", "pip", "show", "gunicorn"], 
                      check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("✅ Gunicorn ist installiert.")
    except subprocess.CalledProcessError:
        print("❌ Gunicorn ist nicht installiert. Installiere es mit:")
        print("pip install gunicorn>=21.2.0 gevent>=23.9.1")
        sys.exit(1)
    
    # Prüfe, ob Gevent installiert ist
    try:
        subprocess.run([sys.executable, "-m", "pip", "show", "gevent"], 
                      check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("✅ Gevent ist installiert.")
    except subprocess.CalledProcessError:
        print("❌ Gevent ist nicht installiert. Installiere es mit:")
        print("pip install gevent>=23.9.1")
        sys.exit(1)
    
    # Pfad zur Gunicorn-Konfigurationsdatei
    config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gunicorn.conf.py")
    
    # Prüfe, ob die Konfigurationsdatei existiert
    if not os.path.exists(config_file):
        print(f"❌ Konfigurationsdatei nicht gefunden: {config_file}")
        sys.exit(1)
    
    print(f"✅ Konfigurationsdatei gefunden: {config_file}")
    
    # Gunicorn-Befehl aufbauen und ausführen
    cmd = [
        "gunicorn",
        "-c", config_file,
        "--preload",
        "app:app"
    ]
    
    print(f"Starte Gunicorn mit: {' '.join(cmd)}")
    
    try:
        # Starte Gunicorn und gib Ausgabe direkt weiter
        process = subprocess.Popen(cmd)
        process.wait()
    except KeyboardInterrupt:
        print("\nServer wird durch Benutzer-Unterbrechung beendet...")
        process.terminate()
        process.wait()
    except Exception as e:
        print(f"❌ Fehler beim Starten von Gunicorn: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("💻 Starte HackTheStudy Backend API...")
    setup_environment()
    
    # Starte den geeigneten Server je nach Betriebssystem
    if platform.system() == "Windows":
        print("Windows erkannt - verwende Waitress statt Gunicorn")
        run_waitress()
    else:
        print("Unix/Linux erkannt - verwende Gunicorn")
        run_gunicorn() 