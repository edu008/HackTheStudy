#!/usr/bin/env python3
import time
import json
import psutil
import http.server
import socketserver

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
    server = socketserver.TCPServer(('', 8081), HealthHandler)
    server.serve_forever() 