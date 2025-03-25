"""
Modul zur Initialisierung und Verwaltung der Datenbankverbindung.
"""

import os
import logging
from flask import Flask, current_app
from sqlalchemy.exc import SQLAlchemyError

from .models import db, User, Upload, UserActivity

# Logger konfigurieren
logger = logging.getLogger(__name__)

def init_db():
    """
    Initialisiert die Datenbank und erstellt alle Tabellen, falls sie noch nicht existieren.
    """
    try:
        # Erstelle alle definierten Tabellen
        db.create_all()
        logger.info("Datenbanktabellen erfolgreich erstellt/überprüft")
        
        # Optional: Initialdaten einfügen, falls nötig
        _insert_initial_data()
        
        return True
    except SQLAlchemyError as e:
        logger.error(f"Fehler bei der Datenbankinitialisierung: {str(e)}")
        return False

def _insert_initial_data():
    """
    Fügt initiale Daten in die Datenbank ein (z.B. Admin-Benutzer).
    Diese Funktion sollte nur einmal und nur in bestimmten Umgebungen ausgeführt werden.
    """
    try:
        # Überprüfe, ob wir in einer Entwicklungsumgebung sind
        if os.environ.get('ENVIRONMENT') == 'development':
            # Nur ausführen, wenn keine Benutzer vorhanden sind
            if User.query.count() == 0:
                logger.info("Keine Benutzer in der Datenbank gefunden, erstelle Test-Admin-Benutzer")
                
                # Erstelle einen Admin-Benutzer für Testzwecke
                admin_user = User(
                    id="00000000-0000-0000-0000-000000000000",
                    email="admin@example.com",
                    name="Admin User",
                    settings={"role": "admin", "is_test_account": True}
                )
                
                db.session.add(admin_user)
                db.session.commit()
                
                logger.info("Test-Admin-Benutzer erfolgreich erstellt")
    except SQLAlchemyError as e:
        logger.error(f"Fehler beim Einfügen von Initialdaten: {str(e)}")
        # Wir wollen den Startvorgang nicht abbrechen, daher kein Raise
        db.session.rollback()

def get_connection_info():
    """
    Gibt Informationen über die aktuelle Datenbankverbindung zurück.
    Nützlich für Diagnostik und Monitoring.
    """
    try:
        engine = db.engine
        
        # Basisdaten über die Verbindung sammeln
        connection_info = {
            "dialect": engine.dialect.name,
            "driver": engine.dialect.driver,
            "pool_size": engine.pool.size(),
            "pool_timeout": engine.pool.timeout(),
            "database": current_app.config.get('SQLALCHEMY_DATABASE_URI', '').split('/')[-1].split('?')[0]
        }
        
        # Statistiken über Tabellen abrufen
        stats = {}
        stats['users'] = User.query.count()
        stats['uploads'] = Upload.query.count()
        stats['activities'] = UserActivity.query.count()
        
        connection_info['table_stats'] = stats
        
        return connection_info
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Verbindungsinformationen: {str(e)}")
        return {"error": str(e)} 