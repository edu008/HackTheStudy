"""
SQLAlchemy-Modelle für den Worker (Angepasst für separate Dateien).
"""
import uuid
import os 
import logging
from datetime import datetime

from sqlalchemy import (Column, String, Text, Integer, DateTime, Boolean, 
                        ForeignKey, BigInteger, JSON, LargeBinary, 
                        create_engine)
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from config.config import config 

logger = logging.getLogger(__name__)
Base = declarative_base()

# Datenbankverbindungsfunktion
def get_db_session():
    """Erstellt eine neue Datenbankverbindung."""
    db_url = config.database_url
    if not db_url:
        logger.error("DATABASE_URL nicht in der Konfiguration gefunden!")
        raise ValueError("DATABASE_URL ist nicht konfiguriert.")
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()

# --- Modelldefinitionen --- 

class User(Base):
    """Nur ID für FKs benötigt."""
    __tablename__ = 'user'
    id = Column(String(36), primary_key=True)
    # Minimale Definition für den Worker

class Upload(Base):
    """Repräsentiert einen gesamten Upload-Vorgang."""
    __tablename__ = 'upload'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), nullable=False, unique=True, index=True)
    user_id = Column(String(36), ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    last_used_at = Column(DateTime, nullable=True, index=True)
    overall_processing_status = Column(String(50), nullable=True, index=True, default='pending')
    error_message = Column(Text, nullable=True)
    upload_metadata = Column(JSON, nullable=True) # z.B. { "language": "de" }

    # Beziehung zu den einzelnen Dateien dieses Uploads
    files = relationship("UploadedFile", back_populates="upload", cascade="all, delete-orphan", lazy="dynamic")

    # Beziehungen zu generierten Daten (bleiben auf Upload-Ebene)
    topics = relationship('Topic', backref='upload', lazy='dynamic', cascade="all, delete-orphan")
    questions = relationship('Question', backref='upload', lazy='dynamic', cascade="all, delete-orphan")
    flashcards = relationship('Flashcard', backref='upload', lazy='dynamic', cascade="all, delete-orphan")

class UploadedFile(Base):
    """Repräsentiert eine einzelne hochgeladene Datei innerhalb eines Uploads."""
    __tablename__ = 'uploaded_file' 
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = Column(String(36), ForeignKey('upload.id', ondelete='CASCADE'), nullable=False, index=True)
    file_index = Column(Integer, nullable=True) # Optional: Reihenfolge/Slot (1-5)
    file_name = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    file_content = Column(LargeBinary, nullable=False)
    extracted_text = Column(Text, nullable=True)
    extraction_status = Column(String(50), nullable=True, index=True, default='pending')
    extraction_info = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Beziehung zurück zum übergeordneten Upload
    upload = relationship("Upload", back_populates="files")

# --- Andere vom Worker benötigte Modelle --- 

class ProcessingTask(Base):
    # Unverändert, außer ggf. FK zu uploaded_file_id hinzufügen?
    __tablename__ = 'processing_task'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = Column(String(36), ForeignKey('upload.id', ondelete='CASCADE'), nullable=True, index=True)
    # uploaded_file_id = Column(String(36), ForeignKey('uploaded_file.id', ondelete='CASCADE'), nullable=True, index=True)
    session_id = Column(String(36), nullable=False, index=True)
    task_type = Column(String(50), nullable=False, index=True)
    status = Column(String(50), nullable=False, default='pending', index=True)
    priority = Column(Integer, nullable=False, default=5)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    result_data = Column(JSON, nullable=True)
    task_metadata = Column(JSON, nullable=True)

class Flashcard(Base):
    __tablename__ = 'flashcard'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = Column(String(36), ForeignKey('upload.id', ondelete='CASCADE'), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    tags = Column(JSON, nullable=True)

class Topic(Base):
    __tablename__ = 'topic'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = Column(String(36), ForeignKey('upload.id', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String(200), nullable=False, index=True)
    is_main_topic = Column(Boolean, nullable=True, index=True) 
    parent_id = Column(String(36), ForeignKey('topic.id', ondelete='CASCADE'), nullable=True, index=True)
    description = Column(Text, nullable=True)
    is_key_term = Column(Boolean, nullable=True, index=True)
    subtopics = relationship('Topic', backref='parent_topic', remote_side=[id], cascade="all, delete-orphan", single_parent=True)

class Question(Base):
    __tablename__ = 'question'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = Column(String(36), ForeignKey('upload.id', ondelete='CASCADE'), nullable=False, index=True)
    text = Column(String(500), nullable=False)
    options = Column(JSON, nullable=False)
    correct_answer = Column(Integer, nullable=False)
    explanation = Column(String(1000), nullable=True)

class UserActivity(Base):
    __tablename__ = 'user_activity'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    session_id = Column(String(36), nullable=True, index=True)
    upload_id = Column(String(36), ForeignKey('upload.id', ondelete='CASCADE'), nullable=True, index=True)
    main_topic = Column(Text, nullable=True) 
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
