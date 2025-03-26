"""
Verbessertes Token-Tracking-System für die Monetarisierung
-----------------------------------------------------------
Dieses Modul stellt erweiterte Funktionen für das Token-Tracking und die Credit-Berechnung bereit.
Es verfolgt den Input- und Output-Tokenverbrauch jeder Funktion und speichert sie in der Datenbank.
"""

from flask import current_app, g, jsonify
from . import api_bp
from .auth import token_required
from core.models import db, User, TokenUsage
import tiktoken
import logging
import math
import uuid
import os
import time
import json
import threading
import inspect
import traceback
from datetime import datetime

# Lokales Caching von Kosten für höhere Leistung
_pricing_cache = {}

logger = logging.getLogger(__name__)

# Kosten pro 1000 Tokens (in Credits)
GPT4_INPUT_COST_PER_1K = 10
GPT4_OUTPUT_COST_PER_1K = 30
GPT35_INPUT_COST_PER_1K = 1.5
GPT35_OUTPUT_COST_PER_1K = 2

def count_tokens(text, model="gpt-4o"):
    """
    Zählt die Tokens in einem Text für ein bestimmtes Modell
    
    Args:
        text (str): Der zu zählende Text
        model (str): Das Modell, für das die Tokens gezählt werden sollen
        
    Returns:
        int: Die Anzahl der Tokens
    """
    if not text:
        return 0
        
    try:
        encoder = tiktoken.encoding_for_model(model)
        token_count = len(encoder.encode(text))
        logger.info(f"Tiktoken-Zählung: {token_count} Tokens für {len(text)} Zeichen")
        return token_count
    except Exception as e:
        logger.warning(f"Fehler beim Zählen der Tokens mit tiktoken: {str(e)}")
        # Fallback: Ungefähre Schätzung (1 Token ≈ 4 Zeichen)
        fallback_count = len(text) // 4
        logger.warning(f"Fallback-Zählung verwendet: {fallback_count} Tokens (ca.)")
        return fallback_count

def calculate_token_cost(input_tokens, output_tokens, model="gpt-4o", document_tokens=None):
    """
    Berechnet die Kosten basierend auf Token-Anzahl und Modell.
    
    Args:
        input_tokens (int): Anzahl der Input-Token
        output_tokens (int): Anzahl der Output-Token
        model (str): Das verwendete OpenAI-Modell
        document_tokens (int, optional): Die tatsächliche Anzahl der Tokens im Dokument (ohne Systemprompt)
        
    Returns:
        int: Kosten in Credits (gerundet auf die nächste ganze Zahl)
    """
    # Für sehr kleine Dokumente (<500 Tokens), unabhängig vom Gesamtprompt
    if input_tokens < 500:
        return 100  # Pauschale Mindestgebühr für kleine Dokumente
        
    # Für mittlere Dokumente (500-3000 Tokens)
    if input_tokens < 3000:
        return 200  # Pauschale Gebühr für mittlere Dokumente
    
    # Basis-Kosten pro 1000 Token
    if model.startswith("gpt-4"):
        input_cost_per_1k = 150  # 15 Credits pro 1000 Tokens (Entspricht 15.000 für 100.000)
        output_cost_per_1k = 300  # 30 Credits pro 1000 Tokens
    else:  # GPT-3.5
        input_cost_per_1k = 15  # 1,5 Credits pro 1000 Tokens
        output_cost_per_1k = 20  # 2 Credits pro 1000 Tokens
    
    # Direkte Berechnung der Kosten basierend auf Token-Anzahl
    input_cost = (input_tokens / 1000) * input_cost_per_1k
    output_cost = (output_tokens / 1000) * output_cost_per_1k
    
    # Gesamtkosten berechnen und auf die nächste ganze Zahl aufrunden
    total_cost = math.ceil(input_cost + output_cost)
    
    # Mindestkosten von 100 Credits pro API-Aufruf für größere Dokumente
    return max(100, total_cost)

