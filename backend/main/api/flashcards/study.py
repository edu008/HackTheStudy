"""
Study-Modul für das Flashcards-Paket
----------------------------------

Dieses Modul enthält Funktionen zur Verwaltung von Lern-Sessions,
Implementierungen von Spaced-Repetition-Algorithmen und zur Fortschrittsverfolgung.
"""

import json
import logging
import random
from datetime import datetime, timedelta

# Verbesserte Import-Logik für StudyRecord und StudySession
try:
    from core.models import Flashcard, StudyRecord, StudySession, db
except ImportError:
    try:
        # Alternativer Import-Pfad
        from backend.main.core.models import Flashcard, StudyRecord, StudySession, db
    except ImportError:
        # Fallback, wenn die Modelle nicht gefunden werden
        from core.models import Flashcard, db
        # Definiere die fehlenden Modelle als Fallback
        class StudyRecord(db.Model):
            """Temporäres StudyRecord-Model, sollte in core.models definiert werden"""
            __tablename__ = 'study_records'
            id = db.Column(db.String(36), primary_key=True)
            study_session_id = db.Column(db.String(36))
            flashcard_id = db.Column(db.String(36))
            performance_rating = db.Column(db.Integer)
            time_spent = db.Column(db.Integer)
            timestamp = db.Column(db.DateTime)
        
        class StudySession(db.Model):
            """Temporäres StudySession-Model, sollte in core.models definiert werden"""
            __tablename__ = 'study_sessions'
            id = db.Column(db.String(36), primary_key=True)
            session_id = db.Column(db.String(255))
            settings = db.Column(db.Text)
            started_at = db.Column(db.DateTime)
            cards_count = db.Column(db.Integer)

from .models import get_flashcards
from .utils import create_study_plan

logger = logging.getLogger(__name__)


def create_study_session(session_id, settings=None, max_cards=20):
    """
    Erstellt eine neue Lern-Session für eine Sitzung.

    Args:
        session_id: Die ID der Sitzung
        settings: Einstellungen für die Lern-Session
        max_cards: Die maximale Anzahl der Karten pro Session

    Returns:
        Ein Dictionary mit der Session-ID und den ausgewählten Flashcards
    """
    # Standardeinstellungen
    default_settings = {
        'prioritize_difficult': True,
        'randomize': True,
        'include_new': True,
        'include_due': True,
        'cards_per_session': 10
    }

    # Aktualisiere die Standardeinstellungen mit den übergebenen Einstellungen
    if settings:
        default_settings.update(settings)

    # Hole alle Flashcards für die Sitzung
    flashcards = get_flashcards(session_id=session_id)

    if not flashcards:
        return None

    # Sortiere die Flashcards nach verschiedenen Kriterien
    sorted_flashcards = []

    # Teile die Flashcards in neue und bereits gelernte Karten auf
    new_cards = [card for card in flashcards if card.repetitions == 0]
    learned_cards = [card for card in flashcards if card.repetitions > 0]

    # Sortiere die gelernten Karten nach Schwierigkeit und Fälligkeit
    if default_settings['prioritize_difficult']:
        learned_cards.sort(key=lambda x: (-(x.difficulty or 3), x.due_date or datetime.now()))
    else:
        learned_cards.sort(key=lambda x: (x.due_date or datetime.now()))

    # Füge neue Karten hinzu, falls gewünscht
    if default_settings['include_new']:
        sorted_flashcards.extend(new_cards)

    # Füge fällige Karten hinzu, falls gewünscht
    if default_settings['include_due']:
        due_cards = [card for card in learned_cards if (card.due_date or datetime.now()) <= datetime.now()]
        sorted_flashcards.extend(due_cards)

    # Füge nicht fällige Karten hinzu, falls die Session nicht voll ist
    if len(sorted_flashcards) < default_settings['cards_per_session']:
        non_due_cards = [card for card in learned_cards if (card.due_date or datetime.now()) > datetime.now()]
        sorted_flashcards.extend(non_due_cards)

    # Begrenze die Anzahl der Karten
    sorted_flashcards = sorted_flashcards[:min(
        len(sorted_flashcards), default_settings['cards_per_session'], max_cards)]

    # Randomisiere die Reihenfolge, falls gewünscht
    if default_settings['randomize']:
        random.shuffle(sorted_flashcards)

    # Erstelle eine StudySession in der Datenbank
    try:
        study_session = StudySession(
            session_id=session_id,
            settings=json.dumps(default_settings),
            started_at=datetime.now(),
            cards_count=len(sorted_flashcards)
        )
        db.session.add(study_session)
        db.session.commit()

        return {
            'study_session_id': study_session.id,
            'flashcards': sorted_flashcards,
            'settings': default_settings
        }

    except Exception as e:
        db.session.rollback()
        logger.error("Fehler beim Erstellen der Lern-Session: %s", str(e))
        return None


