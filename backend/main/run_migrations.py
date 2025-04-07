#!/usr/bin/env python
"""
Script zum Ausführen aller verfügbaren Migrationen.

Dieses Script durchsucht das migrations-Verzeichnis und führt
alle verfügbaren Migrations-Scripts aus.
"""

import importlib
import inspect
import logging
import os
import sys
from flask import Flask
from core.models import db
from sqlalchemy import text
from dotenv import load_dotenv

# Logger konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment-Variablen aus .env laden
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
    logger.info(f"Umgebungsvariablen aus {env_path} geladen")
else:
    logger.warning(f".env-Datei nicht gefunden unter {env_path}")

def create_app():
    """Erstellt eine minimale Flask-App für Migrationen."""
    app = Flask(__name__)
    
    # Lade Konfiguration aus Umgebungsvariablen
    db_uri = os.environ.get('SQLALCHEMY_DATABASE_URI')
    if not db_uri:
        # Verwende alternative Umgebungsvariable DATABASE_URL
        db_uri = os.environ.get('DATABASE_URL')
        if db_uri:
            logger.info(f"Verwende DATABASE_URL als Datenbankverbindung")
        else:
            # Fallback für lokale Entwicklung
            db_uri = 'postgresql://postgres:postgres@localhost:5432/hackthestudy'
            logger.warning(f"Keine Datenbankverbindung in Umgebungsvariablen gefunden, verwende Fallback: {db_uri}")
    else:
        logger.info(f"Verwende SQLALCHEMY_DATABASE_URI als Datenbankverbindung")
    
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Debug-Log für die Datenbankverbindung
    logger.info(f"Verwende Datenbankverbindung: {db_uri.split('@')[-1]} (Benutzer und Passwort maskiert)")
    
    # Initialisiere die Datenbank
    db.init_app(app)
    
    return app

def run_migrations(app):
    """
    Führt alle verfügbaren Migrations-Scripts aus.
    
    Args:
        app: Flask-App
        
    Returns:
        tuple: (erfolgreiche_migrationen, fehlerhafte_migrationen)
    """
    logger.info("Starte Datenbank-Migrationen...")
    
    # Pfad zum Migrations-Verzeichnis
    migrations_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations')
    
    # Prüfe, ob das Verzeichnis existiert
    if not os.path.exists(migrations_dir):
        logger.error(f"Migrations-Verzeichnis {migrations_dir} existiert nicht")
        return 0, 0
    
    # Suche nach Python-Dateien im Migrations-Verzeichnis
    migration_files = []
    for filename in os.listdir(migrations_dir):
        if filename.endswith('.py') and filename != '__init__.py':
            migration_files.append(filename[:-3])  # Entferne .py-Endung
    
    logger.info(f"Gefundene Migrations-Dateien: {', '.join(migration_files)}")
    
    # Migrations-Tabelle erstellen, falls nicht vorhanden
    with app.app_context():
        try:
            db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS migrations (
                id VARCHAR(200) PRIMARY KEY,
                description TEXT,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """))
            db.session.commit()
            logger.info("Migrations-Tabelle überprüft/erstellt")
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Migrations-Tabelle: {e}")
            return 0, 0
    
    # Migrationen ausführen
    successful_migrations = 0
    failed_migrations = 0
    
    for migration_module_name in sorted(migration_files):
        with app.app_context():
            try:
                # Migrations-Modul importieren
                migration_module = importlib.import_module(f"migrations.{migration_module_name}")
                
                # Migration-ID und Beschreibung abrufen oder generieren
                migration_id = getattr(migration_module, "MIGRATION_ID", migration_module_name)
                migration_description = getattr(migration_module, "MIGRATION_DESCRIPTION", f"Migration {migration_id}")
                
                logger.info(f"Prüfe Migration: {migration_id} - {migration_description}")
                
                # Prüfen, ob die Migration bereits angewendet wurde
                result = db.session.execute(
                    text("SELECT id FROM migrations WHERE id = :id"),
                    {"id": migration_id}
                ).fetchone()
                
                if result:
                    logger.info(f"Migration {migration_id} wurde bereits angewendet, überspringe...")
                    continue
                
                # Migration ausführen
                if hasattr(migration_module, "run_migration") and inspect.isfunction(migration_module.run_migration):
                    logger.info(f"Führe Migration {migration_id} aus...")
                    success = migration_module.run_migration()
                    
                    if success:
                        successful_migrations += 1
                        logger.info(f"Migration {migration_id} erfolgreich angewendet")
                    else:
                        failed_migrations += 1
                        logger.error(f"Migration {migration_id} fehlgeschlagen")
                else:
                    logger.warning(f"Migrations-Modul {migration_module_name} hat keine run_migration-Funktion")
            except Exception as e:
                failed_migrations += 1
                logger.error(f"Fehler beim Ausführen der Migration {migration_module_name}: {e}")
    
    logger.info(f"Migrations-Durchlauf abgeschlossen: {successful_migrations} erfolgreich, {failed_migrations} fehlgeschlagen")
    return successful_migrations, failed_migrations


def run_single_migration(app, migration_name):
    """
    Führt eine einzelne Migration aus.
    
    Args:
        app: Flask-App
        migration_name: Name des Migrations-Moduls
        
    Returns:
        bool: True bei Erfolg, False bei Fehler
    """
    logger.info(f"Starte einzelne Migration: {migration_name}")
    
    with app.app_context():
        try:
            # Migrations-Tabelle erstellen, falls nicht vorhanden
            db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS migrations (
                id VARCHAR(200) PRIMARY KEY,
                description TEXT,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """))
            db.session.commit()
            logger.info("Migrations-Tabelle überprüft/erstellt")
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Migrations-Tabelle: {e}")
            return False
        
        try:
            # Migrations-Modul importieren
            migration_module = importlib.import_module(f"migrations.{migration_name}")
            
            # Migration-ID und Beschreibung abrufen oder generieren
            migration_id = getattr(migration_module, "MIGRATION_ID", migration_name)
            migration_description = getattr(migration_module, "MIGRATION_DESCRIPTION", f"Migration {migration_id}")
            
            # Prüfen, ob die Migration bereits angewendet wurde
            result = db.session.execute(
                text("SELECT id FROM migrations WHERE id = :id"),
                {"id": migration_id}
            ).fetchone()
            
            if result:
                logger.info(f"Migration {migration_id} wurde bereits angewendet, überspringe...")
                return True
            
            # Migration ausführen
            if hasattr(migration_module, "run_migration") and inspect.isfunction(migration_module.run_migration):
                logger.info(f"Führe Migration {migration_id} aus...")
                return migration_module.run_migration()
            else:
                logger.warning(f"Migrations-Modul {migration_name} hat keine run_migration-Funktion")
                return False
        except Exception as e:
            logger.error(f"Fehler beim Ausführen der Migration {migration_name}: {e}")
            return False


if __name__ == "__main__":
    """
    Hauptausführung des Migration-Scripts.
    
    Nutzung:
        python run_migrations.py              - Führt alle Migrationen aus
        python run_migrations.py [MODULE]     - Führt eine einzelne Migration aus
    """
    app = create_app()
    
    if len(sys.argv) == 1:
        # Alle Migrationen ausführen
        successful, failed = run_migrations(app)
        sys.exit(0 if failed == 0 else 1)
    elif len(sys.argv) == 2:
        # Einzelne Migration ausführen
        migration_name = sys.argv[1]
        success = run_single_migration(app, migration_name)
        sys.exit(0 if success else 1)
    else:
        logger.error("Ungültige Argumente. Verwendung: python run_migrations.py [MODULE]")
        sys.exit(1) 