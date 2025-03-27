"""
Health-Check-HTTP-Server für den Worker.
Stellt einfache HTTP-Endpunkte für Container-Orchestrierung bereit.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)

# Globaler Status für den Health-Check-Server
HEALTH_STATUS = {
    'status': 'starting',
    'start_time': datetime.now().isoformat(),
    'last_check': None,
    'checks': {}
}

# Flag zum Beenden des Servers
SHUTDOWN_FLAG = threading.Event()

# Server-Instance
SERVER_INSTANCE = None
SERVER_THREAD = None


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Handler für Health-Check-HTTP-Anfragen."""

    def do_GET(self):
        """Behandelt GET-Anfragen an den Health-Check-Server."""
        if self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'pong')

        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            # Aktualisiere den Zeitstempel der letzten Prüfung
            HEALTH_STATUS['last_check'] = datetime.now().isoformat()

            # Systemressourcen hinzufügen
            try:
                import psutil
                mem = psutil.virtual_memory()
                HEALTH_STATUS['system'] = {
                    'cpu_percent': psutil.cpu_percent(interval=0.1),
                    'memory_percent': mem.percent,
                    'memory_available_mb': mem.available / (1024 * 1024)
                }
            except ImportError:
                pass

            self.wfile.write(json.dumps(HEALTH_STATUS).encode('utf-8'))

        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Not Found')

    # Logging unterdrücken
    def log_message(self, format, *args):
        return


def update_health_status(component, status, details=None):
    """
    Aktualisiert den Health-Status einer Komponente.

    Args:
        component (str): Name der Komponente.
        status (str): Status ('ok', 'warning', 'error').
        details (dict, optional): Weitere Statusdetails.
    """
    HEALTH_STATUS['checks'][component] = {
        'status': status,
        'timestamp': datetime.now().isoformat(),
        'details': details or {}
    }

    # Gesamtstatus aktualisieren
    statuses = [check['status'] for check in HEALTH_STATUS['checks'].values()]

    if 'error' in statuses:
        HEALTH_STATUS['status'] = 'error'
    elif 'warning' in statuses:
        HEALTH_STATUS['status'] = 'warning'
    else:
        HEALTH_STATUS['status'] = 'ok'


def run_server(port=None):
    """
    Startet den Health-Check-HTTP-Server.

    Args:
        port (int, optional): Port für den Server. Standardmäßig wird der Port aus
                             der Umgebungsvariable HEALTH_PORT oder 8080 verwendet.

    Returns:
        tuple: (HTTPServer-Instanz, Server-Thread)
    """
    global SERVER_INSTANCE, SERVER_THREAD

    # Port aus Umgebungsvariable oder Standardwert
    if port is None:
        port = int(os.environ.get('HEALTH_PORT', 8080))

    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        logger.info("Health-Check-Server gestartet auf Port %s", port)

        SERVER_INSTANCE = server

        # Server in separatem Thread starten
        def server_thread():
            while not SHUTDOWN_FLAG.is_set():
                server.handle_request()
                time.sleep(0.1)

        thread = threading.Thread(target=server_thread, daemon=True)
        thread.start()

        SERVER_THREAD = thread

        # Anfangsstatus aktualisieren
        HEALTH_STATUS['status'] = 'running'

        return server, thread

    except Exception as e:
        logger.error("Fehler beim Starten des Health-Check-Servers: %s", e)
        return None, None


def start_health_check_server(port=None):
    """
    Startet den Health-Check-Server und gibt die Server-Instanz zurück.

    Args:
        port (int, optional): Port für den Server.

    Returns:
        HTTPServer: Die Server-Instanz oder None bei Fehler.
    """
    server, thread = run_server(port)
    return server


def stop_health_check_server():
    """Stoppt den laufenden Health-Check-Server."""
    global SERVER_INSTANCE, SERVER_THREAD

    if SERVER_INSTANCE:
        logger.info("Stoppe Health-Check-Server...")
        SHUTDOWN_FLAG.set()

        # Warte auf Thread-Beendigung (maximal 5 Sekunden)
        if SERVER_THREAD and SERVER_THREAD.is_alive():
            SERVER_THREAD.join(timeout=5)

        SERVER_INSTANCE.server_close()
        logger.info("Health-Check-Server gestoppt")

        SERVER_INSTANCE = None
        SERVER_THREAD = None
