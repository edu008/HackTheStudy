"""
Basis-Datenbankmodelle für den API-Container.
Angepasst für separate UploadedFile-Tabelle.
"""
import uuid
import os
import logging
from datetime import datetime
from sqlalchemy import event # Für SQLite Pragma
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship

# Logging
logger = logging.getLogger(__name__)

# SQLAlchemy-Instanz erstellen (wird in app_factory initialisiert)
db = SQLAlchemy()

# --- Modelldefinitionen ---

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.String(36), primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    avatar = db.Column(db.String(200), nullable=True)
    oauth_provider = db.Column(db.String(50), nullable=True)
    oauth_id = db.Column(db.String(100), nullable=True)
    credits = db.Column(db.Integer, nullable=True)

    # Beziehungen
    uploads = db.relationship("Upload", backref="user", lazy="dynamic")
    # payments = db.relationship(...) # Behalte relevante Beziehungen
    # oauth_tokens = db.relationship(...)
    # token_usages = db.relationship(...)
    activities = db.relationship('UserActivity', back_populates='user', lazy='dynamic', cascade="all, delete-orphan") # Angepasst mit back_populates

class Upload(db.Model):
    """Repräsentiert einen gesamten Upload-Vorgang."""
    __tablename__ = 'upload'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = db.Column(db.String(36), nullable=False, unique=True, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    last_used_at = db.Column(db.DateTime, nullable=True, index=True)
    overall_processing_status = db.Column(db.String(50), nullable=True, index=True, default='pending')
    error_message = db.Column(db.Text, nullable=True)
    upload_metadata = db.Column(db.JSON, nullable=True) # z.B. { "language": "de" }

    # Beziehung zu den einzelnen Dateien dieses Uploads
    files = db.relationship("UploadedFile", back_populates="upload", cascade="all, delete-orphan", lazy="dynamic")

    # Beziehungen zu generierten Daten (bleiben auf Upload-Ebene)
    topics = db.relationship('Topic', backref='upload', lazy='dynamic', cascade="all, delete-orphan")
    questions = db.relationship('Question', backref='upload', lazy='dynamic', cascade="all, delete-orphan")
    flashcards = db.relationship('Flashcard', backref='upload', lazy='dynamic', cascade="all, delete-orphan")
    user_activities = db.relationship('UserActivity', back_populates='upload', lazy='dynamic', cascade="all, delete-orphan") # Angepasst mit back_populates


class UploadedFile(db.Model):
    """Repräsentiert eine einzelne hochgeladene Datei innerhalb eines Uploads."""
    __tablename__ = 'uploaded_file'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id', ondelete='CASCADE'), nullable=False, index=True)
    file_index = db.Column(db.Integer, nullable=True) # Optional: Reihenfolge/Slot (1-5)
    file_name = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), nullable=True)
    file_size = db.Column(db.BigInteger, nullable=True)
    file_content = db.Column(db.LargeBinary, nullable=False)
    extracted_text = db.Column(db.Text, nullable=True)
    extraction_status = db.Column(db.String(50), nullable=True, index=True, default='pending')
    extraction_info = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Beziehung zurück zum übergeordneten Upload
    upload = db.relationship("Upload", back_populates="files")


class ProcessingTask(db.Model):
    # Annahme: Diese Tabelle wird von beiden Services genutzt und bleibt gleich
    __tablename__ = 'processing_task'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id', ondelete='CASCADE'), nullable=True, index=True)
    # uploaded_file_id = db.Column(db.String(36), db.ForeignKey('uploaded_file.id', ondelete='CASCADE'), nullable=True, index=True) # Optional hinzufügen
    session_id = db.Column(db.String(36), nullable=False, index=True)
    task_type = db.Column(db.String(50), nullable=False, index=True)
    status = db.Column(db.String(50), nullable=False, default='pending', index=True)
    priority = db.Column(db.Integer, nullable=False, default=5)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    result_data = db.Column(db.JSON, nullable=True)
    task_metadata = db.Column(db.JSON, nullable=True)


