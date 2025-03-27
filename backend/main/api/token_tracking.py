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
from core.openai_integration import (
    count_tokens,
    calculate_token_cost,
    track_token_usage,
    check_credits_available,
    deduct_credits,
    get_user_credits,
    get_usage_stats
)

# Lokales Caching von Kosten für höhere Leistung
_pricing_cache = {}

logger = logging.getLogger(__name__)

# Kosten pro 1000 Tokens (in Credits)
GPT4_INPUT_COST_PER_1K = 10
GPT4_OUTPUT_COST_PER_1K = 30
GPT35_INPUT_COST_PER_1K = 1.5
GPT35_OUTPUT_COST_PER_1K = 2

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

@api_bp.route('/token-usage', methods=['GET'])
@token_required
def get_token_usage():
    """
    Gibt Token-Nutzungsstatistiken für den aktuellen Benutzer zurück.
    
    Returns:
        JSON mit Token-Nutzungsstatistiken
    """
    try:
        # Verwende die zentrale Implementierung
        stats = get_usage_stats(user_id=g.user.id)
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/credits', methods=['GET'])
@token_required
def get_credits():
    """
    Gibt die Anzahl der verfügbaren Credits des Benutzers zurück.
    
    Returns:
        JSON mit Credits-Anzahl
    """
    try:
        # Verwende die zentrale Implementierung
        credits = get_user_credits(user_id=g.user.id)
        return jsonify({"credits": credits}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500 