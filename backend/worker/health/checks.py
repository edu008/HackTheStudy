"""
Gesundheitsprüfungen für den Worker-Microservice
"""
import os
import logging
import time
import socket
import requests
import psutil
from datetime import datetime
import json
from redis_utils.client import get_redis_client

# Logger konfigurieren
logger = logging.getLogger(__name__)

def check_redis_connection():
    """
    Prüft die Redis-Verbindung für Health-Checks.
    
    Returns:
        dict: Status und Details der Redis-Verbindung
    """
    try:
        redis_client = get_redis_client()
        start_time = time.time()
        ping_result = redis_client.ping()
        response_time = (time.time() - start_time) * 1000  # ms
        
        if ping_result:
            redis_info = redis_client.info()
            redis_host = os.environ.get('REDIS_HOST', 'localhost')
            
            return {
                "status": "healthy",
                "message": "Redis-Verbindung erfolgreich",
                "host": redis_host,
                "response_time_ms": round(response_time, 2),
                "redis_version": redis_info.get('redis_version', 'unbekannt'),
                "used_memory_human": redis_info.get('used_memory_human', 'unbekannt')
            }
        else:
            return {
                "status": "degraded",
                "message": "Redis-Ping fehlgeschlagen"
            }
    except Exception as e:
        logger.error(f"Redis-Verbindungsfehler im Health-Check: {str(e)}")
        return {
            "status": "error",
            "message": f"Redis-Verbindungsfehler: {str(e)}"
        }

def check_system_resources():
    """
    Prüft Systemressourcen für Health-Checks.
    
    Returns:
        dict: Status und Details der Systemressourcen
    """
    try:
        # CPU und RAM prüfen
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        
        status = "healthy"
        if cpu_percent > 90 or memory.percent > 90:
            status = "degraded"
        
        process = psutil.Process()
        
        return {
            "status": status,
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_available_mb": round(memory.available / (1024 * 1024), 2),
            "process_memory_mb": round(process.memory_info().rss / (1024 * 1024), 2),
            "open_file_descriptors": len(process.open_files()),
            "process_uptime": round(time.time() - process.create_time(), 2)
        }
    except ImportError:
        # Wenn psutil nicht verfügbar ist, vereinfachten Status zurückgeben
        return {
            "status": "degraded",
            "message": "psutil nicht verfügbar - eingeschränkte Systemdiagnose",
            "os": os.name
        }
    except Exception as e:
        logger.error(f"Fehler bei Systemressourcenprüfung: {str(e)}")
        return {
            "status": "degraded",
            "message": f"Fehler bei Systemressourcenprüfung: {str(e)}"
        }

def check_api_connection():
    """
    Prüft die Verbindung zum API-Backend.
    
    Returns:
        dict: Status und Details der API-Verbindung
    """
    try:
        # API-Host aus Umgebungsvariablen ermitteln
        api_host = os.environ.get('API_HOST', 'api')
        port = 8080  # Standard-API-Port
        
        # Verschiedene mögliche URLs probieren
        api_urls = [
            f"http://{api_host}:{port}/api/v1/ping",
            f"http://{api_host}:{port}/api/v1/simple-health",
            f"http://localhost:{port}/api/v1/ping"
        ]
        
        for url in api_urls:
            try:
                start_time = time.time()
                response = requests.get(url, timeout=2)
                response_time = (time.time() - start_time) * 1000  # ms
                
                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "message": f"API erreichbar unter {url}",
                        "response_time_ms": round(response_time, 2),
                        "response_code": response.status_code,
                        "api_host": api_host
                    }
            except:
                continue
        
        # Wenn wir hier ankommen, war keine Verbindung erfolgreich
        # Prüfe, ob wir den Host auflösen können
        try:
            api_ip = socket.gethostbyname(api_host)
            return {
                "status": "degraded",
                "message": f"API nicht direkt erreichbar, Host auflösbar: {api_host} -> {api_ip}",
                "api_host": api_host
            }
        except:
            return {
                "status": "degraded",
                "message": "API nicht erreichbar, Host nicht auflösbar",
                "api_host": api_host
            }
    except Exception as e:
        logger.error(f"Fehler bei API-Verbindungsprüfung: {str(e)}")
        return {
            "status": "error", 
            "message": f"Fehler bei API-Verbindungsprüfung: {str(e)}"
        } 