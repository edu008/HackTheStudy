"""
Health-Check-Server für den Worker-Microservice
"""
import os
import json
import logging
import socket
import threading
import http.server
import socketserver
from datetime import datetime
import time

from backend.worker.health.checks import (
    check_redis_connection,
    check_system_resources,
    check_api_connection
)
from backend.worker.config import HEALTH_PORT

# Globale Start-Zeit für Uptime-Berechnung
start_time = time.time()

# Logger konfigurieren
logger = logging.getLogger(__name__)

class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    """Handler für HTTP-Anfragen des Health-Check-Servers"""
    
    def do_GET(self):
        """Behandelt GET-Anfragen"""
        if self.path == '/' or self.path == '/health':
            # Health-Check-Endpunkt
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            # Mehrere Systemkomponenten überprüfen
            checks = {
                "redis": check_redis_connection(),
                "system": check_system_resources(),
                "api": check_api_connection()
            }
            
            # Bestimme den Gesamtstatus basierend auf den einzelnen Checks
            overall_status = "healthy"
            for component, status in checks.items():
                if status.get("status") == "error":
                    overall_status = "unhealthy"
                    break
                elif status.get("status") == "degraded" and overall_status != "unhealthy":
                    overall_status = "degraded"
            
            # Gesundheitsstatus
            health_info = {
                "status": overall_status,
                "checks": checks,
                "worker_uptime": time.time() - start_time,
                "worker_info": {
                    "pid": os.getpid(),
                    "hostname": socket.gethostname(),
                    "container_type": os.environ.get('CONTAINER_TYPE', 'unknown'),
                    "run_mode": os.environ.get('RUN_MODE', 'unknown')
                },
                "timestamp": datetime.now().isoformat()
            }
            
            self.wfile.write(json.dumps(health_info).encode())
        elif self.path == '/ping':
            # Einfacher Ping-Endpunkt ohne aufwändige Prüfungen
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "message": "pong"}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Unterdrücke Logging für Health-Check-Anfragen
        pass

def start_health_check_server():
    """
    Startet einen einfachen HTTP-Server für Health-Checks im Hintergrund.
    
    Returns:
        bool: True bei Erfolg, False bei Fehler
    """
    try:
        # Port für Health-Check-Server
        # Versuche mehrere Ports, falls einer bereits belegt ist
        health_port = HEALTH_PORT
        available_ports = [health_port, 8081, 8082, 8083, 8084]
        
        server = None
        
        for port in available_ports:
            try:
                logger.info(f"Versuche Health-Check-Server auf Port {port} zu starten...")
                server = socketserver.TCPServer(("", port), HealthCheckHandler)
                # Falls wir hier ankommen, ist der Port verfügbar
                os.environ['HEALTH_PORT'] = str(port)  # Aktualisiere Umgebungsvariable
                break
            except OSError:
                logger.warning(f"Port {port} bereits belegt, versuche alternativen Port...")
                server = None
                continue
        
        if server:
            # Starte den Server in einem separaten Thread
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            logger.info(f"✅ Health-Check-Server läuft auf Port {port}")
            return True
        else:
            logger.error("❌ Konnte keinen Health-Check-Server starten: Alle Ports belegt")
            return False
            
    except Exception as e:
        logger.warning(f"❌ Konnte Health-Check-Server nicht starten: {str(e)}")
        return False 