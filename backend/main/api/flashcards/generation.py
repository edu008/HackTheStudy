"""
Generation-Modul für das Flashcards-Paket
---------------------------------------

Dieses Modul enthält Funktionen zur KI-gestützten Generierung von Flashcards.
Es verwendet OpenAI-APIs, um Lernkarten aus einem gegebenen Text zu extrahieren.
"""

import logging
import json
import re
from openai import OpenAI
import tiktoken
from api.token_tracking import track_token_usage
from .utils import categorize_content

logger = logging.getLogger(__name__)

def generate_flashcards(content, client, analysis, count=10, language='de', session_id=None, function_name=None):
    """
    Generiert Lernkarten aus einem gegebenen Text.
    
    Args:
        content: Der Inhalt, aus dem Flashcards generiert werden sollen
        client: Der OpenAI-Client
        analysis: Die Analyse des Inhalts (Themen, Unterthemen)
        count: Die Anzahl der zu generierenden Flashcards
        language: Die Sprache der Flashcards ('de' oder 'en')
        session_id: Optional - Die Sitzungs-ID für das Token-Tracking
        function_name: Optional - Der Name der Funktion für das Token-Tracking
        
    Returns:
        Eine Liste von Flashcard-Dictionaries
    """
    # Sicherstellen, dass content ein String ist
    if not isinstance(content, str):
        content = str(content)
    
    # Kürze den Inhalt, falls er zu lang ist
    max_token_length = 4000
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    content_tokens = encoding.encode(content)
    
    if len(content_tokens) > max_token_length:
        # Kürze den Inhalt auf die max_token_length
        truncated_content = encoding.decode(content_tokens[:max_token_length])
        logger.warning(f"Inhalt zu lang ({len(content_tokens)} Tokens). Gekürzt auf {max_token_length} Tokens.")
        content = truncated_content
    
    # Systemprompt je nach Sprache
    if language == 'de':
        system_prompt = """Du bist ein hilfreicher Assistent, der Lernkarten für Studierende erstellt. 
Deine Aufgabe ist es, aus dem bereitgestellten Text wichtige Konzepte zu identifizieren und daraus Lernkarten zu generieren.

Jede Lernkarte sollte folgende Struktur haben:
- front: Eine Frage oder ein Begriff auf der Vorderseite
- back: Die Antwort oder Erklärung auf der Rückseite
- category: Eine Kategorie, zu der die Lernkarte gehört (optional)

Die Lernkarten sollten:
1. Wichtige Konzepte, Definitionen und Zusammenhänge abdecken
2. Präzise und klar formuliert sein
3. Verschiedene Aspekte des Themas abdecken
4. Von einfachen zu komplexeren Konzepten fortschreiten
5. Als eigenständige Lerneinheiten funktionieren

Antworte mit einem JSON-Array von Lernkarten-Objekten."""
    else:
        system_prompt = """You are a helpful assistant that creates flashcards for students.
Your task is to identify important concepts from the provided text and generate flashcards from them.

Each flashcard should have the following structure:
- front: A question or term on the front side
- back: The answer or explanation on the back side
- category: A category to which the flashcard belongs (optional)

The flashcards should:
1. Cover important concepts, definitions, and relationships
2. Be precisely and clearly formulated
3. Cover different aspects of the topic
4. Progress from simpler to more complex concepts
5. Function as independent learning units

Respond with a JSON array of flashcard objects."""
    
    # Vorbereitung der Kategorien
    main_topic = analysis.get('main_topic', '')
    subtopics = [st.get('name', '') for st in analysis.get('subtopics', [])]
    
    # Filtere leere Strings
    subtopics = [st for st in subtopics if st]
    
    # Benutzerprompt je nach Sprache
    if language == 'de':
        user_prompt = f"""Generiere {count} Lernkarten basierend auf dem folgenden Text.

Text: ```{content}```

Hauptthema: {main_topic}
Unterthemen: {', '.join(subtopics) if subtopics else 'Keine spezifischen Unterthemen'}

Stelle sicher, dass die Lernkarten wichtige Konzepte und Informationen aus dem Text abdecken.
Die Lernkarten sollten als eigene Lerneinheiten funktionieren, ohne den ursprünglichen Text zu benötigen.
Verteile die Lernkarten auf verschiedene Aspekte des Textes, um eine gute Abdeckung zu gewährleisten.

Gib die Antwort im folgenden JSON-Format zurück:
[
  {{"front": "Frage oder Begriff", "back": "Antwort oder Erklärung", "category": "Kategorienname"}},
  // weitere Lernkarten
]

Die 'category' sollte eines der Unterthemen sein oder ein anderes passendes Thema, falls kein passendes Unterthema existiert."""
    else:
        user_prompt = f"""Generate {count} flashcards based on the following text.

Text: ```{content}```

Main Topic: {main_topic}
Subtopics: {', '.join(subtopics) if subtopics else 'No specific subtopics'}

Ensure that the flashcards cover important concepts and information from the text.
The flashcards should function as independent learning units, without requiring the original text.
Distribute the flashcards across different aspects of the text to ensure good coverage.

Return the answer in the following JSON format:
[
  {{"front": "Question or term", "back": "Answer or explanation", "category": "Category name"}},
  // additional flashcards
]

The 'category' should be one of the subtopics or another suitable topic if no matching subtopic exists."""
    
    try:
        # OpenAI-Anfrage
        response = client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        # Token-Tracking
        if session_id and function_name:
            track_token_usage(
                client=client,
                response=response,
                session_id=session_id,
                function_name=function_name
            )
        
        # Extrahiere JSON aus der Antwort
        result_text = response.choices[0].message.content
        
        # Suche nach JSON-Strukturen
        json_match = re.search(r'(\[[\s\S]*\])', result_text)
        if json_match:
            json_str = json_match.group(1)
            try:
                flashcards = json.loads(json_str)
                return flashcards
            except json.JSONDecodeError:
                # Wenn der JSON-Parse fehlschlägt, versuche es mit dem gesamten Text
                try:
                    result_json = json.loads(result_text)
                    # Extrahiere das Flashcards-Array, falls vorhanden
                    if isinstance(result_json, dict) and 'flashcards' in result_json:
                        return result_json['flashcards']
                    return result_json
                except json.JSONDecodeError:
                    logger.error(f"Fehler beim JSON-Parsing: {result_text}")
                    return generate_fallback_flashcards(analysis, count, language)
        else:
            try:
                # Versuche, den gesamten Text als JSON zu parsen
                result_json = json.loads(result_text)
                # Extrahiere das Flashcards-Array, falls vorhanden
                if isinstance(result_json, dict) and 'flashcards' in result_json:
                    return result_json['flashcards']
                return result_json
            except json.JSONDecodeError:
                logger.error(f"Keine JSON-Struktur gefunden: {result_text}")
                return generate_fallback_flashcards(analysis, count, language)
    
    except Exception as e:
        logger.error(f"Fehler bei der Flashcard-Generierung: {str(e)}")
        return generate_fallback_flashcards(analysis, count, language)

