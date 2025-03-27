"""
KI-Generierungsaufgaben für den Worker.
"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# OpenAI API-Konfiguration
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
DEFAULT_MODEL = os.environ.get('OPENAI_DEFAULT_MODEL', 'gpt-3.5-turbo')


def register_tasks(celery_app):
    """
    Registriert alle KI-Generierungsaufgaben mit der Celery-App.

    Args:
        celery_app: Die Celery-App-Instanz.

    Returns:
        dict: Dictionary mit den registrierten Tasks.
    """
    tasks = {}

    @celery_app.task(name='ai.generate_flashcards', bind=True, max_retries=3)
    def generate_flashcards(self, content, num_cards=10, language='de', options=None):
        """
        Generiert Lernkarten aus dem gegebenen Inhalt mit OpenAI.

        Args:
            content (str): Textinhalt für die Karteikarten.
            num_cards (int): Anzahl der zu generierenden Karten.
            language (str): Sprachcode (de, en, ...).
            options (dict): Weitere Optionen.

        Returns:
            dict: Generierte Karteikarten.
        """
        logger.info("Generiere %s Lernkarten in %s", num_cards, language)

        options = options or {}
        result = {
            'status': 'processing',
            'started_at': datetime.now().isoformat(),
            'flashcards': [],
            'error': None
        }

        try:
            # Inhalt auf sinnvolle Länge begrenzen
            if len(content) > 15000:
                content = content[:15000] + "...[Gekürzt]"

            # Asyncio-Event-Loop verwenden, um OpenAI-API aufzurufen
            flashcards = asyncio.run(generate_flashcards_with_openai(
                content=content,
                num_cards=num_cards,
                language=language,
                **options
            ))

            # Ergebnis formatieren
            result['status'] = 'completed'
            result['completed_at'] = datetime.now().isoformat()
            result['flashcards'] = flashcards

            return result

        except Exception as e:
            error_message = str(e)
            logger.error("Fehler bei der Generierung der Lernkarten: %s", error_message)

            result['status'] = 'error'
            result['error'] = error_message
            result['completed_at'] = datetime.now().isoformat()

            # Wiederhole den Task bei API-Fehlern
            if "openai.error" in error_message.lower() or "rate limit" in error_message.lower():
                try:
                    # Exponentielles Backoff für Wiederholungen
                    retry_count = self.request.retries
                    backoff = 60 * (2 ** retry_count)  # 60s, 120s, 240s, ...
                    logger.info("Wiederhole Lernkarten-Generierung in %ss (Versuch %s/3)", backoff, retry_count+1)
                    self.retry(countdown=backoff, exc=e)
                except self.MaxRetriesExceededError:
                    logger.error("Maximale Anzahl an Wiederholungen für Lernkarten-Generierung erreicht")

            return result

    tasks['ai.generate_flashcards'] = generate_flashcards

    @celery_app.task(name='ai.generate_questions', bind=True, max_retries=3)
    def generate_questions(self, content, num_questions=5,
                           question_type='multiple_choice', language='de', options=None):
        """
        Generiert Fragen aus dem gegebenen Inhalt mit OpenAI.

        Args:
            content (str): Textinhalt für die Fragen.
            num_questions (int): Anzahl der zu generierenden Fragen.
            question_type (str): Fragetyp (multiple_choice, open, ...).
            language (str): Sprachcode (de, en, ...).
            options (dict): Weitere Optionen.

        Returns:
            dict: Generierte Fragen.
        """
        logger.info("Generiere %s Fragen vom Typ %s in %s", num_questions, question_type, language)

        options = options or {}
        result = {
            'status': 'processing',
            'started_at': datetime.now().isoformat(),
            'questions': [],
            'error': None
        }

        try:
            # Inhalt auf sinnvolle Länge begrenzen
            if len(content) > 15000:
                content = content[:15000] + "...[Gekürzt]"

            # Asyncio-Event-Loop verwenden, um OpenAI-API aufzurufen
            questions = asyncio.run(generate_questions_with_openai(
                content=content,
                num_questions=num_questions,
                question_type=question_type,
                language=language,
                **options
            ))

            # Ergebnis formatieren
            result['status'] = 'completed'
            result['completed_at'] = datetime.now().isoformat()
            result['questions'] = questions

            return result

        except Exception as e:
            error_message = str(e)
            logger.error("Fehler bei der Generierung der Fragen: %s", error_message)

            result['status'] = 'error'
            result['error'] = error_message
            result['completed_at'] = datetime.now().isoformat()

            # Wiederhole den Task bei API-Fehlern
            if "openai.error" in error_message.lower() or "rate limit" in error_message.lower():
                try:
                    # Exponentielles Backoff für Wiederholungen
                    retry_count = self.request.retries
                    backoff = 60 * (2 ** retry_count)  # 60s, 120s, 240s, ...
                    logger.info("Wiederhole Fragen-Generierung in %ss (Versuch %s/3)", backoff, retry_count+1)
                    self.retry(countdown=backoff, exc=e)
                except self.MaxRetriesExceededError:
                    logger.error("Maximale Anzahl an Wiederholungen für Fragen-Generierung erreicht")

            return result

    tasks['ai.generate_questions'] = generate_questions

    @celery_app.task(name='ai.extract_topics', bind=True, max_retries=2)
    def extract_topics(self, content, max_topics=8, language='de', options=None):
        """
        Extrahiert Hauptthemen aus dem gegebenen Inhalt mit OpenAI.

        Args:
            content (str): Textinhalt für die Themenextraktion.
            max_topics (int): Maximale Anzahl der zu extrahierenden Themen.
            language (str): Sprachcode (de, en, ...).
            options (dict): Weitere Optionen.

        Returns:
            dict: Extrahierte Themen.
        """
        logger.info("Extrahiere bis zu %s Themen in %s", max_topics, language)

        options = options or {}
        result = {
            'status': 'processing',
            'started_at': datetime.now().isoformat(),
            'topics': [],
            'error': None
        }

        try:
            # Inhalt auf sinnvolle Länge begrenzen
            if len(content) > 20000:
                content = content[:20000] + "...[Gekürzt]"

            # Asyncio-Event-Loop verwenden, um OpenAI-API aufzurufen
            topics = asyncio.run(extract_topics_with_openai(
                content=content,
                max_topics=max_topics,
                language=language,
                **options
            ))

            # Ergebnis formatieren
            result['status'] = 'completed'
            result['completed_at'] = datetime.now().isoformat()
            result['topics'] = topics

            return result

        except Exception as e:
            error_message = str(e)
            logger.error("Fehler bei der Themenextraktion: %s", error_message)

            result['status'] = 'error'
            result['error'] = error_message
            result['completed_at'] = datetime.now().isoformat()

            # Wiederhole den Task bei API-Fehlern
            if "openai.error" in error_message.lower() or "rate limit" in error_message.lower():
                try:
                    self.retry(countdown=30, exc=e)
                except self.MaxRetriesExceededError:
                    logger.error("Maximale Anzahl an Wiederholungen für Themenextraktion erreicht")

            return result

    tasks['ai.extract_topics'] = extract_topics

    return tasks

# --- OpenAI-Hilfsfunktionen ---


async def call_openai_api(model, messages, temperature=0.7, max_tokens=None, **kwargs):
    """
    Ruft die OpenAI-API mit Caching auf.

    Args:
        model (str): Das zu verwendende OpenAI-Modell.
        messages (list): Liste der Nachrichtenelemente.
        temperature (float): Temperatur für die Antwortgenerierung.
        max_tokens (int, optional): Maximale Antwortlänge in Tokens.
        **kwargs: Weitere Parameter für die API.

    Returns:
        dict: OpenAI-API-Antwort.
    """
    try:
        # Importiere OpenAI mit Cache-Decorator
        import openai
        from openaicache import cache_openai_response

        # API-Schlüssel setzen
        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        # Cache-Decorator anwenden
        @cache_openai_response
        async def cached_openai_call(model, messages, temperature=0.7, max_tokens=None, **kwargs):
            """Cacheable OpenAI API call."""
            # Parameter für die Anfrage vorbereiten
            params = {
                "model": model,
                "messages": messages,
                "temperature": temperature
            }

            # Optionale Parameter hinzufügen
            if max_tokens:
                params["max_tokens"] = max_tokens

            for key, value in kwargs.items():
                params[key] = value

            # API-Aufruf
            response = await client.chat.completions.create(**params)
            return response.dict()

        # API mit Cache aufrufen
        return await cached_openai_call(model, messages, temperature, max_tokens, **kwargs)

    except Exception as e:
        logger.error("Fehler beim OpenAI-API-Aufruf: %s", e)
        raise


async def generate_flashcards_with_openai(content, num_cards=10, language='de', **options):
    """
    Generiert Lernkarten mit OpenAI.

    Args:
        content (str): Textinhalt für die Karteikarten.
        num_cards (int): Anzahl der zu generierenden Karten.
        language (str): Sprachcode (de, en, ...).
        **options: Weitere Optionen.

    Returns:
        list: Generierte Lernkarten.
    """
    # Model auswählen
    model = options.get('model', DEFAULT_MODEL)

    # System-Prompt für Lernkarten-Generierung
    system_prompt = {
        "de": f"Du bist ein Experte für das Erstellen präziser Lernkarten. Erstelle {num_cards} Lernkarten basierend auf dem gegebenen Text. Jede Karte sollte eine Vorderseite (Frage/Begriff) und Rückseite (Antwort/Definition) haben. Formatiere die Antwort als JSON-Array mit Objekten, die die Felder 'front' und 'back' enthalten.",
        "en": f"You are an expert in creating precise flashcards. Create {num_cards} flashcards based on the given text. Each card should have a front side (question/term) and back side (answer/definition). Format the response as a JSON array with objects containing 'front' and 'back' fields."
    }.get(language, f"Create {num_cards} flashcards based on the text. Format as JSON array with 'front' and 'back' fields.")

    # Nachrichtenarray erstellen
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Hier ist der Textinhalt, für den du Lernkarten erstellen sollst:\n\n{content}"}
    ]

    # OpenAI-API aufrufen
    response = await call_openai_api(
        model=model,
        messages=messages,
        temperature=0.7,
        max_tokens=2000,
        response_format={"type": "json_object"}
    )

    # Antwort parsen
    try:
        response_content = response.get('choices', [{}])[0].get('message', {}).get('content', '{}')
        cards_data = json.loads(response_content)

        # Extrahiere Karten aus der Antwort
        cards = cards_data.get('cards', [])
        if not cards and isinstance(cards_data, list):
            cards = cards_data

        # Stelle sicher, dass das Format korrekt ist
        for i, card in enumerate(cards):
            if not isinstance(card, dict) or 'front' not in card or 'back' not in card:
                logger.warning("Ungültiges Kartenformat für Karte %s: %s", i+1, card)
                # Versuche zu reparieren
                if isinstance(card, str) and ":" in card:
                    parts = card.split(":", 1)
                    cards[i] = {'front': parts[0].strip(), 'back': parts[1].strip()}

        return cards

    except json.JSONDecodeError as e:
        logger.error("Fehler beim Parsen der OpenAI-Antwort für Lernkarten: %s", e)
        # Fallback: Versuche, Text manuell zu parsen
        content = response.get('choices', [{}])[0].get('message', {}).get('content', '')

        # Einfache Textparsing-Logik, wenn JSON fehlerhaft
        cards = []
        lines = content.split('\n')
        current_card = {}

        for line in lines:
            if line.startswith("Front:") or line.startswith("Vorderseite:"):
                if current_card and 'front' in current_card:
                    cards.append(current_card)
                    current_card = {}
                current_card['front'] = line.split(":", 1)[1].strip()
            elif line.startswith("Back:") or line.startswith("Rückseite:"):
                if 'front' in current_card:
                    current_card['back'] = line.split(":", 1)[1].strip()

        if current_card and 'front' in current_card and 'back' in current_card:
            cards.append(current_card)

        return cards


async def generate_questions_with_openai(content, num_questions=5, question_type='multiple_choice', language='de', **options):
    """
    Generiert Fragen mit OpenAI.

    Args:
        content (str): Textinhalt für die Fragen.
        num_questions (int): Anzahl der zu generierenden Fragen.
        question_type (str): Fragetyp (multiple_choice, open, ...).
        language (str): Sprachcode (de, en, ...).
        **options: Weitere Optionen.

    Returns:
        list: Generierte Fragen.
    """
    # Model auswählen
    model = options.get('model', DEFAULT_MODEL)

    # System-Prompt basierend auf Fragetyp und Sprache
    system_prompts = {
        'multiple_choice': {
            'de': f"Erstelle {num_questions} Multiple-Choice-Fragen basierend auf dem gegebenen Text. Jede Frage sollte 4 Auswahlmöglichkeiten haben, wobei eine die richtige Antwort ist. Formatiere die Antwort als JSON-Array mit Objekten, die 'question', 'options' (Array) und 'correct_index' (0-basierter Index der richtigen Antwort) enthalten.",
            'en': f"Create {num_questions} multiple-choice questions based on the given text. Each question should have 4 options with one correct answer. Format the response as a JSON array with objects containing 'question', 'options' (array), and 'correct_index' (0-based index of the correct answer)."
        },
        'open': {
            'de': f"Erstelle {num_questions} offene Fragen basierend auf dem gegebenen Text. Jede Frage sollte eine Modellantwort haben. Formatiere die Antwort als JSON-Array mit Objekten, die 'question' und 'answer' enthalten.",
            'en': f"Create {num_questions} open-ended questions based on the given text. Each question should have a model answer. Format the response as a JSON array with objects containing 'question' and 'answer'."
        },
        'true_false': {
            'de': f"Erstelle {num_questions} Wahr/Falsch-Fragen basierend auf dem gegebenen Text. Formatiere die Antwort als JSON-Array mit Objekten, die 'statement' und 'is_true' (boolean) enthalten.",
            'en': f"Create {num_questions} true/false questions based on the given text. Format the response as a JSON array with objects containing 'statement' and 'is_true' (boolean)."
        }
    }

    question_type_prompt = system_prompts.get(question_type, system_prompts['multiple_choice'])
    system_prompt = question_type_prompt.get(language, question_type_prompt['en'])

    # Nachrichtenarray erstellen
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Hier ist der Textinhalt, für den du Fragen erstellen sollst:\n\n{content}"}
    ]

    # OpenAI-API aufrufen
    response = await call_openai_api(
        model=model,
        messages=messages,
        temperature=0.7,
        max_tokens=2000,
        response_format={"type": "json_object"}
    )

    # Antwort parsen
    try:
        response_content = response.get('choices', [{}])[0].get('message', {}).get('content', '{}')
        questions_data = json.loads(response_content)

        # Extrahiere Fragen aus der Antwort
        questions = questions_data.get('questions', [])
        if not questions and isinstance(questions_data, list):
            questions = questions_data

        return questions

    except json.JSONDecodeError as e:
        logger.error("Fehler beim Parsen der OpenAI-Antwort für Fragen: %s", e)
        # Fallback: Leeres Array zurückgeben
        return []


async def extract_topics_with_openai(content, max_topics=8, language='de', **options):
    """
    Extrahiert Hauptthemen mit OpenAI.

    Args:
        content (str): Textinhalt für die Themenextraktion.
        max_topics (int): Maximale Anzahl der zu extrahierenden Themen.
        language (str): Sprachcode (de, en, ...).
        **options: Weitere Optionen.

    Returns:
        list: Extrahierte Themen.
    """
    # Model auswählen
    model = options.get('model', DEFAULT_MODEL)

    # System-Prompt basierend auf Sprache
    system_prompts = {
        'de': f"Analysiere den gegebenen Text und extrahiere die wichtigsten Themen (maximal {max_topics}). Für jedes Thema, gib einen Titel und eine kurze Beschreibung an. Formatiere die Antwort als JSON-Array mit Objekten, die 'title' und 'description' enthalten.",
        'en': f"Analyze the given text and extract the main topics (maximum {max_topics}). For each topic, provide a title and a short description. Format the response as a JSON array with objects containing 'title' and 'description'."
    }

    system_prompt = system_prompts.get(language, system_prompts['en'])

    # Nachrichtenarray erstellen
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Hier ist der Textinhalt, für den du die Hauptthemen extrahieren sollst:\n\n{content}"}
    ]

    # OpenAI-API aufrufen
    response = await call_openai_api(
        model=model,
        messages=messages,
        temperature=0.5,  # Niedrigere Temperatur für konsistentere Ergebnisse
        max_tokens=1500,
        response_format={"type": "json_object"}
    )

    # Antwort parsen
    try:
        response_content = response.get('choices', [{}])[0].get('message', {}).get('content', '{}')
        topics_data = json.loads(response_content)

        # Extrahiere Themen aus der Antwort
        topics = topics_data.get('topics', [])
        if not topics and isinstance(topics_data, list):
            topics = topics_data

        return topics

    except json.JSONDecodeError as e:
        logger.error("Fehler beim Parsen der OpenAI-Antwort für Themen: %s", e)
        # Fallback: Leeres Array zurückgeben
        return []