def track_token_usage(user_id, session_id, function_name, input_tokens, output_tokens, model="gpt-4o", details=None):
    """
    Verfolgt die Token-Nutzung für einen bestimmten Benutzer und eine Funktion.
    
    Args:
        user_id (str): Die ID des Benutzers
        session_id (str): Die ID der Session
        function_name (str): Der Name der Funktion, die die Tokens verwendet hat
        input_tokens (int): Die Anzahl der Input-Tokens
        output_tokens (int): Die Anzahl der Output-Tokens
        model (str): Das verwendete OpenAI-Modell
        details (dict, optional): Zusätzliche Details zur Anfrage
        
    Returns:
        bool: True, wenn das Tracking erfolgreich war, False sonst
    """
    try:
        # Logging für Tracking-Informationen
        logger.info(f"Token-Tracking für Benutzer {user_id} (Funktion: {function_name}): Input={input_tokens}, Output={output_tokens}, Modell={model}")
        
        # Wenn details vorhanden sind, logge eine Zusammenfassung
        if details:
            # Extrahiere wichtige Informationen aus details, falls vorhanden
            prompt_info = f"Prompt: {details.get('prompt_length', '?')} Zeichen" if 'prompt_length' in details else ""
            response_info = f"Antwort: {details.get('response_length', '?')} Zeichen" if 'response_length' in details else ""
            
            if prompt_info or response_info:
                logger.info(f"Details für {function_name}: {prompt_info}, {response_info}")
                
            # Wenn der Prompt oder die Antwort in den Details enthalten sind, zeige Ausschnitte an
            if 'prompt' in details:
                prompt = details['prompt']
                logger.info(f"Prompt-Ausschnitt: {prompt[:500]}...")
                
            if 'response' in details:
                response = details['response']
                logger.info(f"Antwort-Ausschnitt: {response[:500]}...")
        
        # Speichere die Token-Nutzung in der Datenbank
        try:
            # Berechne die Kosten in Credits
            cost = calculate_token_cost(input_tokens, output_tokens, model)
            
            # Erstelle einen neuen TokenUsage-Eintrag
            usage = TokenUsage(
                id=str(uuid.uuid4()),
                user_id=user_id,
                session_id=session_id,
                timestamp=datetime.utcnow(),
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                endpoint=function_name,
                function_name=function_name,
                cached=False,
                request_metadata=details
            )
            
            db.session.add(usage)
            db.session.commit()
            
            logger.info(f"Token-Nutzung in Datenbank gespeichert: {cost} Credits für {function_name}")
            return True
            
        except Exception as db_err:
            logger.error(f"Fehler beim Speichern der Token-Nutzung in der Datenbank: {str(db_err)}")
            return False
            
    except Exception as e:
        logger.error(f"Fehler beim Token-Tracking: {str(e)}")
        return False

def check_credits_available(cost, user_id=None):
    """
    Überprüft, ob der Benutzer genügend Credits hat, ohne sie abzuziehen
    
    Args:
        cost (int): Anzahl der Credits, die benötigt werden
        user_id (str, optional): Die ID des Benutzers (falls nicht in g.user)
        
    Returns:
        bool: True, wenn genügend Credits vorhanden sind, False sonst
    """
    # Wenn eine spezifische Benutzer-ID angegeben wurde, verwende diese
    if user_id:
        user = User.query.get(user_id)
        if not user:
            return False
        return user.credits >= cost
    
    # Ansonsten den aktuellen Benutzer aus g verwenden
    if not hasattr(g, 'user') or not g.user:
        return False
    
    user_id = g.user.id
    user = User.query.get(user_id)
    
    if not user:
        return False
    
    return user.credits >= cost

def deduct_credits(user_id, cost, session_id=None, function_name=None):
    """
    Zieht Credits von einem Benutzer ab.
    
    Args:
        user_id (str): Die ID des Benutzers
        cost (int): Die Anzahl der abzuziehenden Credits
        session_id (str, optional): Die ID der Session
        function_name (str, optional): Der Name der Funktion, für die Credits abgezogen werden
        
    Returns:
        bool: True, wenn die Credits erfolgreich abgezogen wurden, False sonst
    """
    try:
        user = User.query.get(user_id)
        
        if not user:
            logger.warning(f"Benutzer {user_id} nicht gefunden für Credits-Abzug")
            return False
        
        if user.credits < cost:
            logger.warning(f"Benutzer {user_id} hat nicht genügend Credits: {user.credits} < {cost}")
            return False
        
        # Credits abziehen
        user.credits -= cost
        db.session.commit()
        
        logger.info(f"Credits abgezogen: {cost} von Benutzer {user_id}, neue Bilanz: {user.credits}")
        return True
        
    except Exception as e:
        logger.error(f"Fehler beim Abziehen von Credits: {str(e)}")
        db.session.rollback()
        return False

