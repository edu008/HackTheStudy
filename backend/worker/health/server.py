"""
Einfacher Health-Check-Server für den Worker-Microservice.
"""
import os
import threading
import logging
import json
import time
import signal
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Standard-Port für den Health-Check-Server
DEFAULT_PORT = int(os.environ.get('HEALTH_PORT', 8080))

# Flag, um den Server-Status zu verfolgen
server_running = False
server_instance = None
shutdown_requested = False

class HealthCheckHandler(BaseHTTPRequestHandler):
    """
    HTTP-Request-Handler für den Health-Check-Server.
    """
    
    def _send_response(self, status_code, content_type, content):
        """
        Sendet eine HTTP-Response.
        """
        self.send_response(status_code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)
    
    def log_message(self, format, *args):
        """
        Überschreibe die Log-Methode, um zu unserem Logger umzuleiten.
        """
        logger.debug(f"Health-Check-Server: {format % args}")
    
    def do_GET(self):
        """
        Behandelt GET-Requests.
        """
        if self.path == '/ping' or self.path == '/':
            # Einfacher Ping-Endpunkt
            self._send_response(200, 'text/plain', b'pong')
        
        elif self.path == '/health':
            # Detaillierter Health-Check-Endpunkt
            from redis_utils.client import is_redis_connected, get_redis_connection_info
            
            # Sammle Statusinformationen
            health_data = {
                'status': 'healthy',
                'container_type': os.environ.get('CONTAINER_TYPE', 'worker'),
                'redis': {
                    'connected': is_redis_connected(),
                    'connection_info': get_redis_connection_info()
                },
                'environment': {
                    'REDIS_HOST': os.environ.get('REDIS_HOST', 'not set'),
                    'REDIS_URL': os.environ.get('REDIS_URL', 'not set'),
                    'API_HOST': os.environ.get('API_HOST', 'not set'),
                    'REDIS_FALLBACK_URLS': os.environ.get('REDIS_FALLBACK_URLS', 'not set')
                }
            }
            
            # Als JSON zurückgeben
            response_content = json.dumps(health_data, indent=2).encode('utf-8')
            self._send_response(200, 'application/json', response_content)
        
        else:
            # Unbekannter Pfad
            self._send_response(404, 'text/plain', b'Not Found')
    
    def do_HEAD(self):
        """
        Behandelt HEAD-Requests.
        """
        if self.path == '/ping' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """
    Threaded HTTP-Server für parallele Anfragen.
    """
    daemon_threads = True

def signal_handler(signum, frame):
    """
    Behandelt Signale wie SIGTERM und SIGINT.
    """
    global shutdown_requested
    logger.info(f"Signal {signum} empfangen, Herunterfahren...")
    shutdown_requested = True
    stop_health_check_server()

def start_health_check_server(port=None):
    """
    Startet den Health-Check-Server im Hintergrund.
    
    Args:
        port: Der Port, auf dem der Server laufen soll (default: 8080)
    """
    global server_running, server_instance, shutdown_requested
    
    if server_running:
        logger.info("Health-Check-Server läuft bereits")
        return
    
    if port is None:
        port = DEFAULT_PORT
    
    logger.info(f"Versuche Health-Check-Server auf Port {port} zu starten...")
    
    def run_server():
        global server_running, server_instance
        try:
            server = ThreadedHTTPServer(('0.0.0.0', port), HealthCheckHandler)
            server_instance = server
            server_running = True
            logger.info(f"✅ Health-Check-Server läuft auf Port {port}")
            logger.info(f"   - Ping-Endpunkt: http://localhost:{port}/ping")
            logger.info(f"   - Status-Endpunkt: http://localhost:{port}/health")
            server.serve_forever()
        except Exception as e:
            server_running = False
            logger.error(f"❌ Fehler beim Starten des Health-Check-Servers: {str(e)}")
    
    # Starte den Server in einem eigenen Thread
    server_thread = threading.Thread(target=run_server, daemon=False)  # Daemon auf False setzen, damit er nicht beendet wird
    server_thread.start()

def stop_health_check_server():
    """
    Stoppt den Health-Check-Server.
    """
    global server_running, server_instance
    
    if not server_running or server_instance is None:
        logger.info("Health-Check-Server läuft nicht")
        return
    
    logger.info("Stoppe Health-Check-Server...")
    server_instance.shutdown()
    server_running = False
    server_instance = None
    logger.info("Health-Check-Server gestoppt")

# Wenn dieses Skript direkt ausgeführt wird
if __name__ == "__main__":
    # Logging konfigurieren, wenn nicht bereits geschehen
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format='[HEALTH] %(levelname)s: %(message)s')
    
    # Signal-Handler registrieren
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Server starten
    start_health_check_server()
    
    logger.info("Health-Check-Server läuft im Vordergrund. Drücken Sie Strg+C zum Beenden.")
    
    # Hauptschleife, um den Prozess am Leben zu halten
    try:
        while not shutdown_requested:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Tastatur-Interrupt empfangen, Herunterfahren...")
        stop_health_check_server()
        
    logger.info("Health-Check-Server-Prozess beendet") 