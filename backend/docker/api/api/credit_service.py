import logging
from datetime import datetime
from flask import current_app, g, jsonify
from core.models import db, User, TokenUsage
from functools import wraps
import math
import uuid
from api.token_tracking import deduct_credits, calculate_token_cost, check_credits_available, track_token_usage

def check_and_deduct_credits(cost):
    """
    Decorator zum Überprüfen und Abziehen von Credits
    
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
    Decorator zum Überprüfen und Abziehen von dynamisch berechneten Credits
    Die Kostenfunktion wird verwendet, um die Kosten basierend auf der Anfrage zu berechnen
    
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
    Ruft die aktuellen Credits eines Benutzers ab
    
    Args:
        user_id (str): Die ID des Benutzers
        
    Returns:
        int: Die Anzahl der Credits des Benutzers
    """
    user = User.query.get(user_id)
    if not user:
        return 0
    return user.credits

def add_credits(user_id, credits):
    """
    Fügt einem Benutzer Credits hinzu
    
    Args:
        user_id (str): Die ID des Benutzers
        credits (int): Die Anzahl der hinzuzufügenden Credits
        
    Returns:
        bool: True, wenn erfolgreich, False sonst
    """
    user = User.query.get(user_id)
    if not user:
        return False
    
    user.credits += credits
    db.session.commit()
    return True 