"""
Datenbank-Modelle für den Worker-Microservice.
Diese Datei verwendet die gleichen Modelle wie der Hauptserver, um mit der Datenbank zu interagieren.
"""
import os
import json
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)
logger.info("Worker-spezifische models.py mit echter DB-Verbindung geladen")

# SQLAlchemy-Instanz erstellen
db = SQLAlchemy()

# Dummy-Definition für SQLAlchemy-Kompatibilität, da der Worker nur mit Redis arbeitet
class DummyDatabase:
    def __init__(self):
        self.Model = Model
    
    def create_all(self, *args, **kwargs):
        logger.info("Dummy-Datenbank create_all aufgerufen - wird ignoriert im Worker")
        pass
    
    def session(self, *args, **kwargs):
        logger.info("Dummy-Datenbank session aufgerufen - wird ignoriert im Worker")
        return DummySession()

class DummySession:
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    
    def commit(self):
        pass
    
    def rollback(self):
        pass
    
    def close(self):
        pass

class Model:
    """
    Basisklasse für alle Modelle im Worker-Microservice.
    Diese Klasse dient nur der API-Kompatibilität, da der Worker
    vorrangig mit Redis arbeitet und keine eigene Datenbank verwendet.
    """
    id = None
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert das Modell in ein Dictionary."""
        result = {}
        for key in dir(self):
            # Überspringe private und dunder Methoden und Eigenschaften
            if key.startswith('_'):
                continue
            
            value = getattr(self, key)
            # Überspringe Methoden
            if callable(value):
                continue
                
            # Sonderbehandlung für datetime-Objekte
            if isinstance(value, datetime):
                value = value.isoformat()
                
            result[key] = value
            
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Model':
        """Erstellt eine Modell-Instanz aus einem Dictionary."""
        return cls(**data)
    
    @classmethod
    def query(cls):
        """
        Dummy-Methode für Kompatibilität mit Flask-SQLAlchemy.
        """
        return DummyQuery(cls)

class DummyQuery:
    def __init__(self, model_class):
        self.model_class = model_class
        
    def filter_by(self, **kwargs):
        """
        Dummy-Implementation von filter_by.
        """
        return self
        
    def first(self):
        """
        Dummy-Implementation von first.
        """
        return None
        
    def all(self):
        """
        Dummy-Implementation von all.
        """
        return []

# Erstelle eine globale Instanz der Dummy-Datenbank
db = DummyDatabase()

# Definiere die gleichen Modelle wie im Hauptserver
class User(db.Model):
    """Benutzermodell für die Authentifizierung und Profilinformationen."""
    __tablename__ = 'user'
    
    id = db.Column(db.String(36), primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    avatar = db.Column(db.String(200), nullable=True)
    oauth_provider = db.Column(db.String(50), nullable=True)
    oauth_id = db.Column(db.String(100), nullable=True)
    credits = db.Column(db.Integer, nullable=True)
    
    # Beziehungen
    uploads = db.relationship('Upload', backref='user', lazy=True)
    activities = db.relationship('UserActivity', backref='user', lazy=True)
    payments = db.relationship('Payment', backref='user', lazy=True)
    oauth_tokens = db.relationship('OAuthToken', backref='user', lazy=True)
    token_usages = db.relationship('TokenUsage', backref='user', lazy=True)

class Upload(db.Model):
    """Modell für hochgeladene Dateien und Dokumente."""
    __tablename__ = 'upload'
    
    id = db.Column(db.String(36), primary_key=True)
    session_id = db.Column(db.String(36), nullable=False, unique=True, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    file_name_1 = db.Column(db.String(200), nullable=True)
    file_name_2 = db.Column(db.String(200), nullable=True)
    file_name_3 = db.Column(db.String(200), nullable=True)
    file_name_4 = db.Column(db.String(200), nullable=True)
    file_name_5 = db.Column(db.String(200), nullable=True)
    upload_date = db.Column(db.DateTime, nullable=True, index=True)
    content = db.Column(db.Text, nullable=True)
    token_count = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=True, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    last_used_at = db.Column(db.DateTime, nullable=True, index=True)
    processing_status = db.Column(db.String(50), nullable=True, index=True)
    
    # Beziehungen
    topics = db.relationship('Topic', backref='upload', lazy=True, cascade="all, delete-orphan")
    questions = db.relationship('Question', backref='upload', lazy=True, cascade="all, delete-orphan")
    flashcards = db.relationship('Flashcard', backref='upload', lazy=True, cascade="all, delete-orphan")
    connections = db.relationship('Connection', backref='upload', lazy=True, foreign_keys='Connection.upload_id', cascade="all, delete-orphan")

class Topic(db.Model):
    """Modell für Themen aus Uploads."""
    __tablename__ = 'topic'
    
    id = db.Column(db.String(36), primary_key=True)
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    is_main_topic = db.Column(db.Boolean, nullable=True, index=True)
    parent_id = db.Column(db.String(36), db.ForeignKey('topic.id', ondelete='CASCADE'), nullable=True, index=True)
    description = db.Column(db.Text, nullable=True)
    is_key_term = db.Column(db.Boolean, nullable=True, index=True)
    
    # Rekursive Beziehung für Hierarchie
    subtopics = db.relationship(
        'Topic', 
        backref=db.backref('parent', remote_side=[id]),
        cascade="all, delete-orphan",
        single_parent=True
    )

class Connection(db.Model):
    """Modell für Verbindungen zwischen Themen/Elementen."""
    __tablename__ = 'connection'
    
    id = db.Column(db.String(36), primary_key=True)
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id'), nullable=False)
    source_id = db.Column(db.String(36), db.ForeignKey('topic.id'), nullable=False, index=True)
    target_id = db.Column(db.String(36), db.ForeignKey('topic.id'), nullable=False, index=True)
    label = db.Column(db.String(500), nullable=False)
    
    # Beziehungen zu Topics
    source = db.relationship('Topic', foreign_keys=[source_id])
    target = db.relationship('Topic', foreign_keys=[target_id])

class Flashcard(db.Model):
    """Modell für Lernkarten."""
    __tablename__ = 'flashcard'
    
    id = db.Column(db.String(36), primary_key=True)
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)

class Question(db.Model):
    """Modell für Fragen/Quiz zu Uploads."""
    __tablename__ = 'question'
    
    id = db.Column(db.String(36), primary_key=True)
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id'), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    options = db.Column(db.JSON, nullable=False)
    correct_answer = db.Column(db.Integer, nullable=False)
    explanation = db.Column(db.String(1000), nullable=True)

class UserActivity(db.Model):
    """Modell für Benutzeraktivitäten."""
    __tablename__ = 'user_activity'
    
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    main_topic = db.Column(db.String(200), nullable=True)
    subtopics = db.Column(db.JSON, nullable=True)
    session_id = db.Column(db.String(36), nullable=True)
    details = db.Column(db.JSON, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=True)

class OAuthToken(db.Model):
    """Modell für OAuth Authentifizierungs-Tokens."""
    __tablename__ = 'o_auth_token'
    
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)

class Payment(db.Model):
    """Modell für Zahlungen und Kreditkäufe."""
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
    """Modell für Token-Nutzungsverfolgung."""
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

# Hilfsfunktion zur Initialisierung der DB mit der richtigen URL
def init_db(app):
    """
    Initialisiert die Datenbankverbindung mit der Anwendung.
    
    Args:
        app: Die Flask-App-Instanz
    """
    # Konfiguriere die Datenbank-URL
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        # Alternativ können wir die URL aus den Einzelkomponenten aufbauen
        db_user = os.environ.get('POSTGRES_USER')
        db_pass = os.environ.get('POSTGRES_PASSWORD')
        db_host = os.environ.get('POSTGRES_HOST')
        db_port = os.environ.get('POSTGRES_PORT')
        db_name = os.environ.get('POSTGRES_DB')
        
        # Prüfe, ob alle notwendigen Umgebungsvariablen gesetzt sind
        if all([db_user, db_pass, db_host, db_port, db_name]):
            database_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}?sslmode=require"
        else:
            logger.error("Fehlende Datenbank-Umgebungsvariablen - keine Datenbankverbindung möglich")
            database_url = "sqlite:///:memory:"  # Fallback zu In-Memory SQLite
    
    # Setze die Datenbank-URL in der App-Konfiguration
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialisiere die DB mit der App
    db.init_app(app)
    
    logger.info(f"Datenbank initialisiert mit URL: {database_url.split('@')[0].split('://')[0]}://*****@{database_url.split('@')[1]}")
    
    return db 