class Flashcard(db.Model):
    __tablename__ = 'flashcard'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id', ondelete='CASCADE'), nullable=False, index=True)
    # uploaded_file_id = db.Column(db.String(36), db.ForeignKey('uploaded_file.id', ondelete='CASCADE'), nullable=True, index=True) # Optional hinzufügen
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    tags = db.Column(db.JSON, nullable=True)


class Topic(db.Model):
    __tablename__ = 'topic'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id', ondelete='CASCADE'), nullable=False, index=True)
    # uploaded_file_id = db.Column(db.String(36), db.ForeignKey('uploaded_file.id', ondelete='CASCADE'), nullable=True, index=True) # Optional hinzufügen
    name = db.Column(db.String(200), nullable=False, index=True)
    is_main_topic = db.Column(db.Boolean, nullable=True, index=True)
    parent_id = db.Column(db.String(36), db.ForeignKey('topic.id', ondelete='CASCADE'), nullable=True, index=True)
    description = db.Column(db.Text, nullable=True)
    is_key_term = db.Column(db.Boolean, nullable=True, index=True)

    # Rekursive Beziehung
    subtopics = db.relationship('Topic',
        backref=db.backref('parent_topic', remote_side=[id]), # Eindeutiger Backref-Name
        cascade="all, delete-orphan",
        single_parent=True # Wichtig für delete-orphan
    )


class Question(db.Model):
    __tablename__ = 'question'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id', ondelete='CASCADE'), nullable=False, index=True)
    # uploaded_file_id = db.Column(db.String(36), db.ForeignKey('uploaded_file.id', ondelete='CASCADE'), nullable=True, index=True) # Optional hinzufügen
    text = db.Column(db.String(500), nullable=False)
    options = db.Column(db.JSON, nullable=False)
    correct_answer = db.Column(db.Integer, nullable=False)
    explanation = db.Column(db.String(1000), nullable=True)


class UserActivity(db.Model):
    __tablename__ = 'user_activity'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    session_id = db.Column(db.String(36), nullable=True, index=True)
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id', ondelete='CASCADE'), nullable=True, index=True)
    main_topic = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Korrigierte Beziehungen mit back_populates
    user = db.relationship('User', back_populates='activities')
    upload = db.relationship('Upload', back_populates='user_activities')


# --- Modelle, die eher nur im Main relevant sind (Beispiele) ---

class OAuthToken(db.Model):
    __tablename__ = 'o_auth_token'
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)


class Payment(db.Model):
    __tablename__ = 'payment'
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    credits = db.Column(db.Integer, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    transaction_id = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)


class TokenUsage(db.Model):
    __tablename__ = 'token_usage'
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=True)
    session_id = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=True)
    model = db.Column(db.String(50), nullable=False)
    input_tokens = db.Column(db.Integer, nullable=False)
    output_tokens = db.Column(db.Integer, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    endpoint = db.Column(db.String(100), nullable=True)
    function_name = db.Column(db.String(100), nullable=True)
    cached = db.Column(db.Boolean, nullable=True)
    request_metadata = db.Column(db.JSON, nullable=True)


# --- DB Initialisierung und Helper (gehören eher in app_factory oder __init__) ---

def init_db(app):
    """Initialisiert die Datenbank."""
    # Diese Funktion könnte in app_factory aufgerufen werden
    with app.app_context():
        logger.info("Initialisiere Datenbank-Tabellen (falls nötig)...")
        # db.drop_all() # Nur für Entwicklung/Reset
        db.create_all()
        logger.info("Datenbank-Tabellen initialisiert.")

        # Event Listener für SQLite FKs
        @event.listens_for(db.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
             if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
                 cursor = dbapi_connection.cursor()
                 cursor.execute("PRAGMA foreign_keys=ON")
                 cursor.close()