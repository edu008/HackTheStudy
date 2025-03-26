"""
Funktionen zur Textanalyse mit OpenAI API.
"""
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

def analyze_content(text, language='de'):
    """
    Analysiert den Inhalt eines Textes mit OpenAI API.
    
    Args:
        text: Der zu analysierende Text
        language: Die Sprache des Textes (default: 'de')
        
    Returns:
        dict: Analyseergebnisse als Dictionary
    """
    try:
        # Import am Anfang der Funktion, um zirkuläre Abhängigkeiten zu vermeiden
        from utils.openai_utils import get_openai_client, query_openai
        
        logger.info(f"Starte OpenAI-Analyse für {len(text)} Zeichen Text in '{language}'")
        
        # Begrenze die Textlänge für die API
        max_text_length = 60000
        if len(text) > max_text_length:
            logger.warning(f"Text zu lang für API, wird auf {max_text_length} Zeichen gekürzt")
            text = text[:max_text_length]
        
        # System-Prompt basierend auf der Sprache
        if language == 'de':
            system_prompt = """Du bist ein Experte für die Analyse und Strukturierung von Lerninhalten. 
            Deine Aufgabe ist es, den bereitgestellten Text zu analysieren und eine strukturierte Zusammenfassung 
            zu erstellen, die als Grundlage für ein interaktives Lernmodul dienen kann. Identifiziere das 
            Hauptthema, wichtige Unterthemen, Schlüsselkonzepte und deren Beziehungen zueinander."""
        else:
            system_prompt = """You are an expert in analyzing and structuring educational content.
            Your task is to analyze the provided text and create a structured summary that can serve
            as the foundation for an interactive learning module. Identify the main topic, important
            subtopics, key concepts and their relationships to each other."""
        
        # Hauptprompt basierend auf der Sprache
        if language == 'de':
            prompt = f"""Analysiere den folgenden Text und erstelle eine strukturierte Zusammenfassung:

{text}

Erstelle eine JSON-Struktur mit folgenden Elementen:
1. "main_topic": Das Hauptthema des Textes
2. "topics": Eine Liste von Unterthemen, jeweils mit "name" und kurzer "description"
3. "connections": Beziehungen zwischen den Themen
4. "flashcards": 5-10 Lernkarten mit "question" und "answer"
5. "questions": 3-5 Multiple-Choice-Fragen mit "text", "options" (Array), "correct_answer" (Index) und "explanation"

Die Antwort sollte ausschließlich aus einem validen JSON-Objekt bestehen."""
        else:
            prompt = f"""Analyze the following text and create a structured summary:

{text}

Create a JSON structure with the following elements:
1. "main_topic": The main topic of the text
2. "topics": A list of subtopics, each with a "name" and short "description"
3. "connections": Relationships between the topics
4. "flashcards": 5-10 flashcards with "question" and "answer"
5. "questions": 3-5 multiple-choice questions with "text", "options" (array), "correct_answer" (index) and "explanation"

The response should consist exclusively of a valid JSON object."""
        
        # Versuche, die OpenAI-Anfrage zu senden
        client = get_openai_client()
        start_time = time.time()
        response = query_openai(
            client=client,
            system_content=system_prompt,
            user_content=prompt,
            temperature=0.3  # Niedrigere Temperatur für strukturierte Antworten
        )
        
        processing_time = time.time() - start_time
        logger.info(f"OpenAI-Anfrage verarbeitet in {processing_time:.2f}s")
        
        # Extrahiere und parse die JSON-Antwort
        try:
            # Wenn die Antwort bereits ein Wörterbuch ist
            if isinstance(response, dict):
                result = response
            # Wenn die Antwort ein String ist, parse ihn als JSON
            else:
                # Entferne Backticks und andere Markdown-Formatierungen
                cleaned_response = response.strip()
                if cleaned_response.startswith("```json"):
                    cleaned_response = cleaned_response[7:]
                if cleaned_response.startswith("```"):
                    cleaned_response = cleaned_response[3:]
                if cleaned_response.endswith("```"):
                    cleaned_response = cleaned_response[:-3]
                
                result = json.loads(cleaned_response.strip())
                
            logger.info(f"JSON-Antwort erfolgreich geparst, enthält {len(result.get('topics', []))} Themen")
            return result
            
        except json.JSONDecodeError as json_err:
            logger.error(f"Fehler beim Parsen der JSON-Antwort: {str(json_err)}")
            logger.error(f"Rohtext der Antwort: {response[:500]}...")
            
            # Fallback: Erzeuge eine einfache Struktur
            return {
                "main_topic": "Unbekanntes Thema",
                "topics": [
                    {"name": "Fehler bei der Analyse", "description": "Die OpenAI-Antwort konnte nicht verarbeitet werden."}
                ],
                "flashcards": [],
                "questions": []
            }
    
    except Exception as e:
        logger.error(f"Fehler bei der OpenAI-Analyse: {str(e)}")
        return {
            "main_topic": "Fehler",
            "topics": [
                {"name": "Verarbeitungsfehler", "description": f"Fehler bei der Analyse: {str(e)}"}
            ],
            "flashcards": [],
            "questions": []
        }

# Hilfsfunktion für OpenAI-Client und Anfragen
def get_openai_client():
    """Erstellt einen OpenAI-Client mit den Anmeldedaten aus den Umgebungsvariablen."""
    try:
        import openai
        
        # Konfiguriere OpenAI-Client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY nicht in Umgebungsvariablen gefunden")
            raise ValueError("OPENAI_API_KEY fehlt")
            
        client = openai.OpenAI(api_key=api_key)
        return client
    except ImportError:
        logger.error("openai-Paket nicht installiert")
        raise

def query_openai(client, system_content, user_content, temperature=0.7):
    """Sendet eine Anfrage an die OpenAI API."""
    try:
        # Bestimme das Modell aus Umgebungsvariablen oder Standard
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            temperature=temperature,
            max_tokens=4000
        )
        
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Fehler bei der OpenAI-Anfrage: {str(e)}")
        raise 