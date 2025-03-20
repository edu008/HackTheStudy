from flask import current_app, g, jsonify
from models import db, User
from functools import wraps
import math

# Kosten pro 1000 Tokens (in Credits)
GPT4_INPUT_COST_PER_1K = 10
GPT4_OUTPUT_COST_PER_1K = 30
GPT35_INPUT_COST_PER_1K = 1.5
GPT35_OUTPUT_COST_PER_1K = 2

def calculate_token_cost(input_tokens, output_tokens, model="gpt-4o"):
    """
    Berechnet die Kosten basierend auf Token-Anzahl und Modell
    Wichtig: Die Kosten sind das Doppelte der eigentlichen OpenAI-Kosten, 
    um einen Gewinn zu erzielen.
    
    Args:
        input_tokens (int): Anzahl der Input-Token
        output_tokens (int): Anzahl der Output-Token
        model (str): Das verwendete OpenAI-Modell
        
    Returns:
        int: Kosten in Credits (gerundet auf die nächste ganze Zahl)
    """
    if model.startswith("gpt-4"):
        input_cost = (input_tokens / 1000) * GPT4_INPUT_COST_PER_1K
        output_cost = (output_tokens / 1000) * GPT4_OUTPUT_COST_PER_1K
    else:  # GPT-3.5
        input_cost = (input_tokens / 1000) * GPT35_INPUT_COST_PER_1K
        output_cost = (output_tokens / 1000) * GPT35_OUTPUT_COST_PER_1K
    
    # Gesamtkosten berechnen und auf die nächste ganze Zahl aufrunden
    total_cost = math.ceil(input_cost + output_cost)
    
    # Mindestkosten von 1 Credit pro API-Aufruf
    return max(1, total_cost)

def check_credits_available(cost):
    """
    Überprüft, ob der Benutzer genügend Credits hat, ohne sie abzuziehen
    
    Args:
        cost (int): Anzahl der Credits, die benötigt werden
        
    Returns:
        bool: True, wenn genügend Credits vorhanden sind, False sonst
    """
    if not hasattr(g, 'user') or not g.user:
        return False
    
    user_id = g.user.id
    user = User.query.get(user_id)
    
    if not user:
        return False
    
    return user.credits >= cost

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

def deduct_credits(user_id, credits):
    """
    Zieht einem Benutzer Credits ab
    
    Args:
        user_id (str): Die ID des Benutzers
        credits (int): Die Anzahl der abzuziehenden Credits
        
    Returns:
        bool: True, wenn erfolgreich, False wenn nicht genügend Credits vorhanden sind
    """
    user = User.query.get(user_id)
    if not user or user.credits < credits:
        return False
    
    user.credits -= credits
    db.session.commit()
    return True 