#!/usr/bin/env python3
import time
import json
import psutil
import http.server
import socketserver
import os

class HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        health_data = {
            'status': 'healthy',
            'memory': psutil.virtual_memory().percent,
            'cpu': psutil.cpu_percent(interval=0.1),
            'uptime': time.time()
        }
        self.wfile.write(json.dumps(health_data).encode())
    
    def log_message(self, *args):
        pass

if __name__ == "__main__":
    # Nutze einen anderen Port als der Hauptserver (der auf 8080 läuft)
    port = int(os.environ.get('HEALTH_MONITOR_PORT', 8081))
    
    # Wenn Port belegt ist, versuche alternative Ports
    try:
        server = socketserver.TCPServer(('', port), HealthHandler)
        print(f"[INFO] Health monitor server gestartet auf Port {port}")
    except OSError:
        # Als letzter Versuch nutze einen zufälligen Port
        server = socketserver.TCPServer(('', 0), HealthHandler)
        actual_port = server.server_address[1]
        print(f"[INFO] Health monitor server gestartet auf zufälligem Port {actual_port}")
    
    server.serve_forever() 