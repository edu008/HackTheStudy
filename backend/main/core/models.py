from flask_sqlalchemy import SQLAlchemy
import uuid
from datetime import datetime
from sqlalchemy import Index, event

def generate_uuid():
    """Erzeugt eine UUID für Primärschlüssel."""
    return str(uuid.uuid4())

# Initialisiere SQLAlchemy
db = SQLAlchemy()

class User(db.Model):
    """
    Repräsentiert einen Benutzer im System.
    Speichert Authentifizierungsinformationen und Benutzerdaten.
    """
    __tablename__ = 'user'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    avatar = db.Column(db.String(200))
    oauth_provider = db.Column(db.String(50))
    oauth_id = db.Column(db.String(100))
    credits = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Beziehungen
    token_usages = db.relationship('TokenUsage', back_populates='user', cascade="all, delete-orphan")
    uploads = db.relationship('Upload', back_populates='user', cascade="all, delete-orphan")
    payments = db.relationship('Payment', back_populates='user', cascade="all, delete-orphan")
    activities = db.relationship('UserActivity', back_populates='user', cascade="all, delete-orphan")
    oauth_tokens = db.relationship('OAuthToken', back_populates='user', cascade="all, delete-orphan")
    
    # Indizes
    __table_args__ = (
        Index('idx_user_oauth', oauth_provider, oauth_id),
    )
    
    def __repr__(self):
        return f"<User {self.id} {self.email}>"

class Upload(db.Model):
    """
    Speichert hochgeladene Dateien und extrahierte Inhalte.
    Bildet die Grundlage für die Generierung von Lernmaterialien.
    """
    __tablename__ = 'upload'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    session_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id', ondelete='CASCADE'), nullable=True, index=True)
    file_name_1 = db.Column(db.String(200), nullable=True)
    file_name_2 = db.Column(db.String(200), nullable=True)
    file_name_3 = db.Column(db.String(200), nullable=True)
    file_name_4 = db.Column(db.String(200), nullable=True)
    file_name_5 = db.Column(db.String(200), nullable=True)
    upload_date = db.Column(db.DateTime, default=db.func.current_timestamp())
    content = db.Column(db.Text)
    token_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    last_used_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp(), index=True)
    processing_status = db.Column(db.String(50), default="pending", index=True)  # pending, processing, completed, failed
    
    # Beziehungen
    user = db.relationship('User', back_populates='uploads')
    flashcards = db.relationship('Flashcard', back_populates='upload', cascade="all, delete-orphan")
    questions = db.relationship('Question', back_populates='upload', cascade="all, delete-orphan")
    topics = db.relationship('Topic', back_populates='upload', cascade="all, delete-orphan")
    
    # Indizes
    __table_args__ = (
        Index('idx_upload_user_date', user_id, upload_date.desc()),
        Index('idx_upload_status_date', processing_status, upload_date.desc()),
    )
    
    def __repr__(self):
        return f"<Upload {self.id} session={self.session_id} status={self.processing_status}>"

class Flashcard(db.Model):
    """
    Repräsentiert eine Lernkarte mit Frage und Antwort.
    """
    __tablename__ = 'flashcard'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id', ondelete='CASCADE'), nullable=False, index=True)
    question = db.Column(db.String(500), nullable=False)
    answer = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Beziehungen
    upload = db.relationship('Upload', back_populates='flashcards')
    
    # Indizes für Volltextsuche 
    __table_args__ = (
        Index('idx_flashcard_question', 'question'),
        Index('idx_flashcard_upload', 'upload_id', 'id'),
    )
    
    def __repr__(self):
        return f"<Flashcard {self.id} upload={self.upload_id}>"

class Question(db.Model):
    """
    Repräsentiert eine Multiple-Choice-Frage mit Optionen und Erklärung.
    """
    __tablename__ = 'question'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id', ondelete='CASCADE'), nullable=False, index=True)
    text = db.Column(db.String(500), nullable=False)
    options = db.Column(db.JSON, nullable=False)
    correct_answer = db.Column(db.Integer, nullable=False)
    explanation = db.Column(db.String(1000))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Beziehungen
    upload = db.relationship('Upload', back_populates='questions')
    
    # Indizes
    __table_args__ = (
        Index('idx_question_upload', 'upload_id', 'id'),
    )
    
    def __repr__(self):
        return f"<Question {self.id} upload={self.upload_id}>"

class Topic(db.Model):
    """
    Repräsentiert ein Thema oder Unterthema im Lernmaterial.
    Kann hierarchisch strukturiert werden.
    """
    __tablename__ = 'topic'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    is_main_topic = db.Column(db.Boolean, default=False, index=True)
    parent_id = db.Column(db.String(36), db.ForeignKey('topic.id', ondelete='CASCADE'), nullable=True, index=True)
    description = db.Column(db.Text, nullable=True)
    is_key_term = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Beziehungen
    upload = db.relationship('Upload', back_populates='topics')
    children = db.relationship('Topic', backref=db.backref('parent', remote_side=[id]), cascade="all, delete-orphan")
    
    # Indizes
    __table_args__ = (
        Index('idx_topic_upload_main', 'upload_id', 'is_main_topic'),
        Index('idx_topic_parent', 'parent_id'),
        Index('idx_topic_name', 'name'),
    )
    
    def __repr__(self):
        return f"<Topic {self.id} name={self.name} main={self.is_main_topic}>"

