"""
Controller-Modul für das Flashcards-Paket (Refaktoriert)
----------------------------------------

Enthält nur noch die Geschäftslogik für das Abrufen,
Aktualisieren, Löschen und Lernen von Flashcards.
Die Generierungslogik wurde entfernt (findet im Worker statt).
"""

import json
import logging
import random
from datetime import datetime

# Entferne Token Tracking, da keine Generierung mehr hier
# from api.token_tracking import (
#    calculate_token_cost, check_credits_available,
#    deduct_credits)
from core.models import Flashcard, Topic, Upload, User, UserActivity, db
from flask import current_app, g, jsonify
# Entferne OpenAI Client Import
# from openai import OpenAI

# Entferne Imports für Generierungsfunktionen
# from .generation import \
#    generate_additional_flashcards as gen_additional_flashcards
# from .generation import generate_flashcards as gen_flashcards

# Behalte notwendige Model-Funktionen
from .models import (delete_flashcard, get_flashcard_categories,
                     get_flashcards, get_flashcards_by_category,
                     save_flashcard, update_flashcard_statistics)
# Behalte notwendige Utils-Funktionen
from .utils import (create_study_plan, detect_language_wrapper,
                    format_flashcards, parse_study_settings)
# Entferne Validierungsfunktionen für Generierung
# from .validation import sanitize_flashcard, validate_generated_flashcards
from .validation import sanitize_flashcard # Behalte für Update?

logger = logging.getLogger(__name__)

# --- Veraltete Generierungs-Controller entfernt --- #

# def process_generate_flashcards(session_id, count=10, topic_filter=None):
#    ...

# def process_generate_more_flashcards(session_id, count, timestamp=""):
#    ...

# --- Controller für Abruf und Verwaltung (bleiben bestehen) --- #

def process_get_flashcards(session_id, include_stats=False, category=None):
    """
    Verarbeitet Anfragen zum Abrufen von Flashcards.
    (Logik bleibt unverändert)
    """
    # ... (Implementierung bleibt)
    try:
        # Finde Upload zur Session ID
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            logger.warning(f"Kein Upload gefunden für Session {session_id} bei Flashcard-Abruf.")
            return jsonify({'success': True, 'flashcards': [], 'data': {'flashcards': [], 'categories': []}})

        if category:
            flashcards = get_flashcards_by_category(upload.id, category) # Verwende upload_id
        else:
            flashcards = get_flashcards(upload_id=upload.id)

        if not flashcards:
            return jsonify({
                'success': True,
                'message': 'Keine Lernkarten gefunden.',
                'flashcards': [],
                'data': {'flashcards': [], 'categories': []}
            })

        flashcards_data = format_flashcards(flashcards, include_stats)
        categories = get_flashcard_categories(upload.id) # Verwende upload_id

        return jsonify({
            'success': True,
            'flashcards': flashcards_data,
            'data': {
                'flashcards': flashcards_data,
                'categories': categories
            }
        })
    except Exception as e:
        logger.error(f"Fehler beim Abrufen von Lernkarten für Session {session_id}: {e}", exc_info=True)
        return jsonify({
            'error': "Fehler beim Laden der Lernkarten.",
            'success': False
        }), 500

