"""
Controller-Modul für das Flashcards-Paket
----------------------------------------

Dieses Modul enthält die Geschäftslogik für die Flashcard-Verwaltung:
- Verarbeitung von Anfragen zur Generierung
- Datenbankoperationen für Flashcards
- Fehlerbehandlung und Rückgabe von Antworten
"""

import json
import logging
import random

from api.token_tracking import (calculate_token_cost, check_credits_available,
                                deduct_credits)
from core.models import Flashcard, Topic, Upload, User, UserActivity, db
from flask import current_app, g, jsonify
from openai import OpenAI

from .generation import \
    generate_additional_flashcards as gen_additional_flashcards
from .generation import generate_flashcards as gen_flashcards
from .models import (delete_flashcard, get_flashcard_categories,
                     get_flashcards, get_flashcards_by_category,
                     save_flashcard, update_flashcard_statistics)
from .utils import (create_study_plan, detect_language_wrapper,
                    format_flashcards, parse_study_settings)
from .validation import sanitize_flashcard, validate_generated_flashcards

logger = logging.getLogger(__name__)


def process_generate_flashcards(session_id, count=10, topic_filter=None):
    """
    Verarbeitet Anfragen zur erstmaligen Generierung von Flashcards.

    Args:
        session_id: Die ID der Sitzung, für die Flashcards generiert werden sollen
        count: Die Anzahl der zu generierenden Flashcards
        topic_filter: Optional - beschränkt die Flashcards auf bestimmte Themen

    Returns:
        Eine JSON-Antwort mit den generierten Flashcards oder einer Fehlermeldung
    """
    # Lade die Sitzungsdaten
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({'error': 'Sitzung nicht gefunden', 'success': False}), 404

    # Prüfe, ob bereits Flashcards generiert wurden
    existing_flashcards = Flashcard.query.filter_by(upload_id=upload.id).all()
    if existing_flashcards:
        flashcards_data = format_flashcards(existing_flashcards)
        return jsonify({
            'success': True,
            'message': 'Es wurden bereits Lernkarten für diese Sitzung generiert.',
            'flashcards': flashcards_data,
            'data': {
                'flashcards': flashcards_data
            }
        })

    # Lade die Analyse für die Generierung
    main_topic = "Unbekanntes Thema"
    subtopics = []

    # Prüfe auf ein vorhandenes Hauptthema
    main_topic_obj = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
    if main_topic_obj:
        main_topic = main_topic_obj.name

    # Lade Subtopics, optional gefiltert
    if topic_filter:
        subtopic_objs = Topic.query.filter(
            Topic.upload_id == upload.id,
            not Topic.is_main_topic,
            Topic.name.in_(topic_filter)
        ).all()
    else:
        subtopic_objs = Topic.query.filter_by(
            upload_id=upload.id,
            is_main_topic=False,
            parent_id=None
        ).all()

    subtopics = [subtopic.name for subtopic in subtopic_objs]

    # Erstelle eine Analyse-Zusammenfassung
    analysis = {
        'main_topic': main_topic,
        'subtopics': [{'name': subtopic} for subtopic in subtopics]
    }

    try:
        # Berechne geschätzte Kosten für diesen Aufruf
        # Wir schätzen Tokens basierend auf der Textlänge und dem gewünschten Count
        content_length = len(upload.content)
        estimated_input_tokens = min(content_length // 4, 2000) + 500  # Grobe Schätzung basierend auf Textlänge
        estimated_output_tokens = count * 150  # Grobe Schätzung

        # Berechne die Kosten
        estimated_cost = calculate_token_cost(
            model="gpt-3.5-turbo",
            input_tokens=estimated_input_tokens,
            output_tokens=estimated_output_tokens
        )

        # Prüfe, ob Benutzer genug Credits hat
        if not check_credits_available(estimated_cost):
            return jsonify({
                'error': {
                    'message': f'Nicht genügend Credits. Benötigt: {estimated_cost} Credits für diese Anfrage.',
                    'credits_required': estimated_cost,
                    'credits_available': g.user.credits if hasattr(g, 'user') and g.user else 0
                },
                'error_type': 'insufficient_credits',
                'success': False
            }), 402

        # Initialize OpenAI client
        openai_api_key = current_app.config.get('OPENAI_API_KEY')
        client = OpenAI(api_key=openai_api_key)

        # Sprache des Textes erkennen
        language = 'de' if detect_language_wrapper(upload.content) == 'de' else 'en'

        # Generiere Lernkarten
        new_flashcards = gen_flashcards(
            upload.content,
            client,
            analysis,
            count,
            language=language,
            session_id=session_id,  # Übergebe session_id für Token-Tracking
            function_name="generate_flashcards"  # Definiere die Funktion für das Tracking
        )

        # Validiere und bereinige die generierten Flashcards
        valid_flashcards = validate_generated_flashcards(new_flashcards)[0]
        sanitized_flashcards = [sanitize_flashcard(fc) for fc in valid_flashcards]

        # Speichere neue Flashcards in der Datenbank
        saved_flashcards = []
        for flashcard_data in sanitized_flashcards:
            flashcard = save_flashcard(
                upload_id=upload.id,
                front=flashcard_data['front'],
                back=flashcard_data['back'],
                category=flashcard_data.get('category', None)
            )
            if flashcard:
                saved_flashcards.append(flashcard)

        # Aktualisiere die Nutzungszeit für diese Sitzung
        upload.last_used_at = db.func.current_timestamp()
        db.session.commit()

        # Erstelle eine UserActivity-Eintrag für diese Aktion
        if hasattr(g, 'user') and g.user:
            user_activity = UserActivity(
                user_id=g.user.id,
                activity_type='flashcard',
                title=f'Generierte {len(saved_flashcards)} Lernkarten',
                main_topic=main_topic,
                subtopics=subtopics,
                session_id=session_id,
                details={
                    'count': len(saved_flashcards)
                }
            )
            db.session.add(user_activity)
            db.session.commit()

        # Formatiere die Flashcards für die Antwort
        flashcards_data = format_flashcards(saved_flashcards)

        # Rückgabe der erfolgreich generierten Flashcards
        return jsonify({
            'success': True,
            'message': f'{len(saved_flashcards)} Lernkarten wurden erfolgreich generiert.',
            'flashcards': flashcards_data,
            'data': {
                'flashcards': flashcards_data
            },
            'credits_available': g.user.credits if hasattr(g, 'user') and g.user else 0
        })

    except Exception as e:
        db.session.rollback()
        logger.error("Fehler beim Generieren von Lernkarten: %s", str(e))
        return jsonify({
            'error': str(e),
            'success': False
        }), 500


def process_generate_more_flashcards(session_id, count, timestamp=""):
    """
    Verarbeitet Anfragen zur Generierung zusätzlicher Flashcards.

    Args:
        session_id: Die ID der Sitzung, für die Flashcards generiert werden sollen
        count: Die Anzahl der zu generierenden Flashcards
        timestamp: Ein optionaler Zeitstempel zur Vermeidung von Caching

    Returns:
        Eine JSON-Antwort mit den generierten Flashcards oder einer Fehlermeldung
    """
    logger.info("Generating flashcards with timestamp: %s", timestamp)

    # Lade die Sitzungsdaten
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({'error': 'Sitzung nicht gefunden', 'success': False}), 404

    # Lade die vorhandenen Flashcards
    existing_flashcards = Flashcard.query.filter_by(upload_id=upload.id).all()
    existing_flashcards_data = format_flashcards(existing_flashcards)

    # Lade die Analyse
    main_topic = "Unbekanntes Thema"
    subtopics = []

    # Prüfe auf ein vorhandenes Hauptthema
    main_topic_obj = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
    if main_topic_obj:
        main_topic = main_topic_obj.name

    # Lade Subtopics
    subtopic_objs = Topic.query.filter_by(upload_id=upload.id, is_main_topic=False, parent_id=None).all()
    subtopics = [subtopic.name for subtopic in subtopic_objs]

    # Erstelle eine Analyse-Zusammenfassung
    analysis = {
        'main_topic': main_topic,
        'subtopics': [{'name': subtopic} for subtopic in subtopics]
    }

    try:
        # Berechne geschätzte Kosten für diesen Aufruf
        estimated_input_tokens = 1000 + len(existing_flashcards) * 50
        estimated_output_tokens = count * 150  # Grobe Schätzung

        # Berechne die Kosten
        estimated_cost = calculate_token_cost(
            model="gpt-3.5-turbo",
            input_tokens=estimated_input_tokens,
            output_tokens=estimated_output_tokens
        )

        # Prüfe, ob Benutzer genug Credits hat
        if not check_credits_available(estimated_cost):
            return jsonify({
                'error': {
                    'message': f'Nicht genügend Credits. Benötigt: {estimated_cost} Credits für diese Anfrage.',
                    'credits_required': estimated_cost,
                    'credits_available': g.user.credits if hasattr(g, 'user') and g.user else 0
                },
                'error_type': 'insufficient_credits',
                'success': False
            }), 402

        # Initialize OpenAI client
        openai_api_key = current_app.config.get('OPENAI_API_KEY')
        client = OpenAI(api_key=openai_api_key)

        # Generiere neue Flashcards
        new_flashcards = gen_additional_flashcards(
            upload.content,
            client,
            analysis,
            existing_flashcards_data,
            count,
            language='de' if detect_language_wrapper(upload.content) == 'de' else 'en',
            session_id=session_id,  # Übergebe session_id für Token-Tracking
            function_name="generate_more_flashcards"  # Definiere die Funktion für das Tracking
        )

        # Validiere und bereinige die generierten Flashcards
        valid_flashcards = validate_generated_flashcards(new_flashcards)[0]
        sanitized_flashcards = [sanitize_flashcard(fc) for fc in valid_flashcards]

        # Speichere neue Flashcards in der Datenbank
        saved_flashcards = []
        for flashcard_data in sanitized_flashcards:
            flashcard = save_flashcard(
                upload_id=upload.id,
                front=flashcard_data['front'],
                back=flashcard_data['back'],
                category=flashcard_data.get('category', None)
            )
            if flashcard:
                saved_flashcards.append(flashcard)

        # Aktualisiere die Nutzungszeit für diese Sitzung
        upload.last_used_at = db.func.current_timestamp()
        db.session.commit()

        # Lade alle Flashcards für die Rückgabe
        all_flashcards = Flashcard.query.filter_by(upload_id=upload.id).all()
        flashcards_data = format_flashcards(all_flashcards)

        # Erstelle eine UserActivity-Eintrag für diese Aktion
        if hasattr(g, 'user') and g.user:
            user_activity = UserActivity(
                user_id=g.user.id,
                activity_type='flashcard',
                title=f'Generierte {len(saved_flashcards)} zusätzliche Lernkarten',
                main_topic=main_topic,
                subtopics=subtopics,
                session_id=session_id,
                details={
                    'count': len(saved_flashcards),
                    'total_count': len(flashcards_data)
                }
            )
            db.session.add(user_activity)
            db.session.commit()

        # Rückgabe der erfolgreich generierten Flashcards
        return jsonify({
            'success': True,
            'message': f'{len(saved_flashcards)} neue Lernkarten wurden erfolgreich generiert.',
            'flashcards': flashcards_data,  # Direkt auf der ersten Ebene für ältere Client-Versionen
            'data': {
                'flashcards': flashcards_data
            },
            'credits_available': g.user.credits if hasattr(g, 'user') and g.user else 0
        })

    except Exception as e:
        db.session.rollback()
        logger.error("Fehler beim Generieren von Lernkarten: %s", str(e))
        return jsonify({
            'error': str(e),
            'success': False
        }), 500


def process_get_flashcards(session_id, include_stats=False, category=None):
    """
    Verarbeitet Anfragen zum Abrufen von Flashcards.

    Args:
        session_id: Die ID der Sitzung
        include_stats: Ob Statistikdaten einbezogen werden sollen
        category: Optional - filtert nach einer bestimmten Kategorie

    Returns:
        Eine JSON-Antwort mit den Flashcards oder einer Fehlermeldung
    """
    try:
        if category:
            # Hole Flashcards einer bestimmten Kategorie
            flashcards = get_flashcards_by_category(session_id, category)
        else:
            # Hole alle Flashcards der Sitzung
            flashcards = get_flashcards(session_id=session_id)

        if not flashcards:
            return jsonify({
                'success': True,
                'message': 'Keine Lernkarten gefunden.',
                'flashcards': [],
                'data': {
                    'flashcards': []
                }
            })

        # Formatiere die Flashcards für die Antwort
        flashcards_data = format_flashcards(flashcards, include_stats)

        # Hole verfügbare Kategorien, falls vorhanden
        categories = get_flashcard_categories(session_id)

        return jsonify({
            'success': True,
            'flashcards': flashcards_data,
            'data': {
                'flashcards': flashcards_data,
                'categories': categories
            }
        })

    except Exception as e:
        logger.error("Fehler beim Abrufen von Lernkarten: %s", str(e))
        return jsonify({
            'error': str(e),
            'success': False
        }), 500


def process_update_flashcard(flashcard_id, data):
    """
    Verarbeitet Anfragen zum Aktualisieren einer Flashcard.

    Args:
        flashcard_id: Die ID der zu aktualisierenden Flashcard
        data: Die aktualisierten Daten

    Returns:
        Eine JSON-Antwort mit der aktualisierten Flashcard oder einer Fehlermeldung
    """
    try:
        # Flashcard aus der Datenbank abrufen
        flashcard = get_flashcards(flashcard_id=flashcard_id)
        if not flashcard:
            return jsonify({
                'error': 'Lernkarte nicht gefunden',
                'success': False
            }), 404

        # Bereinige die Eingabedaten
        sanitized_data = sanitize_flashcard(data)

        # Aktualisiere die Flashcard-Attribute
        if 'front' in sanitized_data:
            flashcard.front = sanitized_data['front']

        if 'back' in sanitized_data:
            flashcard.back = sanitized_data['back']

        if 'category' in sanitized_data:
            flashcard.category = sanitized_data['category']

        if 'difficulty' in sanitized_data:
            flashcard.difficulty = sanitized_data['difficulty']

        # Speichere die Änderungen
        db.session.commit()

        # Formatiere die aktualisierte Flashcard für die Antwort
        flashcard_data = format_flashcards(flashcard, include_stats=True)

        return jsonify({
            'success': True,
            'message': 'Lernkarte erfolgreich aktualisiert.',
            'flashcard': flashcard_data[0] if flashcard_data else None,
            'data': {
                'flashcard': flashcard_data[0] if flashcard_data else None
            }
        })

    except Exception as e:
        db.session.rollback()
        logger.error("Fehler beim Aktualisieren der Lernkarte: %s", str(e))
        return jsonify({
            'error': str(e),
            'success': False
        }), 500


def process_delete_flashcard(flashcard_id):
    """
    Verarbeitet Anfragen zum Löschen einer Flashcard.

    Args:
        flashcard_id: Die ID der zu löschenden Flashcard

    Returns:
        Eine JSON-Antwort mit dem Ergebnis der Löschoperation
    """
    try:
        # Flashcard löschen
        result = delete_flashcard(flashcard_id)

        if result:
            return jsonify({
                'success': True,
                'message': 'Lernkarte erfolgreich gelöscht.',
                'data': {
                    'flashcard_id': flashcard_id
                }
            })
        
        return jsonify({
            'error': 'Lernkarte konnte nicht gelöscht werden oder wurde nicht gefunden.',
            'success': False
        }), 404

    except Exception as e:
        logger.error("Fehler beim Löschen der Lernkarte: %s", str(e))
        return jsonify({
            'error': str(e),
            'success': False
        }), 500


def process_get_study_session(session_id, settings=None):
    """
    Verarbeitet Anfragen zum Starten einer Lern-Session.

    Args:
        session_id: Die ID der Sitzung
        settings: Einstellungen für die Lern-Session

    Returns:
        Eine JSON-Antwort mit den Flashcards für die Lern-Session
    """
    try:
        # Parse study settings
        study_settings = parse_study_settings(settings)

        # Hole alle Flashcards der Sitzung
        all_flashcards = get_flashcards(session_id=session_id)

        if not all_flashcards:
            return jsonify({
                'success': True,
                'message': 'Keine Lernkarten gefunden.',
                'flashcards': [],
                'data': {
                    'flashcards': []
                }
            })

        # Sortiere Flashcards nach den Einstellungen
        if study_settings.get('review_difficult', True):
            # Priorisiere schwierige Karten
            sorted_flashcards = sorted(
                all_flashcards,
                key=lambda x: (-(x.difficulty or 3), -(100 - (x.success_rate or 0)))
            )
        else:
            # Standardsortierung
            sorted_flashcards = all_flashcards

        # Begrenze die Anzahl der Karten für die Session
        cards_per_session = study_settings.get('cards_per_session', 10)
        study_flashcards = sorted_flashcards[:cards_per_session]

        # Randomisiere die Reihenfolge, falls gewünscht
        if study_settings.get('randomize_order', True):
            random.shuffle(study_flashcards)

        # Formatiere die Flashcards für die Antwort
        include_stats = study_settings.get('show_statistics', False)
        flashcards_data = format_flashcards(study_flashcards, include_stats)

        # Rückgabe der Lern-Session
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
        logger.error("Fehler beim Erstellen der Lern-Session: %s", str(e))
        return jsonify({
            'error': str(e),
            'success': False
        }), 500


def process_save_flashcard_feedback(flashcard_id, difficulty, is_correct=None, feedback=None, time_spent=None):
    """
    Verarbeitet Anfragen zum Speichern von Feedback zu einer Flashcard.

    Args:
        flashcard_id: Die ID der Flashcard
        difficulty: Der Schwierigkeitsgrad (1-5)
        is_correct: Optional - ob die Antwort richtig war
        feedback: Optional - textuelles Feedback
        time_spent: Optional - Zeitaufwand in Sekunden

    Returns:
        Eine JSON-Antwort mit dem Ergebnis der Feedback-Speicherung
    """
    try:
        # Aktualisiere die Flashcard-Statistiken
        updated_flashcard = update_flashcard_statistics(
            flashcard_id,
            is_correct=is_correct,
            difficulty=difficulty
        )

        if not updated_flashcard:
            return jsonify({
                'error': 'Lernkarte nicht gefunden',
                'success': False
            }), 404

        # Speichere zusätzliche Feedback-Informationen, falls relevant
        # (In dieser Implementierung noch nicht genutzt)

        # Formatiere die aktualisierte Flashcard für die Antwort
        flashcard_data = format_flashcards(updated_flashcard, include_stats=True)

        return jsonify({
            'success': True,
            'message': 'Feedback erfolgreich gespeichert.',
            'flashcard': flashcard_data[0] if flashcard_data else None,
            'data': {
                'flashcard': flashcard_data[0] if flashcard_data else None
            }
        })

    except Exception as e:
        db.session.rollback()
        logger.error("Fehler beim Speichern des Feedbacks: %s", str(e))
        return jsonify({
            'error': str(e),
            'success': False
        }), 500
