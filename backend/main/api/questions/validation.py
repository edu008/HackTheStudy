"""
Validierungs-Modul für das Questions-Paket
------------------------------------------

Dieses Modul enthält Funktionen zur Validierung von Fragen:
- Überprüfung der Fragen-Struktur
- Validierung der Antwortmöglichkeiten
- Überprüfung der Korrektheit
"""

import logging
import re

from marshmallow import (Schema, ValidationError, fields, validates,
                         validates_schema)

from .schemas import QuestionRequestSchema

logger = logging.getLogger(__name__)


class QuestionDataSchema(Schema):
    """Schema für die Validierung von Fragendaten."""
    text = fields.Str(required=True)
    options = fields.List(fields.Str(), required=True)
    correct = fields.Int(required=True)
    explanation = fields.Str(required=False, allow_none=True)

    @validates('text')
    def validate_text(self, value):
        """Validiert den Fragetext."""
        if not value or len(value.strip()) < 5:
            raise ValidationError("Der Fragetext muss mindestens 5 Zeichen lang sein.")

        if len(value) > 500:
            raise ValidationError("Der Fragetext darf maximal 500 Zeichen lang sein.")

    @validates('options')
    def validate_options(self, values):
        """Validiert die Antwortmöglichkeiten."""
        if not values or len(values) < 2:
            raise ValidationError("Es müssen mindestens 2 Antwortmöglichkeiten angegeben werden.")

        if len(values) > 10:
            raise ValidationError("Es dürfen maximal 10 Antwortmöglichkeiten angegeben werden.")

        for option in values:
            if not option or len(option.strip()) < 1:
                raise ValidationError("Antwortmöglichkeiten dürfen nicht leer sein.")

            if len(option) > 300:
                raise ValidationError("Eine Antwortmöglichkeit darf maximal 300 Zeichen lang sein.")

    @validates('correct')
    def validate_correct(self, value):
        """Validiert den Index der korrekten Antwort."""
        if value < 0:
            raise ValidationError("Der Index der korrekten Antwort darf nicht negativ sein.")

    @validates_schema
    def validate_correct_index(self, data, **kwargs):
        """Validiert, dass der Index der korrekten Antwort gültig ist."""
        if 'correct' in data and 'options' in data:
            if data['correct'] >= len(data['options']):
                raise ValidationError(
                    "Der Index der korrekten Antwort muss kleiner als die Anzahl der Antwortmöglichkeiten sein.",
                    field_name='correct'
                )


def validate_question_data(question_data):
    """
    Validiert die Daten einer Frage.

    Args:
        question_data: Die zu validierenden Fragendaten

    Returns:
        (bool, str): Ein Tupel aus einem Erfolgs-Flag und einer Fehlermeldung (falls vorhanden)
    """
    try:
        QuestionDataSchema().load(question_data)
        return True, ""
    except ValidationError as err:
        error_message = "; ".join([f"{field}: {'; '.join(messages)}" for field, messages in err.messages.items()])
        return False, error_message


def validate_generated_questions(questions):
    """
    Validiert eine Liste von generierten Fragen.

    Args:
        questions: Die zu validierende Fragenliste

    Returns:
        (list, list): Ein Tupel aus gültigen Fragen und Fehlermeldungen für ungültige Fragen
    """
    valid_questions = []
    error_messages = []

    for i, question in enumerate(questions):
        is_valid, error = validate_question_data(question)
        if is_valid:
            valid_questions.append(question)
        else:
            error_messages.append(f"Frage {i+1}: {error}")
            logger.warning("Ungültige Frage: %s", error)

    return valid_questions, error_messages


def sanitize_question_text(text):
    """
    Bereinigt den Fragetext.

    Args:
        text: Der zu bereinigende Fragetext

    Returns:
        str: Der bereinigte Fragetext
    """
    # Entfernt überschüssige Whitespaces
    text = re.sub(r'\s+', ' ', text.strip())

    # Stellt sicher, dass der Text mit einem Zeichen endet
    if text and not text.endswith(('?', '.', '!', ':')):
        text += '?'

    return text


def sanitize_question_options(options):
    """
    Bereinigt die Antwortmöglichkeiten.

    Args:
        options: Die zu bereinigenden Antwortmöglichkeiten

    Returns:
        list: Die bereinigten Antwortmöglichkeiten
    """
    sanitized = []
    for option in options:
        # Entfernt überschüssige Whitespaces
        option = re.sub(r'\s+', ' ', option.strip())

        # Entfernt potentielle Aufzählungszeichen am Anfang (1., A., -, usw.)
        option = re.sub(r'^[A-Za-z0-9][\)\.]\s*', '', option)
        option = re.sub(r'^[-•*]\s*', '', option)

        sanitized.append(option)

    return sanitized


def sanitize_question(question):
    """
    Bereinigt eine komplette Frage.

    Args:
        question: Die zu bereinigende Frage

    Returns:
        dict: Die bereinigte Frage
    """
    sanitized = question.copy()

    if 'text' in sanitized:
        sanitized['text'] = sanitize_question_text(sanitized['text'])

    if 'options' in sanitized:
        sanitized['options'] = sanitize_question_options(sanitized['options'])

    if 'explanation' in sanitized and sanitized['explanation']:
        sanitized['explanation'] = re.sub(r'\s+', ' ', sanitized['explanation'].strip())

    return sanitized
