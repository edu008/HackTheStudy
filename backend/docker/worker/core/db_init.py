"""
Datenbank-Initialisierungsskript für HackTheStudy

Dieses Skript führt die notwendigen Datenbankmigrationen aus und richtet 
die Datenbankstruktur ein, wenn die Anwendung zum ersten Mal gestartet wird.
"""

import os
import sys
import time
import logging
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

# Logging einrichten
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('db_init')

def wait_for_db(db_url, max_retries=30, retry_interval=2):
    """Wartet auf die Verfügbarkeit der Datenbank."""
    retries = 0
    
    # Entferne Schemainformationen und Query-Parameter
    engine = create_engine(db_url)
    
    while retries < max_retries:
        try:
            connection = engine.connect()
            connection.close()
            logger.info("Datenbankverbindung erfolgreich hergestellt")
            return True
        except OperationalError as e:
            retries += 1
            logger.warning(f"Warte auf Datenbank, Versuch {retries}/{max_retries}... ({e})")
            time.sleep(retry_interval)
    
    logger.error(f"Konnte keine Verbindung zur Datenbank herstellen nach {max_retries} Versuchen")
    return False

def create_schema_if_not_exists(db_url):
    """Erstellt das Schema, falls es nicht existiert."""
    try:
        engine = create_engine(db_url)
        
        # Überprüfe, ob die Tabellen bereits existieren
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        if existing_tables:
            logger.info(f"Datenbank-Schema existiert bereits mit {len(existing_tables)} Tabellen")
            return True
        
        # Hier könnten wir explizite Migrationsbefehle ausführen
        # Für jetzt importieren wir einfach die models, die SQLAlchemy-Modelle definieren
        logger.info("Initialisiere Datenbankschema...")
        
        # Wir importieren hier, da wir die korrekte Umgebung benötigen
        sys.path.insert(0, '/app')
        from core.models import Base
        
        # Schema erstellen
        Base.metadata.create_all(engine)
        logger.info("Datenbankschema erfolgreich erstellt")
        return True
        
    except Exception as e:
        logger.error(f"Fehler beim Erstellen des Datenbankschemas: {e}")
        return False

def main():
    """Hauptfunktion zur Initialisierung der Datenbank."""
    db_url = os.environ.get('DATABASE_URL')
    
    if not db_url:
        logger.error("DATABASE_URL ist nicht gesetzt")
        return False
    
    # Warte auf Datenbankverfügbarkeit
    if not wait_for_db(db_url):
        return False
    
    # Schema erstellen, falls es nicht existiert
    if not create_schema_if_not_exists(db_url):
        return False
    
    logger.info("Datenbankinitialisierung erfolgreich abgeschlossen")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 