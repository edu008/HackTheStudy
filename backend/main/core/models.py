"""
Basis-Datenbankmodelle für den API-Container.
Integriert auch Datenbankinitialisierung und Verwaltungsfunktionen.
"""

import os
import logging
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from sqlalchemy.exc import SQLAlchemyError
from flask import current_app

# Logger konfigurieren
logger = logging.getLogger(__name__)

# SQLAlchemy-Instanz erstellen
db = SQLAlchemy()

# Datenbankinitialisierung und -verwaltung
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

def check_db_connection():
    """
    Überprüft die Datenbankverbindung.
    Gibt True zurück, wenn die Verbindung funktioniert, sonst False.
    """
    try:
        db.session.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Datenbankverbindungsfehler: {str(e)}")
        return False

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

    def to_dict(self):
        """Konvertiert das Model in ein Dictionary."""
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'avatar': self.avatar,
            'oauth_provider': self.oauth_provider,
            'oauth_id': self.oauth_id,
            'credits': self.credits
        }

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

    def to_dict(self):
        """Konvertiert das Model in ein Dictionary."""
        return {
            'id': self.id,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'file_name_1': self.file_name_1,
            'file_name_2': self.file_name_2,
            'file_name_3': self.file_name_3,
            'file_name_4': self.file_name_4,
            'file_name_5': self.file_name_5,
            'upload_date': self.upload_date.isoformat() if self.upload_date else None,
            'content': self.content,
            'token_count': self.token_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'processing_status': self.processing_status
        }

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

    def to_dict(self):
        """Konvertiert das Model in ein Dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'activity_type': self.activity_type,
            'title': self.title,
            'main_topic': self.main_topic,
            'subtopics': self.subtopics,
            'session_id': self.session_id,
            'details': self.details,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

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

    def to_dict(self):
        """Konvertiert das Model in ein Dictionary."""
        return {
            'id': self.id,
            'upload_id': self.upload_id,
            'source_id': self.source_id,
            'target_id': self.target_id,
            'label': self.label
        }

class Flashcard(db.Model):
    """Modell für Lernkarten."""
    __tablename__ = 'flashcard'
    
    id = db.Column(db.String(36), primary_key=True)
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)

    def to_dict(self):
        """Konvertiert das Model in ein Dictionary."""
        return {
            'id': self.id,
            'upload_id': self.upload_id,
            'question': self.question,
            'answer': self.answer
        }

class OAuthToken(db.Model):
    """Modell für OAuth Authentifizierungs-Tokens."""
    __tablename__ = 'o_auth_token'
    
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)

    def to_dict(self):
        """Konvertiert das Model in ein Dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'provider': self.provider,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }

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

    def to_dict(self):
        """Konvertiert das Model in ein Dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'amount': self.amount,
            'credits': self.credits,
            'payment_method': self.payment_method,
            'transaction_id': self.transaction_id,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Question(db.Model):
    """Modell für Fragen/Quiz zu Uploads."""
    __tablename__ = 'question'
    
    id = db.Column(db.String(36), primary_key=True)
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id'), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    options = db.Column(db.JSON, nullable=False)
    correct_answer = db.Column(db.Integer, nullable=False)
    explanation = db.Column(db.String(1000), nullable=True)

    def to_dict(self):
        """Konvertiert das Model in ein Dictionary."""
        return {
            'id': self.id,
            'upload_id': self.upload_id,
            'text': self.text,
            'options': self.options,
            'correct_answer': self.correct_answer,
            'explanation': self.explanation
        }

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

    def to_dict(self):
        """Konvertiert das Model in ein Dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'model': self.model,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'cost': self.cost,
            'endpoint': self.endpoint,
            'function_name': self.function_name,
            'cached': self.cached,
            'request_metadata': self.request_metadata
        }

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
    
    # Beziehungen zu Verbindungen
    outgoing_connections = db.relationship('Connection', foreign_keys='Connection.source_id', 
                                         backref='source_topic', lazy='dynamic')
    incoming_connections = db.relationship('Connection', foreign_keys='Connection.target_id', 
                                         backref='target_topic', lazy='dynamic')

    def to_dict(self):
        """Konvertiert das Model in ein Dictionary."""
        return {
            'id': self.id,
            'upload_id': self.upload_id,
            'name': self.name,
            'is_main_topic': self.is_main_topic,
            'parent_id': self.parent_id,
            'description': self.description,
            'is_key_term': self.is_key_term
        } 