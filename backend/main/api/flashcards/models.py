"""
Models-Modul für das Flashcards-Paket
-----------------------------------

Dieses Modul enthält Datenbankoperationen und Hilfsfunktionen für Flashcards:
- Abfrage von Flashcards aus der Datenbank
- Speichern von Flashcards
- Aktualisieren von Statistiken
"""

import logging
from core.models import db, Upload, Flashcard, UserActivity, Topic
from sqlalchemy.exc import SQLAlchemyError
from marshmallow import ValidationError
import json

logger = logging.getLogger(__name__)

def get_flashcards(session_id=None, upload_id=None, flashcard_id=None, limit=None):
    """
    Holt Flashcards aus der Datenbank basierend auf verschiedenen Filterkriterien.
    
    Args:
        session_id: Optional - Die ID der Sitzung
        upload_id: Optional - Die ID des Uploads
        flashcard_id: Optional - Die ID einer bestimmten Lernkarte
        limit: Optional - Die maximale Anzahl der zurückzugebenden Lernkarten
        
    Returns:
        Eine Liste von Flashcard-Objekten
    """
    try:
        query = Flashcard.query
        
        if flashcard_id is not None:
            return query.filter_by(id=flashcard_id).first()
        
        if upload_id is not None:
            query = query.filter_by(upload_id=upload_id)
        
        if session_id is not None:
            # Suche zuerst den Upload mit der session_id
            upload = Upload.query.filter_by(session_id=session_id).first()
            if not upload:
                return []
            query = query.filter_by(upload_id=upload.id)
        
        if limit is not None:
            query = query.limit(limit)
            
        return query.all()
    
    except SQLAlchemyError as e:
        logger.error(f"Fehler beim Abrufen von Flashcards: {str(e)}")
        return []

def save_flashcard(upload_id, front, back, category=None, difficulty=None):
    """
    Speichert eine neue Lernkarte in der Datenbank.
    
    Args:
        upload_id: Die ID des zugehörigen Uploads
        front: Der Text auf der Vorderseite der Karte
        back: Der Text auf der Rückseite der Karte
        category: Optional - Die Kategorie der Lernkarte
        difficulty: Optional - Die Schwierigkeit der Lernkarte (1-5)
        
    Returns:
        Das neu erstellte Flashcard-Objekt oder None bei einem Fehler
    """
    try:
        flashcard = Flashcard(
            upload_id=upload_id,
            front=front,
            back=back,
            category=category,
            difficulty=difficulty
        )
        
        db.session.add(flashcard)
        db.session.commit()
        
        return flashcard
    
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Fehler beim Speichern der Lernkarte: {str(e)}")
        return None

def update_flashcard_statistics(flashcard_id, is_correct, difficulty=None):
    """
    Aktualisiert die Statistiken einer Lernkarte nach einer Wiederholung.
    
    Args:
        flashcard_id: Die ID der Lernkarte
        is_correct: Ob die Antwort richtig war
        difficulty: Optional - Die vom Benutzer angegebene Schwierigkeit (1-5)
        
    Returns:
        Die aktualisierte Lernkarte oder None bei einem Fehler
    """
    try:
        flashcard = Flashcard.query.get(flashcard_id)
        if not flashcard:
            return None
        
        # Aktualisiere die Anzahl der Wiederholungen
        flashcard.repetitions += 1
        
        # Aktualisiere die Statistiken basierend auf der Antwort
        if is_correct:
            flashcard.correct_answers += 1
        else:
            flashcard.incorrect_answers += 1
        
        # Aktualisiere die Schwierigkeit, falls angegeben
        if difficulty is not None:
            flashcard.difficulty = difficulty
        
        # Berechne die Erfolgsrate
        total_answers = flashcard.correct_answers + flashcard.incorrect_answers
        if total_answers > 0:
            flashcard.success_rate = (flashcard.correct_answers / total_answers) * 100
        
        db.session.commit()
        return flashcard
    
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Fehler beim Aktualisieren der Lernkartenstatistik: {str(e)}")
        return None

def get_flashcards_by_category(session_id, category):
    """
    Holt Flashcards einer bestimmten Kategorie für eine Sitzung.
    
    Args:
        session_id: Die ID der Sitzung
        category: Die Kategorie, nach der gefiltert werden soll
        
    Returns:
        Eine Liste von Flashcard-Objekten
    """
    try:
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            return []
        
        return Flashcard.query.filter_by(upload_id=upload.id, category=category).all()
    
    except SQLAlchemyError as e:
        logger.error(f"Fehler beim Abrufen von Flashcards nach Kategorie: {str(e)}")
        return []

def delete_flashcard(flashcard_id):
    """
    Löscht eine Lernkarte aus der Datenbank.
    
    Args:
        flashcard_id: Die ID der zu löschenden Lernkarte
        
    Returns:
        True bei Erfolg, False bei einem Fehler
    """
    try:
        flashcard = Flashcard.query.get(flashcard_id)
        if not flashcard:
            return False
        
        db.session.delete(flashcard)
        db.session.commit()
        return True
    
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Fehler beim Löschen der Lernkarte: {str(e)}")
        return False

def get_flashcard_categories(session_id):
    """
    Ermittelt alle Kategorien der Lernkarten einer Sitzung.
    
    Args:
        session_id: Die ID der Sitzung
        
    Returns:
        Eine Liste der Kategorien
    """
    try:
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            return []
        
        # Verwende DISTINCT, um doppelte Kategorien zu vermeiden
        categories = db.session.query(Flashcard.category)\
            .filter(Flashcard.upload_id == upload.id)\
            .filter(Flashcard.category != None)\
            .distinct()\
            .all()
        
        return [category[0] for category in categories]
    
    except SQLAlchemyError as e:
        logger.error(f"Fehler beim Abrufen der Lernkartenkategorien: {str(e)}")
        return []
