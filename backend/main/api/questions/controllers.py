"""
Controller-Modul für das Questions-Paket
----------------------------------------

Dieses Modul enthält die Geschäftslogik für die Fragenverwaltung:
- Verarbeitung von Anfragen zur Generierung
- Aufrufen der entsprechenden Services
- Fehlerbehandlung und Rückgabe von Antworten
"""

import logging
from datetime import datetime

import tiktoken
from api.token_tracking import (calculate_token_cost, check_credits_available,
                                deduct_credits)
from core.models import Question, Topic, Upload, User, UserActivity, db
from flask import current_app, g, jsonify
from openai import OpenAI

from .generation import generate_additional_questions, generate_questions
from .models import get_questions, save_question
from .utils import detect_language_wrapper

logger = logging.getLogger(__name__)


def process_generate_more_questions(session_id, count, timestamp=""):
    """
    Verarbeitet Anfragen zur Generierung zusätzlicher Fragen.

    Args:
        session_id: Die ID der Sitzung, für die Fragen generiert werden sollen
        count: Die Anzahl der zu generierenden Fragen
        timestamp: Ein optionaler Zeitstempel zur Vermeidung von Caching

    Returns:
        Eine JSON-Antwort mit den generierten Fragen oder einer Fehlermeldung
    """
    logger.info("Generating questions with timestamp: %s", timestamp)

    # Lade die Sitzungsdaten
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({'error': 'Sitzung nicht gefunden', 'success': False}), 404

    # Lade die vorhandenen Fragen
    existing_questions = Question.query.filter_by(upload_id=upload.id).all()
    existing_questions_data = [
        {
            'text': q.text,
            'options': q.options,
            'correct': q.correct_answer,
            'explanation': q.explanation
        }
        for q in existing_questions
    ]

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
        estimated_input_tokens = 1000 + len(existing_questions) * 100
        estimated_output_tokens = count * 200  # Grobe Schätzung

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
        client = OpenAI(
            api_key=openai_api_key,
            default_headers={
                "OpenAI-Beta": "assistants=v2"
            }
        )

        # Generiere neue Fragen
        new_questions = generate_additional_questions(
            upload.content,
            client,
            analysis,
            existing_questions_data,
            count,
            language='de' if detect_language_wrapper(upload.content) == 'de' else 'en',
            session_id=session_id,  # Übergebe session_id für Token-Tracking
            function_name="generate_more_questions"  # Definiere die Funktion für das Tracking
        )

        # Speichere neue Fragen in der Datenbank
        for question_data in new_questions:
            question = Question(
                upload_id=upload.id,
                text=question_data['text'],
                options=question_data['options'],
                correct_answer=question_data['correct'],
                explanation=question_data.get('explanation', '')
            )
            db.session.add(question)

        db.session.commit()

        # Aktualisiere die Nutzungszeit für diese Sitzung
        upload.last_used_at = db.func.current_timestamp()
        db.session.commit()

        # Lade die aktualisierten Fragen
        all_questions = Question.query.filter_by(upload_id=upload.id).all()
        questions_data = [
            {
                'id': q.id,
                'text': q.text,
                'options': q.options,
                'correct': q.correct_answer,
                'explanation': q.explanation
            }
            for q in all_questions
        ]

        # Erstelle eine UserActivity-Eintrag für diese Aktion
        if hasattr(g, 'user') and g.user and upload:
            try:
                # Extrahiere Hauptthema (vereinfacht, nimmt das erste falls vorhanden)
                topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
                main_topic_title = topic.name if topic else None
                
                user_activity = UserActivity(
                    user_id=g.user.id,
                    session_id=session_id, 
                    upload_id=upload.id,
                    main_topic=main_topic_title, # Nur Hauptthema speichern
                    timestamp=datetime.utcnow() # Timestamp wird jetzt automatisch gesetzt
                )
                db.session.add(user_activity)
                db.session.commit()
            except Exception as e_act:
                logger.error(f"Fehler beim Erstellen des UserActivity Eintrags für Fragen: {e_act}")
                db.session.rollback()

        # Rückgabe der erfolgreich generierten Fragen
        return jsonify({
            'success': True,
            'message': f'{len(new_questions)} neue Testfragen wurden erfolgreich generiert.',
            'questions': questions_data,  # Direkt auf der ersten Ebene für ältere Client-Versionen
            'data': {
                'questions': questions_data
            },
            'credits_available': g.user.credits if hasattr(g, 'user') and g.user else 0
        })

    except Exception as e:
        db.session.rollback()
        logger.error("Fehler beim Generieren von Testfragen: %s", str(e))
        return jsonify({
            'error': str(e),
            'success': False
        }), 500


