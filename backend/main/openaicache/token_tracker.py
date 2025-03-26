"""
Token-Tracking für OpenAI-API-Aufrufe.
Ermöglicht die Verfolgung des Token-Verbrauchs und der Kosten.
"""

import logging
import time
from typing import Dict, Any, Optional, Union
from datetime import datetime

# Importiere vorhandene Funktionalität aus dem token_tracking-Modul
from api.token_tracking import (
    count_tokens,
    calculate_token_cost as api_calculate_token_cost,
    track_token_usage as api_track_token_usage,
    deduct_credits,
    check_credits_available
)

# Logger konfigurieren
logger = logging.getLogger(__name__)

class TokenTracker:
    """
    Klasse für das Tracking des Token-Verbrauchs bei OpenAI-API-Aufrufen.
    """
    
    @staticmethod
    def count_tokens(text_or_messages, model="gpt-4o"):
        """
        Zählt die Tokens in einem Text oder einer Liste von Nachrichten.
        
        Args:
            text_or_messages: Text oder Nachrichten
            model: Modellname für die Token-Zählung
            
        Returns:
            int: Anzahl der Tokens
        """
        return count_tokens(text_or_messages, model)
    
    @staticmethod
    def calculate_cost(model, input_tokens, output_tokens):
        """
        Berechnet die Kosten für eine API-Anfrage.
        
        Args:
            model: Modellname
            input_tokens: Anzahl der Eingabe-Tokens
            output_tokens: Anzahl der Ausgabe-Tokens
            
        Returns:
            float: Kosten in USD
        """
        return api_calculate_token_cost(model, input_tokens, output_tokens)
    
    @staticmethod
    def track_usage(user_id=None, session_id=None, model=None, 
                    input_tokens=0, output_tokens=0, 
                    function_name=None, cached=False):
        """
        Verfolgt die Token-Nutzung für eine API-Anfrage.
        
        Args:
            user_id: Benutzer-ID
            session_id: Sitzungs-ID
            model: Modellname
            input_tokens: Anzahl der Eingabe-Tokens
            output_tokens: Anzahl der Ausgabe-Tokens
            function_name: Name der aufrufenden Funktion
            cached: Ob die Antwort aus dem Cache kam
            
        Returns:
            bool: Erfolg des Trackings
        """
        return api_track_token_usage(
            user_id=user_id,
            session_id=session_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            function_name=function_name,
            cached=cached
        )
    
    @staticmethod
    def check_credits(cost, user_id):
        """
        Prüft, ob ein Benutzer genügend Credits hat.
        
        Args:
            cost: Benötigte Credits
            user_id: Benutzer-ID
            
        Returns:
            bool: True, wenn genügend Credits vorhanden sind
        """
        return check_credits_available(cost, user_id)
    
    @staticmethod
    def deduct_credits(user_id, cost, session_id=None, function_name=None):
        """
        Zieht Credits von einem Benutzer ab.
        
        Args:
            user_id: Benutzer-ID
            cost: Abzuziehende Credits
            session_id: Sitzungs-ID
            function_name: Name der aufrufenden Funktion
            
        Returns:
            bool: Erfolg des Abzugs
        """
        return deduct_credits(user_id, cost, session_id, function_name)
    
    @staticmethod
    def get_usage_stats(user_id=None, start_time=None, end_time=None):
        """
        Gibt Nutzungsstatistiken zurück.
        
        Args:
            user_id: Benutzer-ID (optional)
            start_time: Startzeit (optional)
            end_time: Endzeit (optional)
            
        Returns:
            Dict: Nutzungsstatistiken
        """
        from core.models import TokenUsage, db
        
        try:
            query = db.session.query(TokenUsage)
            
            if user_id:
                query = query.filter(TokenUsage.user_id == user_id)
            
            if start_time:
                query = query.filter(TokenUsage.timestamp >= start_time)
            
            if end_time:
                query = query.filter(TokenUsage.timestamp <= end_time)
            
            # Gesamtnutzung
            total_input_tokens = 0
            total_output_tokens = 0
            total_cost = 0
            cached_count = 0
            model_stats = {}
            
            for usage in query.all():
                total_input_tokens += usage.input_tokens
                total_output_tokens += usage.output_tokens
                total_cost += usage.cost
                
                if usage.cached:
                    cached_count += 1
                
                model_name = usage.model
                if model_name not in model_stats:
                    model_stats[model_name] = {
                        "count": 0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cost": 0
                    }
                
                model_stats[model_name]["count"] += 1
                model_stats[model_name]["input_tokens"] += usage.input_tokens
                model_stats[model_name]["output_tokens"] += usage.output_tokens
                model_stats[model_name]["cost"] += usage.cost
            
            return {
                "total_requests": query.count(),
                "cached_requests": cached_count,
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
                "total_cost": round(total_cost, 4),
                "model_stats": model_stats
            }
            
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Nutzungsstatistiken: {e}")
            return {
                "error": str(e),
                "total_requests": 0
            }

# Exportiere Funktionen für direkten Import
def calculate_token_cost(model, input_tokens, output_tokens):
    """Wrapper um TokenTracker.calculate_cost"""
    return TokenTracker.calculate_cost(model, input_tokens, output_tokens)

def track_token_usage(user_id=None, session_id=None, model=None, 
                     input_tokens=0, output_tokens=0, 
                     function_name=None, cached=False):
    """Wrapper um TokenTracker.track_usage"""
    return TokenTracker.track_usage(
        user_id=user_id,
        session_id=session_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        function_name=function_name,
        cached=cached
    )

def update_token_usage(user_id=None, session_id=None, model=None, 
                      input_tokens=0, output_tokens=0, 
                      function_name=None, cached=False):
    """Alias für track_token_usage für Abwärtskompatibilität"""
    return track_token_usage(
        user_id=user_id,
        session_id=session_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        function_name=function_name,
        cached=cached
    ) 