def update_card_scheduling(flashcard_id, performance_rating, algorithm='sm2'):
    """
    Aktualisiert die Zeitplanung einer Flashcard basierend auf dem Spaced-Repetition-Algorithmus.

    Args:
        flashcard_id: Die ID der Flashcard
        performance_rating: Die Leistungsbewertung (1-5, wobei 5 am besten ist)
        algorithm: Der zu verwendende Spaced-Repetition-Algorithmus

    Returns:
        Die aktualisierte Flashcard oder None bei einem Fehler
    """
    try:
        flashcard = Flashcard.query.get(flashcard_id)
        if not flashcard:
            return None

        # Aktualisiere die Anzahl der Wiederholungen
        flashcard.repetitions += 1

        # Wähle den richtigen Algorithmus
        if algorithm == 'sm2':
            # SuperMemo-2-Algorithmus
            return _update_using_sm2(flashcard, performance_rating)
        if algorithm == 'leitner':
            # Leitner-Boxen-Algorithmus (unnötiges "el" aus "elif" entfernt)
            return _update_using_leitner(flashcard, performance_rating)
        
        # Einfacher Algorithmus als Fallback
        return _update_using_simple(flashcard, performance_rating)

    except Exception as e:
        db.session.rollback()
        logger.error("Fehler beim Aktualisieren der Kartenzeitplanung: %s", str(e))
        return None


def _update_using_sm2(flashcard, performance_rating):
    """
    Implementiert den SuperMemo-2-Algorithmus für Spaced Repetition.

    Args:
        flashcard: Die Flashcard-Instanz
        performance_rating: Die Leistungsbewertung (1-5, wobei 5 am besten ist)

    Returns:
        Die aktualisierte Flashcard
    """
    # Konvertiere die Bewertung in einen Wert zwischen 0 und 1
    quality = max(0, min(5, performance_rating)) / 5.0

    # Hole den aktuellen Schwierigkeitsfaktor oder initialisiere ihn
    easiness_factor = getattr(flashcard, 'easiness_factor', 2.5)

    # Berechne den neuen Schwierigkeitsfaktor
    easiness_factor = max(1.3, easiness_factor + (0.1 - (5 - quality * 5) * (0.08 + (5 - quality * 5) * 0.02)))

    # Setze den Intervall je nach Wiederholungsnummer
    if flashcard.repetitions == 1:
        interval = 1
    elif flashcard.repetitions == 2:
        interval = 6
    else:
        interval = round(getattr(flashcard, 'interval', 1) * easiness_factor)

    # Begrenze den Intervall
    interval = min(interval, 365)

    # Aktualisiere die Flashcard
    flashcard.easiness_factor = easiness_factor
    flashcard.interval = interval
    flashcard.due_date = datetime.now() + timedelta(days=interval)
    flashcard.last_reviewed = datetime.now()

    # Speichere Änderungen
    db.session.commit()

    return flashcard


def _update_using_leitner(flashcard, performance_rating):
    """
    Implementiert den Leitner-Boxen-Algorithmus für Spaced Repetition.

    Args:
        flashcard: Die Flashcard-Instanz
        performance_rating: Die Leistungsbewertung (1-5, wobei 5 am besten ist)

    Returns:
        Die aktualisierte Flashcard
    """
    # Mappingtabelle für die Boxen (Box -> Tage bis zur nächsten Wiederholung)
    box_intervals = {
        0: 1,   # Box 0: täglich
        1: 2,   # Box 1: alle 2 Tage
        2: 5,   # Box 2: alle 5 Tage
        3: 9,   # Box 3: alle 9 Tage
        4: 14,  # Box 4: alle 14 Tage
        5: 30,  # Box 5: monatlich
        6: 90   # Box 6: vierteljährlich
    }

    # Hole die aktuelle Box oder initialisiere sie
    current_box = getattr(flashcard, 'box', 0)

    # Bewege die Karte in die nächste oder vorherige Box je nach Leistung
    if performance_rating >= 4:  # Gut (4) oder Perfekt (5)
        current_box = min(6, current_box + 1)
    elif performance_rating <= 2:  # Schlecht (1) oder Schwierig (2)
        current_box = max(0, current_box - 1)
    # Bei mittlerer Leistung (3) bleibt die Box unverändert

    # Berechne das nächste Fälligkeitsdatum
    interval = box_intervals[current_box]

    # Aktualisiere die Flashcard
    flashcard.box = current_box
    flashcard.interval = interval
    flashcard.due_date = datetime.now() + timedelta(days=interval)
    flashcard.last_reviewed = datetime.now()

    # Speichere Änderungen
    db.session.commit()

    return flashcard


def _update_using_simple(flashcard, performance_rating):
    """
    Implementiert einen einfachen Spaced-Repetition-Algorithmus als Fallback.

    Args:
        flashcard: Die Flashcard-Instanz
        performance_rating: Die Leistungsbewertung (1-5, wobei 5 am besten ist)

    Returns:
        Die aktualisierte Flashcard
    """
    # Einfache Intervalle basierend auf der Bewertung
    if performance_rating <= 2:
        interval = 1  # Wiederholung am nächsten Tag
    elif performance_rating == 3:
        interval = 3  # Wiederholung in 3 Tagen
    elif performance_rating == 4:
        interval = 7  # Wiederholung in einer Woche
    else:  # performance_rating == 5
        interval = 14  # Wiederholung in zwei Wochen

    # Aktualisiere die Flashcard
    flashcard.interval = interval
    flashcard.due_date = datetime.now() + timedelta(days=interval)
    flashcard.last_reviewed = datetime.now()

    # Speichere Änderungen
    db.session.commit()

    return flashcard