def process_generate_questions(session_id, count=5, topic_filter=None):
    """
    Verarbeitet Anfragen zur erstmaligen Generierung von Fragen.

    Args:
        session_id: Die ID der Sitzung, für die Fragen generiert werden sollen
        count: Die Anzahl der zu generierenden Fragen
        topic_filter: Optional - beschränkt die Fragen auf bestimmte Themen

    Returns:
        Eine JSON-Antwort mit den generierten Fragen oder einer Fehlermeldung
    """
    # Lade die Sitzungsdaten
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({'error': 'Sitzung nicht gefunden', 'success': False}), 404

    # Prüfe, ob bereits Fragen generiert wurden
    existing_questions = Question.query.filter_by(upload_id=upload.id).all()
    if existing_questions:
        questions_data = [
            {
                'id': q.id,
                'text': q.text,
                'options': q.options,
                'correct': q.correct_answer,
                'explanation': q.explanation
            }
            for q in existing_questions
        ]
        return jsonify({
            'success': True,
            'message': 'Es wurden bereits Testfragen für diese Sitzung generiert.',
            'questions': questions_data,
            'data': {
                'questions': questions_data
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
            Topic.is_main_topic is False
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
        estimated_output_tokens = count * 200  # Grobe Schätzung

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
        client = OpenAI(
            api_key=openai_api_key,
            default_headers={
                "OpenAI-Beta": "assistants=v2"
            }
        )

        # Sprache des Textes erkennen
        language = 'de' if detect_language_wrapper(upload.content) == 'de' else 'en'

        # Generiere Fragen
        questions = generate_questions(
            content=upload.content,
            client=client,
            analysis=analysis,
            count=count,
            language=language
        )

        # Speichere neue Fragen in der Datenbank
        for question_data in questions:
            question = Question(
                upload_id=upload.id,
                text=question_data['text'],
                options=question_data['options'],
                correct_answer=question_data['correct'],
                explanation=question_data.get('explanation', '')
            )
            db.session.add(question)

        db.session.commit()

        # Aktualisiere die Nutzungszeit für diese Sitzung
        upload.last_used_at = db.func.current_timestamp()
        db.session.commit()

        # Lade die aktualisierten Fragen
        all_questions = Question.query.filter_by(upload_id=upload.id).all()
        questions_data = [
            {
                'id': q.id,
                'text': q.text,
                'options': q.options,
                'correct': q.correct_answer,
                'explanation': q.explanation
            }
            for q in all_questions
        ]

        # Erstelle eine UserActivity-Eintrag für diese Aktion
        if hasattr(g, 'user') and g.user and upload:
            try:
                # Extrahiere Hauptthema (vereinfacht, nimmt das erste falls vorhanden)
                topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
                main_topic_title = topic.name if topic else None
                
                user_activity = UserActivity(
                    user_id=g.user.id,
                    session_id=session_id, 
                    upload_id=upload.id,
                    main_topic=main_topic_title, # Nur Hauptthema speichern
                    timestamp=datetime.utcnow() # Timestamp wird jetzt automatisch gesetzt
                )
                db.session.add(user_activity)
                db.session.commit()
            except Exception as e_act:
                logger.error(f"Fehler beim Erstellen des UserActivity Eintrags für Fragen: {e_act}")
                db.session.rollback()

        # Rückgabe der erfolgreich generierten Fragen
        return jsonify({
            'success': True,
            'message': f'{len(questions)} Testfragen wurden erfolgreich generiert.',
            'questions': questions_data,
            'data': {
                'questions': questions_data
            },
            'credits_available': g.user.credits if hasattr(g, 'user') and g.user else 0
        })

    except Exception as e:
        db.session.rollback()
        logger.error("Fehler beim Generieren von Testfragen: %s", str(e))
        return jsonify({
            'error': str(e),
            'success': False
        }), 500
