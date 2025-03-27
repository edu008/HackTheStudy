"""
System-Patches für die Anwendung.

Dieses Modul führt verschiedene Monkey-Patches und Anpassungen durch,
die vor dem Import anderer Module ausgeführt werden müssen.
Enthält auch die Gevent-Konfiguration.
"""

import os
import sys
import logging
import threading

# Logger konfigurieren
logging.basicConfig(level=logging.INFO)
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
    
    # Führe Gevent-Patching als erstes aus, bevor andere Module importiert werden
    patch_gevent()
    
    # Liste der weiteren auszuführenden Patches
    patches = [
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
    
    Dieses Patching muss VOR allem anderen stattfinden, um SSL-RecursionError
    und andere Probleme zu vermeiden.
    """
    # Standardmäßig aktiv, außer explizit deaktiviert
    if os.environ.get('USE_GEVENT', 'true').lower() not in ('false', '0', 'no'):
        try:
            # Import gevent.monkey vor allem anderen
            from gevent import monkey
            
            # Vollständiges Patching aller Module durchführen
            monkey.patch_all(
                socket=True,
                dns=True,
                time=True,
                select=True,
                thread=True,
                os=True,
                ssl=True,
                httplib=False,
                subprocess=True,
                sys=False,
                aggressive=True,
                Event=False
            )
            
            logger.info("Gevent-Monkey-Patching vollständig angewendet")
        except ImportError:
            logger.warning("Gevent nicht verfügbar, Patch übersprungen")
        except Exception as e:
            logger.error(f"Fehler beim Gevent-Monkey-Patching: {str(e)}")
    else:
        logger.warning("Gevent-Patch deaktiviert durch Umgebungsvariable (nicht empfohlen)")

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

# Wenn dieses Modul direkt importiert wird, führe Patches automatisch aus
apply_patches() 