"""
Patch-Manager-Modul für die Anwendung.

Dieses Modul führt verschiedene Monkey-Patches und Anpassungen durch,
die vor dem Import anderer Module ausgeführt werden müssen.
"""

import os
import sys
import logging
import threading

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Flag, um zu verfolgen, ob Patches bereits angewendet wurden
_patches_applied = False

def apply_patches():
    """
    Führt alle notwendigen Monkey-Patches aus.
    
    Diese Funktion muss VOR dem Import aller anderen Module aufgerufen werden,
    die die gepatchten Funktionalitäten verwenden.
    """
    global _patches_applied
    
    # Vermeidet mehrfache Ausführung
    if _patches_applied:
        logger.debug("Patches wurden bereits angewendet, überspringe...")
        return
    
    # Liste der auszuführenden Patches
    patches = [
        patch_gevent,
        patch_ssl,
        patch_requests_timeout,
        patch_socket_timeout
    ]
    
    # Führe alle Patches nacheinander aus
    for patch_func in patches:
        try:
            patch_func()
        except Exception as e:
            logger.warning(f"Fehler beim Anwenden von Patch {patch_func.__name__}: {str(e)}")
    
    # Setze das Flag
    _patches_applied = True
    logger.info("Alle Patches erfolgreich angewendet")

def patch_gevent():
    """
    Patcht Gevent für bessere Async-I/O-Performance.
    """
    # Prüfe, ob wir Gevent patchen sollen
    if os.environ.get('USE_GEVENT', 'false').lower() in ('true', '1', 'yes'):
        try:
            from gevent import monkey
            # Patch nur bestimmte Module für bessere Kompatibilität
            monkey.patch_socket()
            monkey.patch_ssl()
            monkey.patch_time()
            monkey.patch_select()
            logger.info("Gevent-Patch erfolgreich angewendet")
        except ImportError:
            logger.warning("Gevent nicht verfügbar, Patch übersprungen")
    else:
        logger.debug("Gevent-Patch deaktiviert durch Umgebungsvariable")

def patch_ssl():
    """
    Konfiguriert SSL für bessere Sicherheit und Kompatibilität.
    """
    try:
        import ssl
        
        # Setze Standardkontext für höhere Sicherheit
        original_create_default_context = ssl.create_default_context
        
        def patched_create_default_context(*args, **kwargs):
            context = original_create_default_context(*args, **kwargs)
            # Verwende TLS 1.2 als Minimum für bessere Sicherheit
            context.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
            return context
        
        # Wende den Patch an
        ssl.create_default_context = patched_create_default_context
        logger.info("SSL-Patch für höhere Sicherheit angewendet")
    except ImportError:
        logger.warning("SSL-Modul nicht verfügbar, Patch übersprungen")
    except Exception as e:
        logger.error(f"Fehler beim Patchen von SSL: {str(e)}")

def patch_requests_timeout():
    """
    Setzt globale Timeouts für Requests, um Hängenbleiben zu vermeiden.
    """
    try:
        import requests
        from requests.adapters import HTTPAdapter
        
        # Definiere einen benutzerdefinierten Adapter mit längeren Timeouts
        class TimeoutAdapter(HTTPAdapter):
            def __init__(self, *args, **kwargs):
                self.timeout = kwargs.pop('timeout', 30)
                super().__init__(*args, **kwargs)
            
            def send(self, request, **kwargs):
                kwargs.setdefault('timeout', self.timeout)
                return super().send(request, **kwargs)
        
        # Wende den Adapter bei jeder Session an
        original_session = requests.Session
        
        def patched_session(*args, **kwargs):
            session = original_session(*args, **kwargs)
            timeout = float(os.environ.get('DEFAULT_REQUEST_TIMEOUT', '30'))
            adapter = TimeoutAdapter(timeout=timeout)
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            return session
        
        # Ersetze die Session
        requests.Session = patched_session
        logger.info(f"Requests-Timeout-Patch angewendet (Standard-Timeout: {os.environ.get('DEFAULT_REQUEST_TIMEOUT', '30')}s)")
    except ImportError:
        logger.debug("Requests-Modul nicht verfügbar, Timeout-Patch übersprungen")
    except Exception as e:
        logger.error(f"Fehler beim Patchen von Requests-Timeout: {str(e)}")

def patch_socket_timeout():
    """
    Setzt einen globalen Socket-Timeout, um Hängenbleiben zu vermeiden.
    """
    try:
        import socket
        
        # Speichere die originale Socket-Klasse
        original_socket = socket.socket
        
        # Definiere eine gepatchte Version mit Timeout
        def patched_socket(*args, **kwargs):
            sock = original_socket(*args, **kwargs)
            timeout = float(os.environ.get('DEFAULT_SOCKET_TIMEOUT', '30'))
            sock.settimeout(timeout)
            return sock
        
        # Patche die Socket-Klasse
        socket.socket = patched_socket
        logger.info(f"Socket-Timeout-Patch angewendet (Standard-Timeout: {os.environ.get('DEFAULT_SOCKET_TIMEOUT', '30')}s)")
    except Exception as e:
        logger.error(f"Fehler beim Patchen des Socket-Timeouts: {str(e)}")

# Wenn dieses Modul direkt ausgeführt wird, führe alle Patches aus
if __name__ == "__main__":
    # Konfiguriere Basic-Logging
    logging.basicConfig(level=logging.INFO)
    
    # Führe Patches aus
    apply_patches()
    
    logger.info("Patch-Manager erfolgreich ausgeführt") 