def generate_additional_flashcards(content, client, analysis, existing_flashcards, count=5, language='de', session_id=None, function_name=None):
    """
    Generiert zusätzliche Lernkarten, wobei bestehende Lernkarten berücksichtigt werden.
    
    Args:
        content: Der Inhalt, aus dem Flashcards generiert werden sollen
        client: Der OpenAI-Client
        analysis: Die Analyse des Inhalts (Themen, Unterthemen)
        existing_flashcards: Eine Liste der bereits vorhandenen Flashcards
        count: Die Anzahl der zu generierenden Flashcards
        language: Die Sprache der Flashcards ('de' oder 'en')
        session_id: Optional - Die Sitzungs-ID für das Token-Tracking
        function_name: Optional - Der Name der Funktion für das Token-Tracking
        
    Returns:
        Eine Liste von Flashcard-Dictionaries
    """
    # Sicherstellen, dass content ein String ist
    if not isinstance(content, str):
        content = str(content)
    
    # Kürze den Inhalt, falls er zu lang ist
    max_token_length = 3500
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    content_tokens = encoding.encode(content)
    
    if len(content_tokens) > max_token_length:
        # Kürze den Inhalt auf die max_token_length
        truncated_content = encoding.decode(content_tokens[:max_token_length])
        logger.warning(f"Inhalt zu lang ({len(content_tokens)} Tokens). Gekürzt auf {max_token_length} Tokens.")
        content = truncated_content
    
    # Formatiere die bestehenden Lernkarten
    existing_cards_str = json.dumps(existing_flashcards[:min(len(existing_flashcards), 20)], indent=2)
    
    # Systemprompt je nach Sprache
    if language == 'de':
        system_prompt = """Du bist ein hilfreicher Assistent, der Lernkarten für Studierende erstellt. 
Deine Aufgabe ist es, basierend auf dem bereitgestellten Text weitere Lernkarten zu generieren, die die bereits vorhandenen Lernkarten ergänzen.

Jede Lernkarte sollte folgende Struktur haben:
- front: Eine Frage oder ein Begriff auf der Vorderseite
- back: Die Antwort oder Erklärung auf der Rückseite
- category: Eine Kategorie, zu der die Lernkarte gehört (optional)

Die Lernkarten sollten:
1. Neue Konzepte abdecken, die in den bestehenden Lernkarten noch nicht behandelt wurden
2. Eine gute Ergänzung zu den bestehenden Lernkarten darstellen
3. Verschiedene Aspekte des Themas berücksichtigen
4. Von unterschiedlicher Komplexität sein
5. Als eigenständige Lerneinheiten funktionieren

Antworte mit einem JSON-Array von Lernkarten-Objekten."""
    else:
        system_prompt = """You are a helpful assistant that creates flashcards for students.
Your task is to generate additional flashcards based on the provided text that complement the existing flashcards.

Each flashcard should have the following structure:
- front: A question or term on the front side
- back: The answer or explanation on the back side
- category: A category to which the flashcard belongs (optional)

The flashcards should:
1. Cover new concepts that are not yet addressed in the existing flashcards
2. Serve as a good complement to the existing flashcards
3. Consider different aspects of the topic
4. Be of varying complexity
5. Function as independent learning units

Respond with a JSON array of flashcard objects."""
    
    # Vorbereitung der Kategorien
    main_topic = analysis.get('main_topic', '')
    subtopics = [st.get('name', '') for st in analysis.get('subtopics', [])]
    
    # Filtere leere Strings
    subtopics = [st for st in subtopics if st]
    
    # Benutzerprompt je nach Sprache
    if language == 'de':
        user_prompt = f"""Generiere {count} NEUE Lernkarten basierend auf dem folgenden Text. Diese Lernkarten sollen ZUSÄTZLICH zu den bereits vorhandenen Lernkarten sein und diese ERGÄNZEN.

Text: ```{content}```

Hauptthema: {main_topic}
Unterthemen: {', '.join(subtopics) if subtopics else 'Keine spezifischen Unterthemen'}

Bereits vorhandene Lernkarten:
{existing_cards_str}

Wichtige Regeln:
1. Die neuen Lernkarten dürfen KEINE Duplikate oder zu ähnliche Varianten der bestehenden Lernkarten sein.
2. Fokussiere dich auf Aspekte, die in den bestehenden Lernkarten noch nicht behandelt wurden.
3. Die neuen Lernkarten sollten das vorhandene Set sinnvoll ergänzen.
4. Variiere den Schwierigkeitsgrad der Lernkarten.

Gib die Antwort im folgenden JSON-Format zurück:
[
  {{"front": "Frage oder Begriff", "back": "Antwort oder Erklärung", "category": "Kategorienname"}},
  // weitere Lernkarten
]

Die 'category' sollte eines der Unterthemen sein oder ein anderes passendes Thema, falls kein passendes Unterthema existiert."""
    else:
        user_prompt = f"""Generate {count} NEW flashcards based on the following text. These flashcards should be IN ADDITION to the existing flashcards and COMPLEMENT them.

Text: ```{content}```

Main Topic: {main_topic}
Subtopics: {', '.join(subtopics) if subtopics else 'No specific subtopics'}

Existing flashcards:
{existing_cards_str}

Important rules:
1. The new flashcards must NOT be duplicates or too similar to the existing flashcards.
2. Focus on aspects that are not yet covered in the existing flashcards.
3. The new flashcards should meaningfully supplement the existing set.
4. Vary the difficulty level of the flashcards.

Return the answer in the following JSON format:
[
  {{"front": "Question or term", "back": "Answer or explanation", "category": "Category name"}},
  // additional flashcards
]

The 'category' should be one of the subtopics or another suitable topic if no matching subtopic exists."""
    
    try:
        # OpenAI-Anfrage
        response = client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        # Token-Tracking
        if session_id and function_name:
            track_token_usage(
                client=client,
                response=response,
                session_id=session_id,
                function_name=function_name
            )
        
        # Extrahiere JSON aus der Antwort
        result_text = response.choices[0].message.content
        
        # Suche nach JSON-Strukturen
        json_match = re.search(r'(\[[\s\S]*\])', result_text)
        if json_match:
            json_str = json_match.group(1)
            try:
                flashcards = json.loads(json_str)
                return flashcards
            except json.JSONDecodeError:
                # Wenn der JSON-Parse fehlschlägt, versuche es mit dem gesamten Text
                try:
                    result_json = json.loads(result_text)
                    # Extrahiere das Flashcards-Array, falls vorhanden
                    if isinstance(result_json, dict) and 'flashcards' in result_json:
                        return result_json['flashcards']
                    return result_json
                except json.JSONDecodeError:
                    logger.error(f"Fehler beim JSON-Parsing: {result_text}")
                    return generate_fallback_flashcards(analysis, count, language)
        else:
            try:
                # Versuche, den gesamten Text als JSON zu parsen
                result_json = json.loads(result_text)
                # Extrahiere das Flashcards-Array, falls vorhanden
                if isinstance(result_json, dict) and 'flashcards' in result_json:
                    return result_json['flashcards']
                return result_json
            except json.JSONDecodeError:
                logger.error(f"Keine JSON-Struktur gefunden: {result_text}")
                return generate_fallback_flashcards(analysis, count, language)
    
    except Exception as e:
        logger.error(f"Fehler bei der Flashcard-Generierung: {str(e)}")
        return generate_fallback_flashcards(analysis, count, language)

