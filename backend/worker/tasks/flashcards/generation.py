"""
Flashcards-Generierung für Worker-Tasks
---------------------------------------

Dieses Modul enthält Funktionen zur KI-gestützten Generierung von Flashcards.
"""

import json
import logging
import os
from typing import List, Dict, Any, Optional
import datetime
import hashlib

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Absolute Imports verwenden statt relativer Imports
from utils.call_openai import call_openai_api, extract_json_from_response
from config.prompts import get_system_prompt, get_user_prompt
from redis_utils.client import get_redis_client

def generate_flashcards_with_openai(
    extracted_text: str,
    num_cards: int = 10, 
    language: str = 'de', 
    **options
) -> Dict[str, Any]:
    """
    Generiert Lernkarten mit OpenAI (SYNCHRONE VERSION).
    Erhält den Text als Argument.

    Args:
        extracted_text (str): Der Text, aus dem Karten generiert werden sollen.
        num_cards (int): Anzahl der zu generierenden Karten.
        language (str): Sprachcode (de, en, fr, es, ...).
        **options: Weitere Optionen (z.B. 'model').

    Returns:
        dict: Enthält {"flashcards": List[Dict], "usage": Dict} oder leeres Dict bei Fehler.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    model = options.get('model', os.environ.get('OPENAI_DEFAULT_MODEL', 'gpt-3.5-turbo'))
    
    logger.info("="*50)
    logger.info(f"FLASHCARD-GENERIERUNG (SYNC) [{timestamp}] GESTARTET")
    logger.info(f"Konfiguration: {num_cards} Karten, Sprache: {language}, Modell: {model}")
    logger.info("="*50)

    content = extracted_text
    if not content:
         logger.error("[FLASHCARDS] Kein Text zur Verarbeitung übergeben.")
         return {"flashcards": [], "usage": None} # Leeres Ergebnis

    response_content = None
    cache_key = None
    CACHE_TTL = 86400 * 7 # 7 Tage
    try:
        # Erstelle einen eindeutigen Hash basierend auf Inhalt und Parametern
        # (Verwende nur die ersten X Zeichen des Inhalts für den Hash, um Performance zu schonen)
        content_hash_part = content[:20000] # Beispiel: erste 20k Zeichen
        params_str = f"num:{num_cards}-lang:{language}-model:{model}"
        combined_key_material = f"{content_hash_part}-{params_str}"
        cache_key = f"openai_cache:flashcards:{hashlib.sha256(combined_key_material.encode('utf-8')).hexdigest()}"
        
        cached_response = get_redis_client().get(cache_key)
        if cached_response:
            response_content = cached_response.decode('utf-8')
            logger.info(f"[CACHE HIT] Antwort aus Redis-Cache geladen für Key: {cache_key}")
            # Überspringe API-Aufruf, gehe direkt zur JSON-Extraktion
        else:
            logger.info(f"[CACHE MISS] Kein Cache-Eintrag gefunden für Key: {cache_key}")

    except Exception as cache_err:
        logger.warning(f"[FLASHCARDS] Fehler bei Cache-Prüfung: {cache_err}")
        # Fortfahren ohne Cache

    usage = None # Initialisiere usage

    if response_content is None:
        logger.info(f"[FLASHCARDS] Schritt 1: Analysiere Text ({len(content)} Zeichen)")
        tokens_estimate = len(content) // 4
        logger.info(f"[FLASHCARDS] Geschätzte Token-Anzahl: ~{tokens_estimate}")
        logger.info(f"[FLASHCARDS] Textvorschau: {content[:200]}...")

        logger.info(f"[FLASHCARDS] Schritt 2: Erstelle Prompts für die KI")
        system_prompt = get_system_prompt("flashcards", language=language, num_cards=num_cards)
        user_prompt = get_user_prompt("flashcards", content)
        
        logger.info(f"[FLASHCARDS] System-Prompt erstellt ({len(system_prompt)} Zeichen)")
        logger.info(f"[FLASHCARDS] System-Prompt Anfang: {system_prompt[:150]}...")
        logger.info(f"[FLASHCARDS] User-Prompt erstellt ({len(user_prompt)} Zeichen)")
        
        logger.info(f"[FLASHCARDS] Schritt 3: Erstelle Nachrichtenarray für OpenAI")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        logger.info(f"[FLASHCARDS] Nachrichtenarray mit {len(messages)} Nachrichten erstellt")
        
        logger.info(f"[FLASHCARDS] Schritt 4: Sende SYNC Anfrage an OpenAI API ({model})")
        response = call_openai_api(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        logger.info(f"[FLASHCARDS] OpenAI-Antwort erhalten.")

        response_content = response.get('choices', [{}])[0].get('message', {}).get('content', '{}')
        usage = response.get('usage') 
        logger.info(f"[FLASHCARDS] Antworttext extrahiert. Usage: {usage}")
        
        if response_content and response_content != '{}' and cache_key:
            try:
                get_redis_client().set(cache_key, response_content, ex=CACHE_TTL)
                logger.info(f"[CACHE SET] Antwort in Redis gespeichert (Key: {cache_key}, TTL: {CACHE_TTL // 86400} Tage)")
            except Exception as cache_set_err:
                logger.warning(f"[FLASHCARDS] Fehler beim Speichern der Antwort im Cache: {cache_set_err}")

    logger.info(f"[FLASHCARDS] Schritt 5: Verarbeite OpenAI-Antwort")
    try:
        logger.info(f"[FLASHCARDS] Schritt 5/6: Verarbeite Antwortinhalt (aus Cache oder API)")
        logger.info(f"[FLASHCARDS] Antwortvorschau: {response_content[:200]}...")
        
        logger.info(f"[FLASHCARDS] Schritt 6: Extrahiere JSON aus Antwortinhalt")
        cards_data = extract_json_from_response(response_content)
        logger.info(f"[FLASHCARDS] JSON erfolgreich geparst: {len(str(cards_data))} Zeichen")
        logger.info(f"[FLASHCARDS] JSON-Struktur: {type(cards_data)} - Vorschau: {str(cards_data)[:300]}...")

        logger.info(f"[FLASHCARDS] Schritt 7: Extrahiere Karten aus JSON")
        
        cards = []
        if isinstance(cards_data, dict):
            if "flashcards" in cards_data and isinstance(cards_data["flashcards"], list):
                cards = cards_data["flashcards"]
                logger.info(f"[FLASHCARDS] Format 1: Karten aus 'flashcards'-Feld extrahiert")
            elif "cards" in cards_data and isinstance(cards_data["cards"], list):
                cards = cards_data["cards"]
                logger.warning(f"[FLASHCARDS] Format 1b (Fallback): Karten aus 'cards'-Feld extrahiert")
            elif "question" in cards_data and "answer" in cards_data:
                 cards = [cards_data]
                 logger.warning(f"[FLASHCARDS] Format 4 (Fallback): Einzelne Karte aus Wurzel-Objekt extrahiert")
                 
        elif isinstance(cards_data, list):
            cards = cards_data
            logger.warning(f"[FLASHCARDS] Format 2 (Fallback): Karten direkt aus Array extrahiert")
       
        if not cards:
            logger.warning(f"[FLASHCARDS] Keine Karten im erwarteten Format gefunden. Original-Antwort: {response_content}")
        
        logger.info(f"[FLASHCARDS] {len(cards)} Karten gefunden")
        
        if cards:
            logger.info(f"[FLASHCARDS] Beispiel-Karten (erste {min(3, len(cards))} von {len(cards)}):")
            for i, card in enumerate(cards[:min(3, len(cards))]):
                if isinstance(card, dict):
                    has_question = "question" in card or "front" in card
                    has_answer = "answer" in card or "back" in card
                    
                    logger.info(f"[FLASHCARDS] Karte {i+1} hat question/front: {has_question}, answer/back: {has_answer}")
                    
                    if has_question and has_answer:
                        question = card.get("question", card.get("front", ""))
                        answer = card.get("answer", card.get("back", ""))
                        logger.info(f"[FLASHCARDS]   Karte {i+1}:")
                        logger.info(f"[FLASHCARDS]     Frage: {question[:100]}...")
                        logger.info(f"[FLASHCARDS]     Antwort: {answer[:100]}...")
                    else:
                        logger.info(f"[FLASHCARDS]   Karte {i+1} hat unerwartetes Format. Schlüssel: {list(card.keys())}")
                        logger.info(f"[FLASHCARDS]   Inhalt: {str(card)[:200]}...")
                else:
                    logger.warning(f"[FLASHCARDS]   Karte {i+1} ist kein Dictionary: {type(card)} - {str(card)[:100]}...")
            
        logger.info(f"[FLASHCARDS] Schritt 8: Standardisiere Feldnamen")
        standardized_cards = []
        for i, card in enumerate(cards):
            if isinstance(card, dict):
                question = card.get('question', card.get('front', ''))
                answer = card.get('answer', card.get('back', ''))
                
                if question and answer:
                    standardized_cards.append({
                        'question': question,
                        'answer': answer
                    })
                    logger.info(f"[FLASHCARDS] Karte {i+1} standardisiert: {len(question)} Zeichen (Frage), {len(answer)} Zeichen (Antwort)")
                else:
                    logger.warning(f"[FLASHCARDS] Karte {i+1} hat fehlende Felder: question={bool(question)}, answer={bool(answer)}")
            else:
                logger.warning(f"[FLASHCARDS] Karte {i+1} ist kein Dictionary: {type(card)}")
        
        if not standardized_cards:
            logger.warning(f"[FLASHCARDS] Keine standardisierten Karten gefunden")
            
            if isinstance(cards_data, dict) and len(cards_data) > 0:
                fallback_cards = []
                
                if "question" in cards_data and "answer" in cards_data:
                    fallback_cards.append({
                        'question': cards_data.get('question', ''),
                        'answer': cards_data.get('answer', '')
                    })
                    logger.info(f"[FALLBACK] Einzelne Karte aus Wurzelobjekt extrahiert")
                
                if fallback_cards:
                    logger.info(f"[FALLBACK] {len(fallback_cards)} Karten manuell extrahiert")
                    return {"flashcards": fallback_cards, "usage": usage}
            
            logger.warning(f"[FLASHCARDS] Fallback auf leere Liste")
            return {"flashcards": [], "usage": usage}
            
        logger.info(f"[FLASHCARDS] Schritt 9: Überprüfe Karten auf fehlende Antworten")
        final_cards = []
        for i, card in enumerate(standardized_cards):
            question = card.get('question')
            answer = card.get('answer')
            
            if question and not answer:
                logger.warning(f"[FLASHCARDS] Karte {i+1} hat keine Antwort. Generiere Antwort (SYNC)..." )
                try:
                    answer_prompt_messages = [
                        {"role": "system", "content": f"Beantworte die folgende Frage präzise basierend auf dem Kontext, falls möglich. Gib NUR die Antwort zurück.\n\nKontext:\n{content[:8000]}"},
                        {"role": "user", "content": question}
                    ]
                    answer_response = call_openai_api(
                        model=model, 
                        messages=answer_prompt_messages,
                        temperature=0.5,
                        max_tokens=300
                    )
                    answer_text = answer_response.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
                    if answer_text:
                        answer = answer_text
                        logger.info(f"[FLASHCARDS] Antwort für Karte {i+1} SYNC generiert.")
                        final_cards.append({'question': question, 'answer': answer})
                    else:
                        logger.warning(f"[FLASHCARDS] Konnte keine Antwort für Karte {i+1} generieren.")
                except Exception as e:
                    logger.error(f"[FLASHCARDS] Fehler beim SYNC Generieren der Antwort für Karte {i+1}: {e}")
            elif question and answer:
                final_cards.append(card)
            else:
                 logger.warning(f"[FLASHCARDS] Karte {i+1} wird übersprungen (keine Frage oder Antwort): {card}")

        logger.info(f"[FLASHCARDS] Schritt 10: Führe Sprachprüfung durch (Zielsprache: {language})")
        if language != 'de':
            german_words = ['was', 'ist', 'wie', 'sind', 'warum', 'beschreibe', 'erkläre', 'definiere']
            
            deutsch_gefunden = False
            for i, card in enumerate(final_cards[:3]):
                question = card['question'].lower()
                
                for german_word in german_words:
                    if question.startswith(german_word + ' '):
                        deutsch_gefunden = True
                        logger.warning(f"[FLASHCARDS] Deutsche Wörter in Frage gefunden (Karte {i+1}): '{question[:50]}...'")
            
            if deutsch_gefunden:
                logger.warning(f"[FLASHCARDS] Einige Fragen wurden auf Deutsch generiert, obwohl die Zielsprache {language} ist.")
        
        logger.info("="*50)
        logger.info(f"[FLASHCARDS] GENERIERUNG ERFOLGREICH ABGESCHLOSSEN")
        logger.info(f"[FLASHCARDS] {len(final_cards)} Lernkarten in {language} generiert")
        logger.info("="*50)
        
        return {"flashcards": final_cards, "usage": usage}
        
    except Exception as e:
        logger.error(f"[FLASHCARDS] Fehler bei der Verarbeitung der Antwort: {e}")
        logger.error(f"[FLASHCARDS] Antwortinhalt, der zum Fehler führte: {response_content[:500]}...")
        logger.error(f"[FLASHCARDS] Vollständiger Fehler-Trace:", exc_info=True)
        return {"flashcards": [], "usage": None} 