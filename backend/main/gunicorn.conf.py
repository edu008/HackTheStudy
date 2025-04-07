"""
Gunicorn Konfigurationsdatei für die HackTheStudy Backend API.
Diese Datei enthält die Konfiguration für Gunicorn im Entwicklungs- und Produktionsbetrieb.
"""

import os
import multiprocessing
import platform

# Lade Umgebungsvariablen aus .env-Datei, falls vorhanden
try:
    from dotenv import load_dotenv
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_file):
        print(f"Lade Umgebungsvariablen aus {env_file}")
        load_dotenv(env_file)
    else:
        print("Keine .env-Datei gefunden, verwende Umgebungsvariablen des Systems")
except ImportError:
    print("python-dotenv nicht installiert, verwende Umgebungsvariablen des Systems")

# Überprüfe kritische Umgebungsvariablen
if 'SQLALCHEMY_DATABASE_URI' not in os.environ:
    print("WARNUNG: SQLALCHEMY_DATABASE_URI nicht gesetzt!")

# Überprüfe das Betriebssystem - für Windows-Kompatibilität
is_windows = platform.system() == 'Windows'

# Grundlegende Konfiguration
bind = "0.0.0.0:" + os.getenv("PORT", "8080")
worker_class = "gevent"  # Verwende gevent für asynchrone Verarbeitung
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
threads = int(os.getenv("GUNICORN_THREADS", "4"))
timeout = 120  # Timeout in Sekunden
keepalive = 5  # Zeit in Sekunden, die auf Client-Verbindungen gewartet wird

# Logging-Konfiguration
accesslog = "-"  # Log an stdout
errorlog = "-"  # Log an stderr
loglevel = os.getenv("LOG_LEVEL", "info").lower()

# Worker-Optionen - /dev/shm nur unter Linux/Unix
if not is_windows:
    worker_tmp_dir = "/dev/shm"  # Nutze RAM-Disk für temporäre Dateien (schneller)
max_requests = 1000  # Neustarten nach 1000 Anfragen
max_requests_jitter = 50  # Jitter hinzufügen, um alle Worker gleichzeitig neu zu starten
graceful_timeout = 30  # Zeit in Sekunden zum graceful Beenden von Arbeitslasten

# Prozess-Name konfigurieren (für bessere Überwachung)
proc_name = "hackthestudy_api"
default_proc_name = "hackthestudy_api"

# Erhöhe die Limit-Werte für eine bessere Performance
limit_request_line = 8190
limit_request_field_size = 8190

# Falls wir hinter einem Proxy laufen
forwarded_allow_ips = '*'
proxy_protocol = False
proxy_allow_ips = '*'

# Debug-Option für Debug-Umgebungen
debug = os.getenv("FLASK_DEBUG", "0") == "1"
reload = debug

# Umgebungsvariablen an Worker übergeben
raw_env = [
    f"SQLALCHEMY_DATABASE_URI={os.getenv('SQLALCHEMY_DATABASE_URI', '')}",
    f"DATABASE_URL={os.getenv('DATABASE_URL', '')}",
    f"FLASK_APP={os.getenv('FLASK_APP', 'app.py')}",
    f"FLASK_DEBUG={os.getenv('FLASK_DEBUG', '0')}",
    f"PORT={os.getenv('PORT', '8080')}"
]

# Gunicorn-Hook zum Initialisieren von Diensten vor dem Starten
def on_starting(server):
    print("Gunicorn-Server wird gestartet...")
    print(f"Umgebungsvariablen: PORT={os.getenv('PORT')}, FLASK_APP={os.getenv('FLASK_APP')}")
    print(f"Datenbankverbindung: SQLALCHEMY_DATABASE_URI ist {'gesetzt' if 'SQLALCHEMY_DATABASE_URI' in os.environ else 'NICHT GESETZT'}")

# Hook nach dem Starten aller Worker
def post_fork(server, worker):
    print(f"Worker {worker.pid} gestartet")

# Hook zum Herunterfahren eines Workers
def worker_exit(server, worker):
    print(f"Worker {worker.pid} wird beendet")

# Hook nach dem Herunterfahren
def on_exit(server):
    print("Gunicorn-Server wird beendet...") 