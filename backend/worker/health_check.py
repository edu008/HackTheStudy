#!/usr/bin/env python3
import time
import json
import psutil
import http.server
import socketserver
import os

class HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/ping':
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
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, *args):
        pass

if __name__ == "__main__":
    port = int(os.environ.get('HEALTH_PORT', 8080))
    
    # Wenn Port belegt ist, versuche alternative Ports
    try:
        server = socketserver.TCPServer(('', port), HealthHandler)
        print(f"[INFO] Health check server gestartet auf Port {port}")
    except OSError:
        # Wenn Port belegt ist, versuche Port 8081
        alternative_port = 8081
        try:
            server = socketserver.TCPServer(('', alternative_port), HealthHandler)
            print(f"[INFO] Health check server gestartet auf alternativem Port {alternative_port}")
        except OSError:
            # Als letzter Versuch nutze einen zufälligen Port
            server = socketserver.TCPServer(('', 0), HealthHandler)
            actual_port = server.server_address[1]
            print(f"[INFO] Health check server gestartet auf zufälligem Port {actual_port}")
    
    server.serve_forever() 