class Connection(db.Model):
    """
    Repräsentiert eine Verbindung (Beziehung) zwischen zwei Themen.
    """
    __tablename__ = 'connection'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    upload_id = db.Column(db.String(36), db.ForeignKey('upload.id', ondelete='CASCADE'), nullable=False, index=True)
    source_id = db.Column(db.String(36), db.ForeignKey('topic.id', ondelete='CASCADE'), nullable=False, index=True)
    target_id = db.Column(db.String(36), db.ForeignKey('topic.id', ondelete='CASCADE'), nullable=False, index=True)
    label = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Beziehungen
    source = db.relationship('Topic', foreign_keys=[source_id], backref='outgoing_connections')
    target = db.relationship('Topic', foreign_keys=[target_id], backref='incoming_connections')
    
    # Indizes
    __table_args__ = (
        Index('idx_connection_upload', 'upload_id'),
        Index('idx_connection_source_target', 'source_id', 'target_id'),
    )
    
    def __repr__(self):
        return f"<Connection {self.id} {self.source_id} -> {self.target_id}>"

class UserActivity(db.Model):
    """
    Protokolliert Benutzeraktivitäten für Analysen und Verlauf.
    """
    __tablename__ = 'user_activity'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    activity_type = db.Column(db.String(50), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    main_topic = db.Column(db.String(200))
    subtopics = db.Column(db.JSON)
    session_id = db.Column(db.String(36), db.ForeignKey('upload.session_id', ondelete='SET NULL'), nullable=True, index=True)
    details = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp(), index=True)
    
    # Beziehungen
    user = db.relationship('User', back_populates='activities')
    
    # Indizes
    __table_args__ = (
        Index('idx_activity_user_time', 'user_id', 'timestamp'),
        Index('idx_activity_type_time', 'activity_type', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<UserActivity {self.id} type={self.activity_type} user={self.user_id}>"

class Payment(db.Model):
    """
    Speichert Zahlungsinformationen für Kreditkäufe.
    """
    __tablename__ = 'payment'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    credits = db.Column(db.Integer, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    transaction_id = db.Column(db.String(100), nullable=False, unique=True)
    status = db.Column(db.String(50), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), index=True)
    
    # Beziehungen
    user = db.relationship('User', back_populates='payments')
    
    # Indizes
    __table_args__ = (
        Index('idx_payment_user_date', 'user_id', 'created_at'),
        Index('idx_payment_transaction', 'transaction_id'),
    )
    
    def __repr__(self):
        return f"<Payment {self.id} user={self.user_id} amount={self.amount} status={self.status}>"

class OAuthToken(db.Model):
    """
    Speichert OAuth-Token für externe Dienste.
    """
    __tablename__ = 'oauth_token'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    provider = db.Column(db.String(50), nullable=False)
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Beziehungen
    user = db.relationship('User', back_populates='oauth_tokens')
    
    # Indizes
    __table_args__ = (
        Index('idx_oauth_user_provider', 'user_id', 'provider', unique=True),
    )
    
    def __repr__(self):
        return f"<OAuthToken {self.id} user={self.user_id} provider={self.provider}>"

class TokenUsage(db.Model):
    """
    Speichert die Nutzung von API-Tokens für verschiedene Funktionen.
    Trackt detailliert Token-Nutzung, Kosten und Cache-Status.
    """
    __tablename__ = 'token_usage'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    session_id = db.Column(db.String(255), nullable=True, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    model = db.Column(db.String(50), nullable=False, index=True)
    input_tokens = db.Column(db.Integer, nullable=False)
    output_tokens = db.Column(db.Integer, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    endpoint = db.Column(db.String(100), nullable=True, index=True)
    function_name = db.Column(db.String(100), nullable=True, index=True)
    cached = db.Column(db.Boolean, default=False, index=True)
    request_metadata = db.Column(db.JSON, nullable=True)
    
    # Beziehungen
    user = db.relationship("User", back_populates="token_usages")
    
    # Indizes
    __table_args__ = (
        Index('idx_token_user_time', 'user_id', 'timestamp'),
        Index('idx_token_session_time', 'session_id', 'timestamp'),
        Index('idx_token_model_cached', 'model', 'cached'),
    )
    
    def __repr__(self):
        return f"<TokenUsage {self.id} user={self.user_id} tokens={self.input_tokens}+{self.output_tokens} cost={self.cost}>"

# Event-Listener für Datenbereinigung
@event.listens_for(db.session, 'before_commit')
def validate_models(session):
    """Validiert Modelle vor dem Commit."""
    for obj in session.new:
        if hasattr(obj, 'validate'):
            obj.validate()

# Cache-Invalidierung bei Änderungen
@event.listens_for(db.session, 'after_commit')
def clear_caches(session):
    """Leert Caches nach Änderungen."""
    try:
        from core.redis_client import redis_client
        
        for obj in session.new.union(session.dirty).union(session.deleted):
            model_name = obj.__class__.__name__.lower()
            if hasattr(obj, 'id'):
                cache_key = f"db:{model_name}:{obj.id}"
                redis_client.delete(cache_key)
    except Exception as e:
        # Fehler beim Cache-Löschen sollten den Commit nicht beeinträchtigen
        print(f"Fehler beim Leeren des Caches: {e}")
