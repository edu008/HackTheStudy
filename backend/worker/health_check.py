#!/usr/bin/env python3
import time
import json
import psutil
import http.server
import socketserver

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
    server = socketserver.TCPServer(('', 8080), HealthHandler)
    server.serve_forever() 