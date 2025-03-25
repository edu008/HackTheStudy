"""
Haupteinstiegspunkt für den API-Container.
"""

# Lade Umgebungsvariablen vor allem anderen
import os
from dotenv import load_dotenv
load_dotenv()

# Setze die ENVIRONMENT-Variable direkt am Anfang
os.environ['ENVIRONMENT'] = os.environ.get('ENVIRONMENT', 'production')

# Führe Monkey-Patching durch, BEVOR andere Module importiert werden
from bootstrap.patch_manager import apply_patches
apply_patches()

# Jetzt können andere Module sicher importiert werden
import logging
from bootstrap.logging_setup import setup_logging

# Logging initialisieren
logger = setup_logging()
logger.info("API-Container wird gestartet...")

# App erstellen über Factory
from bootstrap.app_factory import create_app
app = create_app()

# Für direktes Ausführen (nicht für Gunicorn)
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    
    logger.info(f"Server wird auf {host}:{port} gestartet (Debug: {debug})")
    app.run(host=host, port=port, debug=debug)