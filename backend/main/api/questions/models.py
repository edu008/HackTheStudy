"""
Datenbankoperationen für Fragen
---------------------------

Dieses Modul enthält Funktionen für Datenbankoperationen mit Fragen
und die Verwaltung von Fragen-Objekten.
"""

import logging

from core.models import Question, UserActivity, db
from flask import g

logger = logging.getLogger(__name__)


def get_questions(upload_id):
    """
    Holt alle Fragen für einen Upload.

    Args:
        upload_id: Die ID des Uploads, für den Fragen geholt werden sollen

    Returns:
        list: Die gefundenen Fragen
    """
    questions = Question.query.filter_by(upload_id=upload_id).all()
    logger.info("Retrieved %s questions for upload ID: %s", len(questions), upload_id)
    return questions


def save_question(upload_id, text, options, correct_answer, explanation=""):
    """
    Erstellt eine neue Frage in der Datenbank.

    Args:
        upload_id: Die ID des Uploads, für den die Frage erstellt werden soll
        text: Der Text der Frage
        options: Die Antwortoptionen der Frage
        correct_answer: Der Index der korrekten Antwort
        explanation: Die Erklärung für die korrekte Antwort (optional)

    Returns:
        Question: Das erstellte Fragen-Objekt
    """
    question = Question(
        upload_id=upload_id,
        text=text,
        options=options,
        correct_answer=correct_answer,
        explanation=explanation
    )
    db.session.add(question)
    db.session.flush()  # Flush, um die ID des neuen Fragen-Objekts zu erhalten
    logger.info("Created new question with ID: %s for upload ID: %s", question.id, upload_id)
    return question


def save_questions(upload_id, questions_data):
    """
    Erstellt mehrere Fragen in der Datenbank.

    Args:
        upload_id: Die ID des Uploads, für den die Fragen erstellt werden sollen
        questions_data: Die Daten der zu erstellenden Fragen

    Returns:
        list: Die erstellten Fragen-Objekte
    """
    questions = []
    for question_data in questions_data:
        question = save_question(
            upload_id,
            question_data['text'],
            question_data['options'],
            question_data['correct'],
            question_data.get('explanation', '')
        )
        questions.append(question)

    logger.info("Saved %s questions for upload ID: %s", len(questions), upload_id)
    return questions


def log_questions_activity(user_id, upload_id, activity_type, title, main_topic, subtopics, session_id, details=None):
    """
    Protokolliert eine Benutzeraktivität im Zusammenhang mit Fragen.

    Args:
        user_id: Die ID des Benutzers
        upload_id: Die ID des Uploads
        activity_type: Der Typ der Aktivität
        title: Der Titel der Aktivität
        main_topic: Das Hauptthema
        subtopics: Die Unterthemen
        session_id: Die ID der Sitzung
        details: Zusätzliche Details (optional)

    Returns:
        UserActivity: Das erstellte UserActivity-Objekt
    """
    if not details:
        details = {}

    activity = UserActivity(
        user_id=user_id,
        activity_type=activity_type,
        title=title,
        main_topic=main_topic,
        subtopics=subtopics,
        session_id=session_id,
        details=details
    )
    db.session.add(activity)
    logger.info("Logged user activity of type %s for user ID: %s", activity_type, user_id)
    return activity


def update_upload_timestamp(upload):
    """
    Aktualisiert den Zeitstempel des letzten Zugriffs auf einen Upload.

    Args:
        upload: Das Upload-Objekt, dessen Zeitstempel aktualisiert werden soll
    """
    upload.last_used_at = db.func.current_timestamp()
    logger.info("Updated last_used_at timestamp for upload ID: %s", upload.id)


def limit_user_activities(user_id, max_activities=5):
    """
    Begrenzt die Anzahl der Benutzeraktivitäten auf eine maximale Anzahl.

    Args:
        user_id: Die ID des Benutzers
        max_activities: Die maximale Anzahl an Aktivitäten (Standard: 5)
    """
    existing_activities = UserActivity.query.filter_by(user_id=user_id).order_by(UserActivity.timestamp.asc()).all()
    if len(existing_activities) >= max_activities:
        # Lösche älteste Aktivitäten, bis die maximale Anzahl erreicht ist
        for i in range(0, len(existing_activities) - max_activities + 1):
            db.session.delete(existing_activities[i])
            logger.info("Deleted old activity with ID: %s for user ID: %s", existing_activities[i].id, user_id)
    logger.info("Limited user activities to %s for user ID: %s", max_activities, user_id)