def get_study_statistics(session_id):
    """
    Ermittelt Statistiken zum Lernfortschritt für eine Sitzung.

    Args:
        session_id: Die ID der Sitzung

    Returns:
        Ein Dictionary mit Statistiken
    """
    try:
        # Hole alle Flashcards für die Sitzung
        flashcards = get_flashcards(session_id=session_id)

        if not flashcards:
            return {
                'total_cards': 0,
                'learned_cards': 0,
                'mastered_cards': 0,
                'due_cards': 0,
                'average_success_rate': 0,
                'study_sessions': 0,
                'total_repetitions': 0
            }

        # Ermittle verschiedene Statistiken
        total_cards = len(flashcards)
        learned_cards = len([card for card in flashcards if card.repetitions > 0])
        mastered_cards = len([card for card in flashcards if card.repetitions > 0 and (card.success_rate or 0) >= 80])
        due_cards = len([card for card in flashcards if (card.due_date or datetime.now()) <= datetime.now()])

        # Berechne die durchschnittliche Erfolgsrate
        success_rates = [card.success_rate for card in flashcards if card.success_rate is not None]
        average_success_rate = sum(success_rates) / len(success_rates) if success_rates else 0

        # Ermittle die Anzahl der Lern-Sessions
        study_sessions = StudySession.query.filter_by(session_id=session_id).count()

        # Berechne die Gesamtzahl der Wiederholungen
        total_repetitions = sum([card.repetitions for card in flashcards])

        return {
            'total_cards': total_cards,
            'learned_cards': learned_cards,
            'mastered_cards': mastered_cards,
            'due_cards': due_cards,
            'average_success_rate': average_success_rate,
            'study_sessions': study_sessions,
            'total_repetitions': total_repetitions
        }

    except Exception as e:
        logger.error("Fehler beim Ermitteln der Lernstatistiken: %s", str(e))
        return None


def record_study_result(study_session_id, flashcard_id, performance_rating, time_spent=None):
    """
    Zeichnet das Ergebnis einer Kartenwiedergabe in einer Lern-Session auf.

    Args:
        study_session_id: Die ID der Lern-Session
        flashcard_id: Die ID der Flashcard
        performance_rating: Die Leistungsbewertung (1-5, wobei 5 am besten ist)
        time_spent: Optional - Die für die Karte aufgewendete Zeit in Sekunden

    Returns:
        True bei Erfolg, False bei einem Fehler
    """
    try:
        # Erstelle einen neuen StudyRecord
        study_record = StudyRecord(
            study_session_id=study_session_id,
            flashcard_id=flashcard_id,
            performance_rating=performance_rating,
            time_spent=time_spent,
            timestamp=datetime.now()
        )

        db.session.add(study_record)
        db.session.commit()

        # Aktualisiere auch die Kartenzeitplanung
        update_card_scheduling(flashcard_id, performance_rating)

        return True

    except Exception as e:
        db.session.rollback()
        logger.error("Fehler beim Aufzeichnen des Lernergebnisses: %s", str(e))
        return False


def get_repetition_interval(card):
    """
    Berechnet das Wiederholungsintervall für eine Karte basierend auf Schwierigkeit und bisherigen Wiederholungen.
    """
    # Basis-Intervalle in Stunden
    intervals = {
        1: 6,     # 6 Stunden
        2: 12,    # 12 Stunden
        3: 24,    # 1 Tag
        4: 72,    # 3 Tage
        5: 168,   # 1 Woche
        6: 336,   # 2 Wochen
        7: 720,   # 1 Monat
        8: 2160,  # 3 Monate
    }
    
    # Bestimme die Anzahl der erfolgreichen Wiederholungen
    successful_reps = card.successful_repetitions or 0
    
    if successful_reps >= 8:
        return intervals[8]
    
    if successful_reps in intervals:
        return intervals[successful_reps]
    
    # Fallback
    return 24  # 24 Stunden
    

def analyze_flashcard_statistics(flashcards):
    """
    Analysiert die Statistiken einer Reihe von Flashcards.

    Args:
        flashcards: Eine Liste von Flashcard-Objekten

    Returns:
        Ein Dictionary mit verschiedenen Statistiken
    """
    # Verwende Generatoren für bessere Performance
    total_repetitions = sum(card.repetitions for card in flashcards)
    total_successful = sum(card.successful_repetitions or 0 for card in flashcards)
    
    total_cards = len(flashcards)
    avg_difficulty = sum(card.difficulty or 3 for card in flashcards) / max(1, total_cards)
    
    # Weitere Berechnungen
    # ...
    
    return {
        "total_cards": total_cards,
        "total_repetitions": total_repetitions,
        "total_successful": total_successful,
        "average_difficulty": avg_difficulty,
        # Weitere Statistiken
    }
