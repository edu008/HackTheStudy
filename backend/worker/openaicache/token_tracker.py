"""
Token-Tracking für OpenAI-API-Aufrufe.
Wrapper für die zentrale Implementierung in core/openai_integration.py.
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

# Direkte Re-Exporte aus der zentralen Implementierung
from core.openai_integration import (
    calculate_token_cost,
    track_token_usage,
    check_credits_available,
    deduct_credits,
    get_user_credits,
    get_usage_stats
)

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Re-Export für die Kompatibilität
def update_token_usage(user_id=None, session_id=None, model=None, 
                      input_tokens=0, output_tokens=0, 
                      function_name=None, cached=False):
    """
    Alias für track_token_usage für Abwärtskompatibilität.
    """
    return track_token_usage(
        user_id=user_id,
        session_id=session_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        function_name=function_name,
        cached=cached
    )

# Kompatibilitäts-Klasse, die die neuen Funktionen verwendet
class TokenTracker:
    """
    Klasse für das Tracking des Token-Verbrauchs bei OpenAI-API-Aufrufen.
    Wrapper für die zentralen Funktionen.
    """
    
    @staticmethod
    def count_tokens(text_or_messages, model="gpt-4o"):
        """Wrapper für count_tokens"""
        return count_tokens(text_or_messages, model)
    
    @staticmethod
    def calculate_cost(model, input_tokens, output_tokens):
        """Wrapper für calculate_token_cost"""
        return calculate_token_cost(model, input_tokens, output_tokens)
    
    @staticmethod
    def track_usage(user_id=None, session_id=None, model=None, 
                   input_tokens=0, output_tokens=0, 
                   function_name=None, cached=False):
        """Wrapper für track_token_usage"""
        return track_token_usage(
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
        """Wrapper für check_credits_available"""
        return check_credits_available(cost, user_id)
    
    @staticmethod
    def deduct_credits(user_id, cost, session_id=None, function_name=None):
        """Wrapper für deduct_credits"""
        return deduct_credits(user_id, cost, session_id, function_name)
    
    @staticmethod
    def get_usage_stats(user_id=None, start_time=None, end_time=None):
        """Wrapper für get_usage_stats"""
        return get_usage_stats(user_id, start_time, end_time)

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