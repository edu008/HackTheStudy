"""
Health-Check-Server für den API-Container.
"""

import os
import sys
import threading
import logging
import json
import socket
from typing import Dict, Any
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import time

from .monitor import get_health_status

# Logger konfigurieren
logger = logging.getLogger(__name__)

class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP-Handler für Health-Check-Anfragen."""
    
    def do_GET(self):
        """Behandelt GET-Anfragen an den Health-Check-Server."""
        try:
            # Pfad analysieren
            if self.path == "/health" or self.path == "/":
                self._serve_health_check()
            elif self.path == "/health/details":
                self._serve_detailed_health()
            elif self.path == "/ping":
                # Direkter Ping-Endpunkt für Kubernetes/DigitalOcean Health-Checks
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"pong")
                logger.debug("Ping-Anfrage beantwortet")
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not Found")
        except Exception as e:
            logger.error(f"Fehler im Health-Check-Handler: {str(e)}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Internal Server Error: {str(e)}".encode('utf-8'))
    
    def _serve_health_check(self):
        """Liefert einfachen Health-Check-Status."""
        health_data = get_health_status()
        
        # Vereinfachter Status (nur OK/nicht OK)
        is_healthy = health_data.get("status") in ["healthy", "starting"]
        
        # HTTP-Status basierend auf Gesundheit
        self.send_response(200 if is_healthy else 503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        
        # Response-Body
        response = {
            "status": "healthy" if is_healthy else "unhealthy",
            "timestamp": datetime.now().isoformat()
        }
        
        self.wfile.write(json.dumps(response).encode('utf-8'))
    
    def _serve_detailed_health(self):
        """Liefert detaillierten Health-Check-Status."""
        health_data = get_health_status()
        
        # HTTP-Status basierend auf Gesundheit
        is_healthy = health_data.get("status") in ["healthy", "starting"]
        self.send_response(200 if is_healthy else 503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        
        # Füge Zeitstempel hinzu
        health_data["timestamp"] = datetime.now().isoformat()
        
        self.wfile.write(json.dumps(health_data).encode('utf-8'))
    
    # Server-Log unterdrücken
    def log_message(self, format, *args):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Health-Server: {format % args}")

def setup_health_server(port: int = 8080, app=None) -> threading.Thread:
    """
    Startet einen HTTP-Server für Health-Checks im Hintergrund.
    
    Args:
        port: TCP-Port für den Health-Check-Server
        app: Optional, Flask-App für erweiterte Health-Checks
    
    Returns:
        Thread-Objekt des Health-Servers
    """
    def run_server():
        try:
            # Immer an alle Interfaces binden (0.0.0.0) für Kubernetes/DigitalOcean Health Checks
            server_address = ('0.0.0.0', port)
            
            logger.info(f"Starte HTTP-Health-Server auf {server_address[0]}:{server_address[1]}...")
            httpd = HTTPServer(server_address, HealthCheckHandler)
            logger.info(f"✅ Health-Check-Server gestartet auf {server_address[0]}:{server_address[1]}")
            logger.info(f"   - Health-Endpunkt verfügbar unter: http://{server_address[0]}:{server_address[1]}/health")
            logger.info(f"   - Details verfügbar unter: http://{server_address[0]}:{server_address[1]}/health/details")
            logger.info(f"   - Ping-Endpunkt verfügbar unter: http://{server_address[0]}:{server_address[1]}/ping")
            
            # Prüfe, ob der Server tatsächlich lauscht
            sock_name = httpd.socket.getsockname()
            logger.info(f"✅ Server lauscht auf {sock_name[0]}:{sock_name[1]}")
            
            # Explizit Ping-Route hinzufügen - eine spezialisierte Handler-Klasse
            class PingHandler(HealthCheckHandler):
                def do_GET(self):
                    if self.path == "/ping":
                        self.send_response(200)
                        self.send_header("Content-Type", "text/plain")
                        self.end_headers()
                        self.wfile.write(b"pong")
                    else:
                        super().do_GET()
            
            # WICHTIG: Wir müssen den HTTP-Server neu erstellen mit dem PingHandler
            # Stoppe den vorherigen Server
            httpd.server_close()
            
            # Erstelle einen neuen Server mit PingHandler
            httpd = HTTPServer(server_address, PingHandler)
            logger.info(f"✅ Health-Check-Server mit PingHandler neu gestartet")
            
            # Server endlos laufen lassen
            httpd.serve_forever()
        except Exception as e:
            logger.error(f"❌ Fehler beim Starten des Health-Check-Servers: {str(e)}")
            
            # Versuche es mit einem anderen Port, falls der Hauptport belegt ist
            if isinstance(e, socket.error) and e.errno == 98:  # Address already in use
                fallback_port = port + 1
                logger.warning(f"Versuche Fallback auf Port {fallback_port}")
                try:
                    server_address = ('0.0.0.0', fallback_port)
                    httpd = HTTPServer(server_address, HealthCheckHandler)
                    logger.info(f"✅ Health-Check-Server gestartet auf Fallback-Port {fallback_port}")
                    httpd.serve_forever()
                except Exception as fallback_e:
                    logger.error(f"❌ Auch Fallback-Port fehlgeschlagen: {str(fallback_e)}")
    
    # Thread starten
    thread = threading.Thread(target=run_server, daemon=True, name="health-server")
    thread.start()
    
    # Warte kurz, um sicherzustellen, dass der Server läuft
    time.sleep(0.5)
    
    # Prüfe, ob der Port erreichbar ist (von localhost und 0.0.0.0)
    try:
        # Prüfe lokalen Zugriff
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        result = s.connect_ex(('127.0.0.1', port))
        if result == 0:
            logger.info(f"✅ Health-Server-Port {port} ist von 127.0.0.1 erreichbar")
        else:
            logger.warning(f"⚠️ Health-Server-Port {port} scheint NICHT von 127.0.0.1 erreichbar zu sein (Code: {result})")
        s.close()
        
        # Prüfe externen Zugriff (nur im Logging)
        logger.info(f"✅ Health-Server wurde auf allen Interfaces (0.0.0.0:{port}) gestartet und sollte für externe Anfragen erreichbar sein")
        
        # Liste alle Netzwerkschnittstellen auf
        logger.info("📊 Netzwerkschnittstellen:")
        try:
            import psutil
            addrs = psutil.net_if_addrs()
            for ifname, addrs in addrs.items():
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        logger.info(f"   - Interface {ifname}: {addr.address}")
        except ImportError:
            logger.info("   - psutil nicht installiert, kann Netzwerkschnittstellen nicht auflisten")
            
    except Exception as e:
        logger.warning(f"⚠️ Fehler beim Prüfen des Health-Server-Ports: {str(e)}")
    
    return thread 