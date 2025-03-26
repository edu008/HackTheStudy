"""
Hilfsfunktionen für die Kommunikation mit der OpenAI API.
"""
import os
import logging
import time
import json

logger = logging.getLogger(__name__)

def get_openai_client():
    """
    Erstellt einen OpenAI-Client mit den Anmeldedaten aus den Umgebungsvariablen.
    
    Returns:
        OpenAI-Client-Objekt
    """
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

def query_openai(client, system_content, user_content, temperature=0.7, max_retries=3):
    """
    Sendet eine Anfrage an die OpenAI API.
    
    Args:
        client: OpenAI-Client-Objekt
        system_content: Systemnachricht
        user_content: Benutzernachricht
        temperature: Temperatur für die Antwortgenerierung (0.0-1.0)
        max_retries: Maximale Anzahl von Wiederholungsversuchen
        
    Returns:
        str: Antwort von OpenAI
    """
    # Bestimme das Modell aus Umgebungsvariablen oder Standard
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    logger.info(f"Verwende OpenAI-Modell: {model}")
    
    # Protokolliere den Prompt (gekürzt)
    prompt_preview = user_content[:300] + "..." if len(user_content) > 300 else user_content
    logger.info(f"Sende Anfrage an OpenAI API mit Prompt: {prompt_preview}")
    
    # Wiederholungsversuche mit exponentiellem Backoff
    retry_count = 0
    while retry_count <= max_retries:
        try:
            start_time = time.time()
            
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content}
                ],
                temperature=temperature,
                max_tokens=4000
            )
            
            processing_time = time.time() - start_time
            logger.info(f"OpenAI-Anfrage verarbeitet in {processing_time:.2f}s")
            
            result = response.choices[0].message.content
            return result
            
        except Exception as e:
            retry_count += 1
            if retry_count <= max_retries:
                # Berechne Wartezeit mit exponentiellem Backoff
                wait_time = 2 ** retry_count
                logger.warning(f"Fehler bei OpenAI-Anfrage (Versuch {retry_count}/{max_retries}): {str(e)}")
                logger.info(f"Warte {wait_time} Sekunden vor dem nächsten Versuch...")
                time.sleep(wait_time)
            else:
                logger.error(f"Alle Versuche fehlgeschlagen ({max_retries}/{max_retries}): {str(e)}")
                raise

def parse_json_response(response_text):
    """
    Parst eine JSON-Antwort von OpenAI.
    
    Args:
        response_text: Die Textantwort von OpenAI
        
    Returns:
        dict: Das geparste JSON-Objekt
    """
    try:
        # Entferne Markdown-Code-Block-Formatierung, falls vorhanden
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        elif cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[3:]
            
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3].strip()
            
        # Parse JSON
        result = json.loads(cleaned_text)
        return result
    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Parsen der JSON-Antwort: {str(e)}")
        logger.error(f"Rohtext: {response_text[:500]}...")
        raise 