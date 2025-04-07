"""
Fragen-Generierung für Worker-Tasks
----------------------------------

Dieses Modul enthält Funktionen zur KI-gestützten Generierung von Fragen.
"""

import json
import logging
import os
from typing import List, Dict, Any, Optional
import hashlib # Import hashlib

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Absolute Imports verwenden statt relativer Imports
from utils.call_openai import call_openai_api, extract_json_from_response
from config.prompts import get_system_prompt, get_user_prompt
from redis_utils.client import get_redis_client

def generate_questions_with_openai(
    extracted_text: str,
    num_questions: int = 5, 
    question_type: str = 'multiple_choice', 
    language: str = 'de', 
    **options
) -> Dict[str, Any]:
    """
    Generiert Fragen mit OpenAI (SYNCHRONE VERSION).
    Erhält den Text als Argument.
    Args:
        extracted_text (str): Der Text.
        num_questions (int): Anzahl der Fragen.
        question_type (str): Fragetyp (multiple_choice, open, true_false).
        language (str): Sprachcode (de, en, ...).
        **options: Weitere Optionen (model).
    Returns:
        dict: Enthält {"questions": List[Dict], "usage": Dict} oder leeres Dict bei Fehler.
    """
    model = options.get('model', os.environ.get('OPENAI_DEFAULT_MODEL', 'gpt-3.5-turbo'))
    logger.info("="*50)
    logger.info(f"FRAGEN-GENERIERUNG (SYNC) GESTARTET")
    logger.info(f"Konfiguration: {num_questions} Fragen, Typ: {question_type}, Sprache: {language}, Modell: {model}")
    logger.info("="*50)

    content = extracted_text
    if not content:
        logger.error("[QUESTIONS] Kein Text zur Verarbeitung übergeben.")
        return {"questions": [], "usage": None}

    # Cache-Prüfung (bleibt ähnlich, verwendet `content`)
    response_content = None
    usage = None
    cache_key = None
    CACHE_TTL = 86400 * 7 # 7 Tage
    redis_client = get_redis_client() # Hole Redis Client hier
    try:
        content_hash_part = content[:20000] 
        params_str = f"num:{num_questions}-type:{question_type}-lang:{language}-model:{model}"
        combined_key_material = f"{content_hash_part}-{params_str}"
        # Cache-Key spezifisch für Fragen
        cache_key = f"openai_cache:questions:{hashlib.sha256(combined_key_material.encode('utf-8')).hexdigest()}"
        
        cached_response = redis_client.get(cache_key)
        if cached_response:
            response_content = cached_response.decode('utf-8')
            logger.info(f"[CACHE HIT] Antwort aus Redis-Cache geladen für Key: {cache_key}")
        else:
            logger.info(f"[CACHE MISS] Kein Cache-Eintrag gefunden für Key: {cache_key}")

    except Exception as cache_err:
        logger.warning(f"[FRAGEN] Fehler bei Cache-Prüfung: {cache_err}")

    if response_content is None:
        # Prompts vorbereiten
        system_prompt = get_system_prompt("questions", language=language, num_questions=num_questions, question_type=question_type)
        user_prompt = get_user_prompt("questions", content)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # OpenAI-API aufrufen (SYNCHRON)
        logger.info(f"[QUESTIONS] Schritt 4: Sende SYNC Anfrage an OpenAI API ({model})")
        response = call_openai_api(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        response_content = response.get('choices', [{}])[0].get('message', {}).get('content', '{}')
        usage = response.get('usage')
        logger.info(f"[QUESTIONS] OpenAI-Antwort erhalten. Usage: {usage}")

        # Cache speichern (bleibt gleich)
        if response_content and response_content != '{}' and cache_key:
            try:
                redis_client.set(cache_key, response_content, ex=CACHE_TTL)
                logger.info(f"[CACHE SET] Antwort in Redis gespeichert (Key: {cache_key}, TTL: {CACHE_TTL // 86400} Tage)")
            except Exception as cache_set_err:
                logger.warning(f"[FRAGEN] Fehler beim Speichern der Antwort im Cache: {cache_set_err}")

    # Antwort parsen & Fragen extrahieren/standardisieren (bleibt gleich)
    standardized_questions = []
    try:
        questions_data = extract_json_from_response(response_content)
        logger.info(f"[FRAGEN] JSON erfolgreich geparst: {len(str(questions_data))} Zeichen")
        logger.info(f"[FRAGEN] JSON-Struktur: {type(questions_data)} - Vorschau: {str(questions_data)[:300]}...")

        # SCHRITT 7: Fragen extrahieren
        logger.info(f"[FRAGEN] Schritt 7: Extrahiere Fragen aus JSON")
        
        # Szenario 1: Fragen im "questions"-Feld
        if isinstance(questions_data, dict) and "questions" in questions_data and isinstance(questions_data["questions"], list):
            questions = questions_data["questions"]
            logger.info(f"[FRAGEN] Format 1: Fragen aus 'questions'-Feld extrahiert")
        
        # Szenario 2: Fragen als direkte Liste
        elif isinstance(questions_data, list):
            questions = questions_data
            logger.info(f"[FRAGEN] Format 2: Fragen direkt aus Array extrahiert")
        
        # Szenario 3: Alternatives Feld
        elif isinstance(questions_data, dict):
            for field in ["results", "items", "data"]:
                if field in questions_data and isinstance(questions_data[field], list):
                    questions = questions_data[field]
                    logger.info(f"[FRAGEN] Format 3: Fragen aus '{field}'-Feld extrahiert")
                    break
        
        # Fallback: Leere Liste, wenn nichts gefunden
        if not questions:
            logger.warning(f"[FRAGEN] Keine Fragen im erwarteten Format gefunden. Original-Antwort: {response_content}")
        
        logger.info(f"[FRAGEN] {len(questions)} Fragen gefunden")
        
        # Erste 3 Fragen zur Überprüfung ausgeben
        if questions:
            logger.info(f"[FRAGEN] Beispiel-Fragen (erste {min(3, len(questions))} von {len(questions)}):")
            for i, question in enumerate(questions[:min(3, len(questions))]):
                if isinstance(question, dict):
                    # Wichtigste Felder prüfen
                    question_text = question.get('question', '')
                    logger.info(f"[FRAGEN]   Frage {i+1}: {question_text[:100]}...")
                    
                    if 'options' in question:
                        logger.info(f"[FRAGEN]     Optionen: {question.get('options', [])}") 
                    
                    if 'correct_answer' in question:
                        correct_answer = question.get('correct_answer', None)
                        logger.info(f"[FRAGEN]     Korrekte Antwort: {correct_answer}")
                else:
                    logger.warning(f"[FRAGEN]   Frage {i+1} ist kein Dictionary: {type(question)} - {str(question)[:100]}...")

        # SCHRITT 8: Fragen standardisieren und validieren
        logger.info(f"[FRAGEN] Schritt 8: Standardisiere und validiere Fragen")
        for i, question in enumerate(questions):
            if isinstance(question, dict):
                try:
                    # Frage-Typ-spezifische Validierung
                    if question_type == 'multiple_choice':
                        # Stelle sicher, dass alle erforderlichen Felder vorhanden sind
                        q_text = question.get('question', '')
                        options = question.get('options', [])
                        correct_answer = question.get('correct_answer', 0)
                        explanation = question.get('explanation', '')
                        
                        # Validiere correct_answer-Wert
                        try:
                            correct_answer = int(correct_answer)
                        except (ValueError, TypeError):
                            correct_answer = 0
                            logger.warning(f"[FRAGEN] Frage {i+1}: Nicht-numerischer correct_answer-Wert gefunden, verwende 0")
                        
                        # Prüfe auf gültigen Bereich
                        if options and (correct_answer < 0 or correct_answer >= len(options)):
                            logger.warning(f"[FRAGEN] Frage {i+1}: correct_answer-Index {correct_answer} außerhalb des gültigen Bereichs (0-{len(options)-1}), verwende 0")
                            correct_answer = 0
                        
                        if q_text and options:
                            standardized_questions.append({
                                'question': q_text,
                                'options': options,
                                'correct_answer': correct_answer,
                                'explanation': explanation
                            })
                            logger.info(f"[FRAGEN] Frage {i+1} standardisiert (Multiple-Choice)")
                        else:
                            logger.warning(f"[FRAGEN] Frage {i+1} hat fehlende Pflichtfelder: question={bool(q_text)}, options={bool(options)}")
                    
                    elif question_type == 'open':
                        # Offene Fragen validieren
                        q_text = question.get('question', '')
                        answer = question.get('answer', '')
                        keywords = question.get('keywords', [])
                        
                        if q_text and answer:
                            standardized_questions.append({
                                'question': q_text,
                                'answer': answer,
                                'keywords': keywords
                            })
                            logger.info(f"[FRAGEN] Frage {i+1} standardisiert (Offen)")
                        else:
                            logger.warning(f"[FRAGEN] Frage {i+1} hat fehlende Pflichtfelder: question={bool(q_text)}, answer={bool(answer)}")
                    
                    elif question_type == 'true_false':
                        # Wahr/Falsch-Fragen validieren
                        statement = question.get('statement', '')
                        is_true = question.get('is_true', False)
                        explanation = question.get('explanation', '')
                        
                        if statement:
                            standardized_questions.append({
                                'statement': statement,
                                'is_true': bool(is_true),
                                'explanation': explanation
                            })
                            logger.info(f"[FRAGEN] Frage {i+1} standardisiert (Wahr/Falsch)")
                        else:
                            logger.warning(f"[FRAGEN] Frage {i+1} hat fehlendes Pflichtfeld: statement={bool(statement)}")
                    
                except Exception as e:
                    logger.error(f"[FRAGEN] Fehler bei der Validierung von Frage {i+1}: {e}")
            else:
                logger.warning(f"[FRAGEN] Frage {i+1} ist kein Dictionary: {type(question)}")

        # Wenn keine gültigen Fragen gefunden wurden
        if not standardized_questions:
            logger.warning(f"[FRAGEN] Keine gültigen Fragen gefunden")
            logger.warning(f"[FRAGEN] Erstelle einfache Fallback-Frage")
            
            if question_type == 'multiple_choice':
                standardized_questions.append({
                    'question': 'Was ist das Hauptthema des Dokuments?',
                    'options': ['Hauptthema A', 'Hauptthema B', 'Hauptthema C', 'Hauptthema D'],
                    'correct_answer': 0,
                    'explanation': 'Wähle die Option, die am besten das Hauptthema des Dokuments beschreibt.'
                })
            elif question_type == 'open':
                standardized_questions.append({
                    'question': 'Fasse den Hauptinhalt des Dokuments zusammen.',
                    'answer': 'Der Hauptinhalt muss aus dem Dokument abgeleitet werden.',
                    'keywords': ['Inhalt', 'Zusammenfassung', 'Hauptthema']
                })
            elif question_type == 'true_false':
                standardized_questions.append({
                    'statement': 'Das Dokument enthält wichtige Informationen.',
                    'is_true': True,
                    'explanation': 'Jedes Dokument enthält in der Regel wichtige Informationen.'
                })
                
            logger.info(f"[FRAGEN] Fallback-Frage erstellt")

        # SCHRITT 9: Abschluss
        logger.info("="*50)
        logger.info(f"[QUESTIONS] GENERIERUNG (SYNC) ABGESCHLOSSEN: {len(standardized_questions)} Fragen generiert.")
        logger.info("="*50)
        
        return {"questions": standardized_questions, "usage": usage}

    except Exception as e:
        logger.error(f"[QUESTIONS] Fehler bei Verarbeitung der Antwort: {e}")
        logger.error(f"[QUESTIONS] Antwortinhalt, der zum Fehler führte: {response_content[:500]}...")
        logger.error(f"[QUESTIONS] Vollständiger Fehler-Trace:", exc_info=True)
        standardized_questions = [] # Fallback
        return {"questions": standardized_questions, "usage": None} 