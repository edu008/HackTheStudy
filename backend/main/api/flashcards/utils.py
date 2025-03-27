"""
Utils-Modul für das Flashcards-Paket
----------------------------------

Dieses Modul enthält Hilfsfunktionen für Flashcards:
- Formatierfunktionen
- Spracherkennung
- Diverse Hilfsfunktionen für die Flashcard-Verwaltung
"""

import json
import logging
import re
from datetime import datetime, timedelta

import langdetect

# Ersetze den problematischen Import durch eine lokale Implementierung
def detect_language(text):
    """
    Erkennt die Sprache eines Textes.
    
    Args:
        text: Der zu analysierende Text
        
    Returns:
        Der Sprachcode ('de', 'en', etc.)
    """
    try:
        return langdetect.detect(text)
    except Exception:
        return 'en'  # Englisch als Fallback

logger = logging.getLogger(__name__)


def detect_language_wrapper(text):
    """
    Wrapper für die Spracherkennung, der Fehler abfängt.

    Args:
        text: Der zu analysierende Text

    Returns:
        'de' für Deutsch, 'en' für Englisch, 'en' als Standardwert bei Fehlern
    """
    try:
        return detect_language(text)
    except Exception as e:
        logger.warning("Fehler bei der Spracherkennung: %s. Verwende Standardwert 'en'.", str(e))
        return 'en'


def format_flashcards(flashcards, include_stats=False):
    """
    Formatiert Flashcard-Objekte für die API-Antwort.

    Args:
        flashcards: Eine Liste von Flashcard-Objekten oder ein einzelnes Objekt
        include_stats: Optional - Ob Statistikdaten einbezogen werden sollen

    Returns:
        Eine Liste formatierter Flashcard-Dictionaries
    """
    if not flashcards:
        return []

    # Wenn ein einzelnes Objekt übergeben wurde, konvertiere es in eine Liste
    if not isinstance(flashcards, list):
        flashcards = [flashcards]

    formatted = []
    for card in flashcards:
        card_dict = {
            'id': card.id,
            'front': card.front,
            'back': card.back,
            'category': card.category
        }

        if include_stats:
            card_dict.update({
                'repetitions': card.repetitions,
                'correct_answers': card.correct_answers,
                'incorrect_answers': card.incorrect_answers,
                'success_rate': card.success_rate,
                'difficulty': card.difficulty
            })

        formatted.append(card_dict)

    return formatted


def categorize_content(content, topics, subtopics):
    """
    Erstellt Kategorien basierend auf den extrahierten Themen.

    Args:
        content: Der Inhalt des Uploads
        topics: Eine Liste der Hauptthemen
        subtopics: Eine Liste der Unterthemen

    Returns:
        Eine Liste möglicher Kategorien für Lernkarten
    """
    categories = []

    # Hauptthema als Kategorie verwenden, falls vorhanden
    if topics and isinstance(topics, list) and len(topics) > 0:
        categories.append(topics[0])

    # Füge Unterthemen als Kategorien hinzu
    if subtopics and isinstance(subtopics, list):
        for subtopic in subtopics:
            if isinstance(subtopic, dict) and 'name' in subtopic:
                categories.append(subtopic['name'])
            elif isinstance(subtopic, str):
                categories.append(subtopic)

    # Entferne Duplikate und None-Werte
    return list(set(filter(None, categories)))


def extract_terms_from_content(content, max_terms=50):
    """
    Extrahiert wichtige Begriffe aus dem Inhalt.

    Args:
        content: Der zu analysierende Inhalt
        max_terms: Die maximale Anzahl der zu extrahierenden Begriffe

    Returns:
        Eine Liste der extrahierten Begriffe
    """
    try:
        # Einfache Extraktion basierend auf Häufigkeit und Länge
        words = re.findall(r'\b[A-Za-z\u00C0-\u00FF]{4,}\b', content)
        word_counts = {}

        for word in words:
            word = word.lower()
            if word in word_counts:
                word_counts[word] += 1
            else:
                word_counts[word] = 1

        # Sortiere nach Häufigkeit und dann nach Länge (längere Begriffe bevorzugen)
        sorted_words = sorted(
            word_counts.items(),
            key=lambda x: (x[1], len(x[0])),
            reverse=True
        )

        # Die häufigsten Begriffe zurückgeben, aber maximal max_terms
        return [word for word, count in sorted_words[:max_terms]]

    except Exception as e:
        logger.error("Fehler beim Extrahieren von Begriffen: %s", str(e))
        return []


def create_study_plan(flashcards, days=7, cards_per_day=10):
    """
    Erstellt einen Lernplan für die Wiederholung von Lernkarten.

    Args:
        flashcards: Eine Liste von Flashcard-Objekten
        days: Die Anzahl der Tage für den Lernplan
        cards_per_day: Die Anzahl der Karten pro Tag

    Returns:
        Ein Dictionary mit Tagen als Schlüssel und Lernkarten-IDs als Werte
    """
    if not flashcards:
        return {}

    # Sortiere Karten nach Schwierigkeit und Erfolgsrate
    sorted_cards = sorted(
        flashcards,
        key=lambda x: (x.difficulty or 3, -1 * (x.success_rate or 0))
    )

    # Erstelle den Lernplan
    study_plan = {}
    today = datetime.now()

    for day in range(days):
        date = today + timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        # Berechne den Startindex für diesen Tag
        start_idx = (day * cards_per_day) % len(sorted_cards)

        # Wähle die Karten für diesen Tag aus
        day_cards = []
        for i in range(cards_per_day):
            card_idx = (start_idx + i) % len(sorted_cards)
            day_cards.append(sorted_cards[card_idx].id)

        study_plan[date_str] = day_cards

    return study_plan


def parse_study_settings(settings_str):
    """
    Parst die Einstellungen für eine Lern-Sitzung.

    Args:
        settings_str: Eine JSON-Zeichenkette mit den Einstellungen

    Returns:
        Ein Dictionary mit den geparsten Einstellungen oder Standardwerte
    """
    default_settings = {
        'cards_per_session': 10,
        'review_difficult': True,
        'randomize_order': True,
        'show_statistics': False,
        'time_limit': None  # Keine Zeitbegrenzung
    }

    if not settings_str:
        return default_settings

    try:
        settings = json.loads(settings_str)
        # Aktualisiere die Standardwerte mit den geparsten Einstellungen
        default_settings.update(settings)
        return default_settings

    except json.JSONDecodeError as e:
        logger.error("Fehler beim Parsen der Studieneinstellungen: %s", str(e))
        return default_settings