def update_token_usage(user_id, session_id, input_tokens, output_tokens, model="gpt-4o", endpoint=None, function_name=None, is_cached=False, metadata=None):
    """
    Aktualisiert die Token-Nutzungsstatistik für einen Benutzer und zieht die entsprechenden Credits ab.
    
    Args:
        user_id (str): Die ID des Benutzers
        session_id (str): Die ID der Session
        input_tokens (int): Die Anzahl der Input-Tokens
        output_tokens (int): Die Anzahl der Output-Tokens
        model (str, optional): Das verwendete OpenAI-Modell
        endpoint (str, optional): Der API-Endpunkt, der verwendet wurde
        function_name (str, optional): Name der aufrufenden Funktion
        is_cached (bool, optional): Gibt an, ob die Antwort aus dem Cache kam
        metadata (dict, optional): Zusätzliche Metadaten zur Anfrage
        
    Returns:
        dict: Ein Ergebnisobjekt mit dem Status und der Anzahl der abgezogenen Credits
    """
    try:
        # Kosten berechnen
        credits_cost = calculate_token_cost(input_tokens, output_tokens, model)
        
        # Überprüfe, ob der Benutzer genügend Credits hat
        from core.models import User, db
        user = User.query.get(user_id)
        
        if not user:
            logger.warning(f"Benutzer {user_id} nicht gefunden für Token-Tracking")
            return {
                "success": False,
                "error": "Benutzer nicht gefunden",
                "credits_cost": credits_cost
            }
        
        # Wenn es sich um einen Cache-Hit handelt, reduziere die Kosten
        if is_cached:
            credits_cost = max(1, int(credits_cost * 0.1))  # 90% Rabatt für Cache-Hits, mindestens 1 Credit
        
        # Überprüfe, ob genügend Credits vorhanden sind
        if user.credits < credits_cost:
            logger.warning(f"Benutzer {user_id} hat nicht genügend Credits: {user.credits} < {credits_cost}")
            return {
                "success": False,
                "error": "Nicht genügend Credits",
                "available_credits": user.credits,
                "required_credits": credits_cost
            }
        
        # Credits abziehen
        user.credits -= credits_cost
        
        # Token-Nutzung in der Datenbank speichern
        token_usage = TokenUsage(
            id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
            timestamp=datetime.utcnow(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=credits_cost,
            endpoint=endpoint or "unknown",
            function_name=function_name or "unknown",
            cached=is_cached,
            request_metadata=metadata
        )
        
        db.session.add(token_usage)
        db.session.commit()
        
        logger.info(f"Credits abgezogen: {credits_cost} von Benutzer {user_id}, neue Bilanz: {user.credits}")
        
        return {
            "success": True,
            "credits_cost": credits_cost,
            "remaining_credits": user.credits,
            "token_usage_id": token_usage.id
        }
        
    except Exception as e:
        logger.error(f"Fehler beim Aktualisieren der Token-Nutzung: {str(e)}")
        traceback.print_exc()
        
        # Bei einem Fehler versuchen wir, die Transaktion rückgängig zu machen
        db.session.rollback()
        
        return {
            "success": False,
            "error": str(e),
            "credits_cost": credits_cost if 'credits_cost' in locals() else None
        }

def get_user_credits(user_id):
    """
    Gibt die aktuelle Anzahl der Credits eines Benutzers zurück.
    
    Args:
        user_id (str): Die ID des Benutzers
        
    Returns:
        int: Die Anzahl der Credits oder 0, wenn der Benutzer nicht gefunden wurde
    """
    from core.models import User
    
    user = User.query.get(user_id)
    if not user:
        return 0
    
    return user.credits

@api_bp.route('/token-usage', methods=['GET'])
@token_required
def get_token_usage():
    """
    API-Endpunkt, um die Token-Nutzung des aktuellen Benutzers abzurufen.
    """
    user_id = request.user_id
    
    # Token-Nutzung aus der Datenbank holen
    usage_records = TokenUsage.query.filter_by(user_id=user_id).order_by(TokenUsage.timestamp.desc()).limit(50).all()
    
    # Für jeden Eintrag ein Dictionary erstellen
    usage_list = []
    for usage in usage_records:
        usage_list.append({
            'id': usage.id,
            'timestamp': usage.timestamp.isoformat() if usage.timestamp else None,
            'model': usage.model,
            'input_tokens': usage.input_tokens,
            'output_tokens': usage.output_tokens,
            'cost': usage.cost,
            'endpoint': usage.endpoint,
            'function_name': usage.function_name,
            'cached': usage.cached
        })
    
    # Gesamtnutzung berechnen
    total_input_tokens = sum(usage.input_tokens for usage in usage_records)
    total_output_tokens = sum(usage.output_tokens for usage in usage_records)
    total_cost = sum(usage.cost for usage in usage_records)
    
    # Benutzer-Credits abrufen
    user = User.query.get(user_id)
    current_credits = user.credits if user else 0
    
    return jsonify({
        'success': True,
        'data': {
            'usage_records': usage_list,
            'summary': {
                'total_input_tokens': total_input_tokens,
                'total_output_tokens': total_output_tokens,
                'total_cost': total_cost,
                'current_credits': current_credits
            }
        }
    }) 