def process_update_flashcard(flashcard_id, data):
    """
    Verarbeitet Anfragen zum Aktualisieren einer Flashcard.
    (Logik bleibt unverändert)
    """
    # ... (Implementierung bleibt)
    try:
        flashcard = db.session.get(Flashcard, flashcard_id) # Verwende session.get
        if not flashcard:
            return jsonify({'error': 'Lernkarte nicht gefunden', 'success': False}), 404

        # Optional: Berechtigungsprüfung (gehört User der Upload an?)

        sanitized_data = sanitize_flashcard(data) # Bereinigung beibehalten

        updated = False
        if 'front' in sanitized_data and flashcard.front != sanitized_data['front']:
            flashcard.front = sanitized_data['front']
            updated = True
        if 'back' in sanitized_data and flashcard.back != sanitized_data['back']:
            flashcard.back = sanitized_data['back']
            updated = True
        # Weitere Felder nach Bedarf (z.B. tags, category?)

        if updated:
             flashcard.updated_at = datetime.utcnow() # Optional: Update Zeitstempel
        db.session.commit()
             logger.info(f"Lernkarte {flashcard_id} aktualisiert.")
        else:
             logger.info(f"Keine Änderungen für Lernkarte {flashcard_id} festgestellt.")

        flashcard_data = format_flashcards([flashcard], include_stats=True) # Formatiere die einzelne Karte

        return jsonify({
            'success': True,
            'message': 'Lernkarte erfolgreich aktualisiert.',
            'flashcard': flashcard_data[0] if flashcard_data else None,
            'data': {'flashcard': flashcard_data[0] if flashcard_data else None}
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Fehler beim Aktualisieren der Lernkarte {flashcard_id}: {e}", exc_info=True)
        return jsonify({
            'error': "Fehler beim Aktualisieren der Lernkarte.",
            'success': False
        }), 500

def process_delete_flashcard(flashcard_id):
    """
    Verarbeitet Anfragen zum Löschen einer Flashcard.
    (Logik bleibt unverändert)
    """
    # ... (Implementierung bleibt)
    try:
        flashcard = db.session.get(Flashcard, flashcard_id)
        if not flashcard:
             return jsonify({'error': 'Lernkarte nicht gefunden', 'success': False}), 404

        # Optional: Berechtigungsprüfung

        db.session.delete(flashcard)
        db.session.commit()
        logger.info(f"Lernkarte {flashcard_id} gelöscht.")

            return jsonify({
                'success': True,
                'message': 'Lernkarte erfolgreich gelöscht.',
            'data': {'flashcard_id': flashcard_id}
            })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Fehler beim Löschen der Lernkarte {flashcard_id}: {e}", exc_info=True)
        return jsonify({
            'error': "Fehler beim Löschen der Lernkarte.",
            'success': False
        }), 500

def process_get_study_session(session_id, settings=None):
    """
    Verarbeitet Anfragen zum Starten einer Lern-Session.
    (Logik bleibt unverändert, nutzt jetzt get_flashcards mit upload_id)
    """
    # ... (Implementierung bleibt)
    try:
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
             return jsonify({'success': True, 'message': 'Keine Lernkarten gefunden (Session ungültig).', 'flashcards': [], 'data': {'flashcards': []}})

        study_settings = parse_study_settings(settings)
        all_flashcards = get_flashcards(upload_id=upload.id)

        if not all_flashcards:
            return jsonify({
                'success': True,
                'message': 'Keine Lernkarten gefunden.',
                'flashcards': [],
                'data': {'flashcards': []}
            })

        # Sortierung und Auswahl (wie vorher)
        if study_settings.get('review_difficult', True):
            sorted_flashcards = sorted(
                all_flashcards,
                key=lambda x: (-(x.difficulty or 3), -(100 - (x.success_rate or 0)))
            )
        else:
            sorted_flashcards = all_flashcards

        cards_per_session = study_settings.get('cards_per_session', 10)
        study_flashcards = sorted_flashcards[:cards_per_session]

        if study_settings.get('randomize_order', True):
            random.shuffle(study_flashcards)

        include_stats = study_settings.get('show_statistics', False)
        flashcards_data = format_flashcards(study_flashcards, include_stats)

        return jsonify({
            'success': True,
            'flashcards': flashcards_data,
            'data': {
                'flashcards': flashcards_data,
                'settings': study_settings,
                'total_cards': len(all_flashcards),
                'session_cards': len(study_flashcards)
            }
        })

    except Exception as e:
        logger.error(f"Fehler beim Erstellen der Lern-Session für Session {session_id}: {e}", exc_info=True)
        return jsonify({
            'error': "Fehler beim Erstellen der Lern-Session.",
            'success': False
        }), 500

def process_save_flashcard_feedback(flashcard_id, difficulty, is_correct=None, feedback=None, time_spent=None):
    """
    Verarbeitet Anfragen zum Speichern von Feedback zu einer Flashcard.
    (Logik bleibt unverändert)
    """
    # ... (Implementierung bleibt)
    try:
        updated_flashcard = update_flashcard_statistics(
            flashcard_id,
            is_correct=is_correct,
            difficulty=difficulty
        )

        if not updated_flashcard:
            return jsonify({'error': 'Lernkarte nicht gefunden', 'success': False}), 404

        # Optional: Detailliertes Feedback speichern?

        flashcard_data = format_flashcards([updated_flashcard], include_stats=True)

        return jsonify({
            'success': True,
            'message': 'Feedback erfolgreich gespeichert.',
            'flashcard': flashcard_data[0] if flashcard_data else None,
            'data': {'flashcard': flashcard_data[0] if flashcard_data else None}
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Fehler beim Speichern des Feedbacks für Flashcard {flashcard_id}: {e}", exc_info=True)
        return jsonify({
            'error': "Fehler beim Speichern des Feedbacks.",
            'success': False
        }), 500