def generate_fallback_flashcards(analysis, count, language='de'):
    """
    Generiert einfache Fallback-Lernkarten, wenn die OpenAI-API fehlschlägt.
    
    Args:
        analysis: Die Analyse des Inhalts (Themen, Unterthemen)
        count: Die Anzahl der zu generierenden Flashcards
        language: Die Sprache der Flashcards ('de' oder 'en')
        
    Returns:
        Eine Liste von Flashcard-Dictionaries
    """
    main_topic = analysis.get('main_topic', 'Unbekanntes Thema' if language == 'de' else 'Unknown Topic')
    subtopics = [st.get('name', '') for st in analysis.get('subtopics', [])]
    
    # Filtere leere Strings
    subtopics = [st for st in subtopics if st]
    
    if not subtopics:
        if language == 'de':
            subtopics = ['Grundkonzepte', 'Definitionen', 'Anwendungen', 'Beispiele']
        else:
            subtopics = ['Basic Concepts', 'Definitions', 'Applications', 'Examples']
    
    flashcards = []
    
    for i in range(min(count, 10)):  # Maximal 10 Fallback-Karten
        subtopic = subtopics[i % len(subtopics)]
        
        if language == 'de':
            front = f"Was sind wichtige Aspekte von {subtopic} im Kontext von {main_topic}?"
            back = f"Dies ist eine automatisch generierte Fallback-Karte. Bitte beziehen Sie sich auf den ursprünglichen Text, um Informationen über {subtopic} im Kontext von {main_topic} zu erhalten."
        else:
            front = f"What are important aspects of {subtopic} in the context of {main_topic}?"
            back = f"This is an automatically generated fallback card. Please refer to the original text to find information about {subtopic} in the context of {main_topic}."
        
        flashcards.append({
            'front': front,
            'back': back,
            'category': subtopic
        })
    
    return flashcards
