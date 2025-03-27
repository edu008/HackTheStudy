"""
Hilfsfunktionen für das Fragen-Modul
---------------------------------

Dieses Modul enthält Hilfsfunktionen für die Verarbeitung von Fragen-Daten
und die Unterstützung der Fragengenerierung.
"""

import logging

import tiktoken
from flask import g

from ..utils import detect_language

logger = logging.getLogger(__name__)


def detect_language_wrapper(content):
    """
    Wrapper-Funktion für die Spracherkennungsfunktion.

    Args:
        content: Der Inhalt, dessen Sprache erkannt werden soll

    Returns:
        str: Der erkannte Sprachcode (z.B. 'de' oder 'en')
    """
    return detect_language(content)


def format_questions(questions):
    """
    Formatiert Fragen für die API-Antwort.

    Args:
        questions: Die zu formatierenden Fragen

    Returns:
        list: Die formatierten Fragen
    """
    return [
        {
            'id': q.id,
            'text': q.text,
            'options': q.options,
            'correct': q.correct_answer,
            'explanation': q.explanation
        }
        for q in questions
    ]


def count_tokens(text):
    """
    Zählt die Anzahl der Tokens in einem Text.

    Args:
        text: Der Text, dessen Tokens gezählt werden sollen

    Returns:
        int: Die Anzahl der Tokens
    """
    try:
        encoding = tiktoken.encoding_for_model("gpt-4")
        return len(encoding.encode(text))
    except Exception as e:
        # Fallback bei Fehlern mit der Tokenizer-Bibliothek
        logger.warning("Error counting tokens with tiktoken: %s. Using fallback method.", str(e))
        return len(text) // 4  # Grobe Schätzung: 1 Token = 4 Zeichen


def calculate_generation_cost(content_length, count=10):
    """
    Berechnet die geschätzten Kosten für die Generierung von Fragen.

    Args:
        content_length: Die Länge des Inhalts
        count: Die Anzahl der zu generierenden Fragen

    Returns:
        int: Die geschätzten Kosten
    """
    # Schätze die Kosten basierend auf der Länge des Inhalts
    estimated_prompt_tokens = min(content_length // 3, 100000)  # Ungefähre Schätzung: 1 Token pro 3 Zeichen

    # Token-Kosten berechnen
    input_token_cost = estimated_prompt_tokens // 1000  # 1 Credit pro 1000 Input-Tokens
    
    # Output-Token werden in die Berechnung einbezogen
    output_token_cost = 0
    if estimated_prompt_tokens < 100:
        output_token_cost = 1  # Minimale Ausgabe für winzige Dokumente
    elif estimated_prompt_tokens < 500:
        output_token_cost = 2  # Reduzierte Ausgabe für kleine Dokumente
    else:
        output_token_cost = count  # Geschätzte Ausgabe für Fragen: skaliert mit Anzahl

    # Grundkosten für die Anfrage
    base_cost = 30

    # Credits pro Frage
    question_cost = count * 3

    total_cost = base_cost + input_token_cost + output_token_cost + question_cost

    # Maximalkosten begrenzen
    return min(total_cost, 150)


def get_user_credits():
    """
    Holt die aktuellen Credits des Benutzers.

    Returns:
        int: Die Anzahl der Credits oder 0, wenn kein Benutzer gefunden wurde
    """
    if hasattr(g, 'user') and g.user:
        return g.user.credits
    return 0


def extract_topics_from_upload(upload):
    """
    Extrahiert Topics aus einem Upload für die Generierung von Fragen.

    Args:
        upload: Das Upload-Objekt

    Returns:
        dict: Ein Dictionary mit Haupttopic und Subtopics
    """
    from core.models import Topic

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

    return analysis
