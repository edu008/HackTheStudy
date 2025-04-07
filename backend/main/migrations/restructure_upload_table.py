# backend/main/migrations/restructure_upload_table.py
import os
import logging
from sqlalchemy import create_engine, text, MetaData, Table, Column, String, DateTime, JSON, Text, Integer, BigInteger, LargeBinary, Boolean, ForeignKey
from sqlalchemy.schema import DropTable, CreateTable, DropConstraint, AddConstraint, ForeignKeyConstraint, PrimaryKeyConstraint
from sqlalchemy.inspection import inspect
from sqlalchemy.exc import NoSuchTableError, ProgrammingError
from sqlalchemy.dialects import postgresql # Für JSONB etc.
from sqlalchemy.types import TypeEngine # Für Typvergleich
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Lade .env aus dem übergeordneten Verzeichnis
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir)) # Gehe zwei Ebenen hoch zum Projekt-Root
dotenv_path = os.path.join(project_root, '.env')
if os.path.exists(dotenv_path):
    logger.info(f"Lade .env-Datei von: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path)
else:
    logger.warning(f".env-Datei nicht gefunden unter: {dotenv_path}")

# --- KONFIGURATION ---
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    logger.error("DATABASE_URL nicht in der Umgebung oder .env gefunden.")
    exit(1)
# ---------------------

def _table_exists(connection, table_name):
    """Prüft, ob eine Tabelle existiert."""
    try:
        insp = inspect(connection.engine)
        return insp.has_table(table_name)
    except Exception as e:
        logger.warning(f"Fehler beim Prüfen der Existenz von Tabelle '{table_name}': {e}")
        return False # Im Zweifel annehmen, dass sie nicht existiert

def _column_exists(connection, table_name, column_name):
    """Prüft, ob eine Spalte in einer Tabelle existiert."""
    if not _table_exists(connection, table_name):
        return False
    try:
        insp = inspect(connection.engine)
        columns = [col['name'] for col in insp.get_columns(table_name)]
        return column_name in columns
    except Exception as e:
        logger.warning(f"Fehler beim Prüfen der Spalte '{column_name}' in Tabelle '{table_name}': {e}")
        return False

def run_manual_migration():
    logger.info(f"Verbinde mit Datenbank: {DATABASE_URL[:30]}...")
    try:
        engine = create_engine(DATABASE_URL)
        connection = engine.connect()
        transaction = connection.begin()
    except Exception as e:
        logger.error(f"Fehler beim Verbinden mit der Datenbank: {e}")
        return

    try:
        logger.info("----------------------------------------------------------")
        logger.info("Starte Manuelle Migration: Restrukturierung Upload/File")
        logger.info("----------------------------------------------------------")

        # Metadaten für Reflexion und Tabellenerstellung
        meta = MetaData()
        Base = declarative_base(metadata=meta)

        # --- Schritt 0: Fehlende Spalten hinzufügen (z.B. 'tags') ---
        # Füge dies *vor* dem Löschen ein, falls alte Daten mit Kaskaden Probleme machen
        tables_to_check = {
            'flashcard': {'tags': JSON},
            'question': {'tags': JSON},
            'topic': {'tags': JSON}
        }
        logger.info("Prüfe und füge ggf. fehlende 'tags'-Spalten hinzu...")
        for table_name, columns_to_add in tables_to_check.items():
             if not _table_exists(connection, table_name):
                 logger.warning(f"Tabelle '{table_name}' existiert nicht, überspringe Spaltenprüfung.")
                 continue
             for col_name, col_type in columns_to_add.items():
                 if not _column_exists(connection, table_name, col_name):
                     logger.info(f"  -> Füge Spalte '{col_name}' zur Tabelle '{table_name}' hinzu...")
                     try:
                         # Verwende rohes SQL statt AddColumn DDL
                         # Stelle sicher, dass der Typ JSONB oder JSON für PostgreSQL passt
                         # Passe den Typ ggf. an deine Datenbank an (z.B. JSON für SQLite)
                         sql_type = "JSONB" # Für PostgreSQL
                         # sql_type = "JSON" # Ggf. für andere DBs
                         connection.execute(text(f'ALTER TABLE \"{table_name}\" ADD COLUMN \"{col_name}\" {sql_type} NULL'))
                         logger.info(f"     Spalte '{col_name}' erfolgreich zu '{table_name}' hinzugefügt.")
                     except Exception as add_col_err:
                         logger.error(f"     Fehler beim Hinzufügen der Spalte '{col_name}' zu '{table_name}': {add_col_err}")
                 else:
                     logger.info(f"  Spalte '{col_name}' existiert bereits in Tabelle '{table_name}'.")
        logger.info("Spaltenprüfung abgeschlossen.")


        # Frage nach Bestätigung für Löschvorgang
        logger.warning("ACHTUNG: Dieses Skript löscht die Tabellen 'upload' und 'uploaded_file' (falls vorhanden) und erstellt sie neu!")
        logger.warning("Abhängige Daten in anderen Tabellen werden durch CASCADE-Regeln ebenfalls beeinflusst!")
        confirm = input("Möchtest du fortfahren mit dem Löschen und Neuerstellen von 'upload' und 'uploaded_file'? (ja/nein): ")
        if confirm.lower() != 'ja':
            logger.info("Vorgang abgebrochen.")
            transaction.rollback()
            connection.close()
            return

        # --- Schritt 1: Abhängigkeiten entfernen (optional, aber sicherer) ---
        # Obwohl CASCADE das meiste erledigen sollte, kann es explizit sein.
        # Insbesondere, wenn ON DELETE Regeln sich geändert haben oder nicht sicher sind.
        # Hier nur ein Beispiel, wie man es machen könnte (auskommentiert):
        # dependent_tables_fk = [...]
        # for table_name in dependent_tables_fk:
        #     try:
        #         logger.info(f"Versuche Fremdschlüssel für Tabelle '{table_name}' zu löschen...")
        #         # Finde und lösche FKs die auf 'upload' zeigen
        #     except Exception as e:
        #         logger.warning(...)

        # --- Schritt 2: Alte Tabellen löschen ---
        logger.info("Lösche alte Tabelle 'uploaded_file' (falls vorhanden)...")
        connection.execute(DropTable(Table('uploaded_file', meta), if_exists=True))
        logger.info("Alte Tabelle 'uploaded_file' gelöscht (falls vorhanden).")

        logger.info("Lösche alte Tabelle 'upload' (falls vorhanden)...")
        connection.execute(DropTable(Table('upload', meta), if_exists=True))
        logger.info("Alte Tabelle 'upload' gelöscht (falls vorhanden).")

        # --- Schritt 3: Neue Tabellen erstellen ---
        logger.info("Reflektiere Tabelle 'user' für ForeignKey...")
        try:
            # Reflektiere nur, wenn sie existiert, ansonsten FK ohne Validierung
            if _table_exists(connection, 'user'):
                 user_table = Table('user', meta, autoload_with=engine)
                 logger.info("Tabelle 'user' erfolgreich reflektiert.")
                 user_fk_column = Column('user_id', String(36), ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
            else:
                 logger.warning("Tabelle 'user' nicht gefunden. Erstelle FK ohne Validierung.")
                 # Erstelle FK ohne Validierung oder lasse user_id weg, je nach Anforderung
                 user_fk_column = Column('user_id', String(36), nullable=True, index=True) # Ohne FK Constraint
        except Exception as reflect_err:
            logger.error(f"Fehler beim Reflektieren der Tabelle 'user': {reflect_err}")
            logger.error("Stelle sicher, dass die Tabelle 'user' existiert oder passe das Skript an.")
            transaction.rollback()
            connection.close()
            return

        logger.info("Erstelle neue Tabelle 'upload'...")
        new_upload_table = Table('upload', meta,
            Column('id', String(36), primary_key=True),
            Column('session_id', String(36), nullable=False, unique=True, index=True),
            user_fk_column, # Füge die (ggf. reflektierte) Spalte hinzu
            Column('created_at', DateTime, default=datetime.utcnow, index=True),
            Column('updated_at', DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True),
            Column('last_used_at', DateTime, nullable=True, index=True),
            Column('overall_processing_status', String(50), nullable=True, index=True, default='pending'),
            Column('error_message', Text, nullable=True),
            Column('upload_metadata', JSON, nullable=True),
            extend_existing=True
        )
        connection.execute(CreateTable(new_upload_table))
        logger.info("Neue Tabelle 'upload' erstellt.")

        logger.info("Erstelle neue Tabelle 'uploaded_file'...")
        new_uploaded_file_table = Table('uploaded_file', meta,
            Column('id', String(36), primary_key=True),
            Column('upload_id', String(36), ForeignKey('upload.id', ondelete='CASCADE'), nullable=False, index=True),
            Column('file_index', Integer, nullable=True),
            Column('file_name', String(255), nullable=False),
            Column('mime_type', String(100), nullable=True),
            Column('file_size', BigInteger, nullable=True),
            Column('file_content', LargeBinary, nullable=False),
            Column('extracted_text', Text, nullable=True),
            Column('extraction_status', String(50), nullable=True, index=True, default='pending'),
            Column('extraction_info', JSON, nullable=True),
            Column('created_at', DateTime, default=datetime.utcnow),
            extend_existing=True
        )
        connection.execute(CreateTable(new_uploaded_file_table))
        logger.info("Neue Tabelle 'uploaded_file' erstellt.")

        # Schritt 4: Fremdschlüssel wiederherstellen (ist nicht mehr nötig, da bei Tabellenerstellung definiert)
        # logger.info("Stelle Fremdschlüssel zu anderen Tabellen wieder her...")
        # ... (Code war hier, aber FKs werden jetzt direkt erstellt)

        transaction.commit()
        logger.info("----------------------------------------------------------")
        logger.info("Manuelle Migration erfolgreich abgeschlossen.")
        logger.info("----------------------------------------------------------")

    except Exception as e:
        logger.error(f"Fehler während der manuellen Migration: {e}", exc_info=True)
        logger.error("Führe Rollback durch...")
        transaction.rollback()
    finally:
        if 'connection' in locals() and connection:
            connection.close()
            logger.info("Datenbankverbindung geschlossen.")

if __name__ == "__main__":
    run_manual_migration()
