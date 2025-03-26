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
        max_text_length = 80000  # Erhöhtes Limit für mehr Kontext
        if len(text) > max_text_length:
            logger.warning(f"Text zu lang für API, wird auf {max_text_length} Zeichen gekürzt")
            # Intelligenteres Kürzen: Behalte Anfang und Ende des Dokuments
            start_chunk = text[:max_text_length//2]
            end_chunk = text[-(max_text_length//2):]
            text = start_chunk + "\n\n[...Inhalt gekürzt...]\n\n" + end_chunk
        
        # System-Prompt basierend auf der Sprache
        if language == 'de':
            system_prompt = """Du bist ein Experte für die Analyse und Strukturierung von Lerninhalten. 
            Deine Aufgabe ist es, den bereitgestellten Text gründlich zu analysieren und eine präzise strukturierte Zusammenfassung 
            zu erstellen, die als Grundlage für ein interaktives Lernmodul dient. Identifiziere das 
            Hauptthema, die wichtigsten Unterthemen, Schlüsselkonzepte und deren Beziehungen zueinander.
            
            Deine Ausgabe MUSS ein valides JSON-Objekt sein, das direkt in einer Anwendung verwendet werden kann."""
        else:
            system_prompt = """You are an expert in analyzing and structuring educational content.
            Your task is to thoroughly analyze the provided text and create a precise structured summary that serves
            as the foundation for an interactive learning module. Identify the main topic, important
            subtopics, key concepts and their relationships to each other.
            
            Your output MUST be a valid JSON object that can be used directly in an application."""
        
        # Hauptprompt basierend auf der Sprache
        if language == 'de':
            prompt = f"""Analysiere den folgenden Text und erstelle eine strukturierte Zusammenfassung:

{text}

Erstelle ein valides JSON-Objekt mit diesen Elementen:
1. "main_topic": Das Hauptthema des Textes als präzise Überschrift
2. "topics": Eine Liste von Unterthemen, jeweils mit "name" und kurzer "description" (max. 2 Sätze)
3. "connections": Beziehungen zwischen den Themen als Liste von Objekten mit "source", "target" und "label"
4. "flashcards": 5-10 hochwertige Lernkarten mit "question" und "answer" (keine Platzhalter)
5. "questions": 3-5 Multiple-Choice-Fragen mit "text", "options" (Array), "correct_answer" (Index) und "explanation"

WICHTIG: Deine Antwort MUSS ein valides JSON-Objekt sein. Verwende keine Markdown-Formatierung oder andere Elemente außerhalb des JSON.
Beantworte Fragen detailliert und konkret basierend auf dem bereitgestellten Inhalt. Sorge dafür, dass die Lernmaterialien von hoher Qualität sind."""
        else:
            prompt = f"""Analyze the following text and create a structured summary:

{text}

Create a valid JSON object with these elements:
1. "main_topic": The main topic of the text as a precise heading
2. "topics": A list of subtopics, each with a "name" and short "description" (max. 2 sentences)
3. "connections": Relationships between topics as a list of objects with "source", "target", and "label"
4. "flashcards": 5-10 high-quality flashcards with "question" and "answer" (no placeholders)
5. "questions": 3-5 multiple-choice questions with "text", "options" (array), "correct_answer" (index), and "explanation"

IMPORTANT: Your response MUST be a valid JSON object. Do not use markdown formatting or any elements outside the JSON.
Answer questions in detail and specifically based on the provided content. Ensure that the learning materials are of high quality."""
        
        # Versuche, die OpenAI-Anfrage zu senden
        client = get_openai_client()
        start_time = time.time()
        response = query_openai(
            client=client,
            system_content=system_prompt,
            user_content=prompt,
            temperature=0.2  # Niedrigere Temperatur für präzisere Antworten
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
                elif cleaned_response.startswith("```"):
                    cleaned_response = cleaned_response[3:]
                if cleaned_response.endswith("```"):
                    cleaned_response = cleaned_response[:-3]
                
                # Speichere die Rohantwort für Diagnose
                logger.debug(f"OpenAI Rohantwort: {cleaned_response[:200]}...")
                
                result = json.loads(cleaned_response.strip())
                
            # Validiere minimale Inhalte
            if "main_topic" not in result:
                result["main_topic"] = "Unbekanntes Thema"
            
            if "topics" not in result or not result["topics"]:
                result["topics"] = [{"name": "Hauptthema", "description": "Zusammenfassung des Inhalts"}]
                
            logger.info(f"JSON-Antwort erfolgreich geparst, enthält {len(result.get('topics', []))} Themen")
            return result
            
        except json.JSONDecodeError as json_err:
            logger.error(f"Fehler beim Parsen der JSON-Antwort: {str(json_err)}")
            logger.error(f"Rohtext der Antwort: {response[:500]}...")
            
            # Erstelle einen manuellen Extraktionsversuch, wenn JSON fehlerhaft ist
            try:
                # Versuche, den JSON-Teil zu extrahieren
                import re
                json_pattern = r'({.*})'
                match = re.search(json_pattern, response, re.DOTALL)
                if match:
                    potential_json = match.group(1)
                    result = json.loads(potential_json)
                    logger.info("JSON konnte durch Regex-Extraktion wiederhergestellt werden")
                    return result
            except Exception:
                pass
            
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