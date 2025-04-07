"""
WSGI-Einstiegspunkt für die HackTheStudy Backend API.
Diese Datei dient als Wrapper für die Flask-App und stellt sicher, dass
alle Umgebungsvariablen korrekt geladen werden.
"""

import os
import sys

# Setze eine Umgebungsvariable, um das automatische Gevent-Patching zu deaktivieren
os.environ["GEVENT_MONKEY_PATCH"] = "0"
os.environ["AUTHLIB_INSECURE_TRANSPORT"] = "1"  # Für Entwicklung, in Produktion entfernen!

# Stelle sicher, dass das Verzeichnis im Python-Pfad ist
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Lade Umgebungsvariablen aus .env-Datei
try:
    from dotenv import load_dotenv
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_file):
        print(f"WSGI: Lade Umgebungsvariablen aus {env_file}")
        load_dotenv(env_file)
    else:
        print("WSGI: Keine .env-Datei gefunden, verwende Umgebungsvariablen des Systems")
except ImportError:
    print("WSGI: python-dotenv nicht installiert, verwende Umgebungsvariablen des Systems")

# Wenn SQLALCHEMY_DATABASE_URI nicht gesetzt ist, setze es explizit
if 'SQLALCHEMY_DATABASE_URI' not in os.environ and 'DATABASE_URL' in os.environ:
    print("WSGI: Setze SQLALCHEMY_DATABASE_URI aus DATABASE_URL")
    os.environ['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']

# Überprüfe, ob die Datenbankverbindung gesetzt ist
if 'SQLALCHEMY_DATABASE_URI' not in os.environ:
    print("WSGI FEHLER: SQLALCHEMY_DATABASE_URI ist nicht gesetzt!")
    # Setze eine Fallback-Verbindung für SQLite
    os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
    print("WSGI: Fallback zu SQLite-Datenbank: sqlite:///app.db")

# Fakeredis für Tests verwenden, wenn REDIS_URL mit memory:// beginnt
if os.environ.get('REDIS_URL', '').startswith('memory://'):
    print("WSGI: Verwende Fakeredis für Tests")
    try:
        import fakeredis
        # Monkey-Patch für Redis
        import sys
        import fakeredis.aioredis
        sys.modules['redis'] = fakeredis
    except ImportError:
        print("WSGI WARNUNG: fakeredis nicht installiert, Redis-Funktionalität wird nicht verfügbar sein")

# Importiere die Flask-App
from app import app as application

# Für direkten Start mit Python
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Starte den HackTheStudy API-Server')
    parser.add_argument('--port', type=int, default=os.getenv('PORT', 8080), 
                        help='Port für den Server (default: 8080)')
    parser.add_argument('--host', default=os.getenv('FLASK_RUN_HOST', '0.0.0.0'), 
                        help='Host für den Server (default: 0.0.0.0)')
    parser.add_argument('--waitress', action='store_true', 
                        help='Waitress anstelle von Flask-Entwicklungsserver verwenden')
    
    args = parser.parse_args()
    
    # Wähle den Server je nach Plattform und Parameter
    if args.waitress:
        try:
            from waitress import serve
            print(f"Starte Waitress-Server auf http://{args.host}:{args.port}")
            serve(application, host=args.host, port=args.port, threads=8)
        except ImportError:
            print("Waitress nicht installiert, verwende Flask-Entwicklungsserver")
            application.run(host=args.host, port=args.port, debug=os.getenv('FLASK_DEBUG', '0') == '1')
    else:
        print(f"Starte Flask-Entwicklungsserver auf http://{args.host}:{args.port}")
        application.run(host=args.host, port=args.port, debug=os.getenv('FLASK_DEBUG', '0') == '1') 