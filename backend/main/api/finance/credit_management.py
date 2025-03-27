"""
Kreditverwaltungsfunktionen für das Finanzmodul.
Enthält Funktionen zum Abfragen, Hinzufügen und Abziehen von Credits.
"""

import logging
import math
from datetime import datetime
from functools import wraps
import uuid
from flask import current_app, g, jsonify
from core.models import db, User, TokenUsage
from .constants import token_to_credits

# Logger konfigurieren
logger = logging.getLogger(__name__)

def check_and_deduct_credits(cost):
    """
    Decorator zum Überprüfen und Abziehen von Credits.
    
    Args:
        cost (int): Anzahl der Credits, die für diesen API-Aufruf abgezogen werden sollen
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Benutzer aus der aktuellen Anfrage abrufen
            if not hasattr(g, 'user') or not g.user:
                return jsonify({'error': 'Benutzer nicht authentifiziert'}), 401
            
            user_id = g.user.id
            user = User.query.get(user_id)
            
            if not user:
                return jsonify({'error': 'Benutzer nicht gefunden'}), 404
            
            # Prüfen, ob der Benutzer genügend Credits hat
            if user.credits < cost:
                return jsonify({
                    'error': 'Nicht genügend Credits',
                    'credits_required': cost,
                    'credits_available': user.credits
                }), 402
            
            # Credits abziehen
            user.credits -= cost
            db.session.commit()
            
            # Die dekorierte Funktion ausführen
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def check_and_deduct_dynamic_credits(calculate_cost_function):
    """
    Decorator zum Überprüfen und Abziehen von dynamisch berechneten Credits.
    Die Kostenfunktion wird verwendet, um die Kosten basierend auf der Anfrage zu berechnen.
    
    Args:
        calculate_cost_function: Funktion, die die Kosten basierend auf den Argumenten berechnet
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Benutzer aus der aktuellen Anfrage abrufen
            if not hasattr(g, 'user') or not g.user:
                return jsonify({'error': 'Benutzer nicht authentifiziert'}), 401
            
            user_id = g.user.id
            user = User.query.get(user_id)
            
            if not user:
                return jsonify({'error': 'Benutzer nicht gefunden'}), 404
            
            # Kosten basierend auf den Argumenten berechnen
            cost = calculate_cost_function(*args, **kwargs)
            
            # Prüfen, ob der Benutzer genügend Credits hat
            if user.credits < cost:
                return jsonify({
                    'error': 'Nicht genügend Credits',
                    'credits_required': cost,
                    'credits_available': user.credits,
                    'message': 'Bitte laden Sie Ihre Credits auf, um diese Funktion zu nutzen.'
                }), 402
            
            # Credits abziehen
            user.credits -= cost
            db.session.commit()
            
            # Die dekorierte Funktion ausführen
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_user_credits(user_id):
    """
    Ruft die aktuellen Credits eines Benutzers ab.
    
    Args:
        user_id (str): Die ID des Benutzers
        
    Returns:
        int: Die Anzahl der Credits des Benutzers
    """
    user = User.query.get(user_id)
    if not user:
        return 0
    return user.credits

def add_credits(user_id, credits, reason=None):
    """
    Fügt einem Benutzer Credits hinzu.
    
    Args:
        user_id (str): Die ID des Benutzers
        credits (int): Die Anzahl der hinzuzufügenden Credits
        reason (str, optional): Der Grund für die Gutschrift
        
    Returns:
        bool: True, wenn erfolgreich, False sonst
    """
    user = User.query.get(user_id)
    if not user:
        return False
    
    try:
        user.credits += credits
        db.session.commit()
        
        # Logge die Gutschrift
        logger.info(f"Credits hinzugefügt: {credits} für Benutzer {user_id} ({reason if reason else 'Keine Angabe'})")
        
        return True
    except Exception as e:
        db.session.rollback()
        logger.error(f"Fehler beim Hinzufügen von Credits: {str(e)}")
        return False

def deduct_credits(user_id, credits, reason=None):
    """
    Zieht einem Benutzer Credits ab.
    
    Args:
        user_id (str): Die ID des Benutzers
        credits (float): Die Anzahl der abzuziehenden Credits
        reason (str, optional): Der Grund für den Abzug
        
    Returns:
        bool: True, wenn erfolgreich, False sonst
    """
    user = User.query.get(user_id)
    if not user:
        return False
    
    try:
        if user.credits < credits:
            logger.warning(f"Nicht genügend Credits: Benutzer {user_id} hat {user.credits}, benötigt {credits}")
            return False
        
        user.credits -= credits
        db.session.commit()
        
        # Logge den Abzug
        logger.info(f"Credits abgezogen: {credits} von Benutzer {user_id} ({reason if reason else 'Keine Angabe'})")
        
        return True
    except Exception as e:
        db.session.rollback()
        logger.error(f"Fehler beim Abziehen von Credits: {str(e)}")
        return False

def check_credits_available(user_id, required_credits):
    """
    Prüft, ob ein Benutzer genügend Credits hat.
    
    Args:
        user_id (str): Die ID des Benutzers
        required_credits (float): Die benötigten Credits
        
    Returns:
        bool: True, wenn genügend Credits vorhanden sind, False sonst
    """
    user = User.query.get(user_id)
    if not user:
        return False
    
    return user.credits >= required_credits

def track_token_usage(user_id, session_id, model, input_tokens, output_tokens, endpoint, function_name=None, cached=False):
    """
    Verfolgt die Token-Nutzung eines Benutzers.
    
    Args:
        user_id (str): Die ID des Benutzers
        session_id (str): Die ID der Session
        model (str): Das verwendete Modell
        input_tokens (int): Die Anzahl der Input-Token
        output_tokens (int): Die Anzahl der Output-Token
        endpoint (str): Der verwendete API-Endpunkt
        function_name (str, optional): Der Name der aufrufenden Funktion
        cached (bool, optional): Ob die Anfrage aus dem Cache bedient wurde
        
    Returns:
        dict: Details zur Token-Nutzung
    """
    # Credits basierend auf Token berechnen
    credit_cost = token_to_credits(model, input_tokens, output_tokens)
    
    # Wenn die Anfrage nicht aus dem Cache bedient wurde, ziehe Credits ab
    if not cached and user_id:
        deduct_credits(user_id, credit_cost, f"Token-Nutzung ({model}, {input_tokens}/{output_tokens})")
    
    # Token-Nutzung in der Datenbank speichern
    try:
        token_usage = TokenUsage(
            id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
            timestamp=datetime.utcnow(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=credit_cost,
            endpoint=endpoint,
            function_name=function_name,
            cached=cached,
            request_metadata={
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens
            }
        )
        db.session.add(token_usage)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Fehler beim Speichern der Token-Nutzung: {str(e)}")
    
    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "credit_cost": credit_cost,
        "cached": cached
    } 