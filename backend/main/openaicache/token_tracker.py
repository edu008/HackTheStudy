"""
Token-Tracking für OpenAI-API-Aufrufe.
Wrapper für die zentrale Implementierung in core/openai_integration.py.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional, Union

# Importiere Funktionalität aus core/openai_integration (zentrale Implementierung)
from core.openai_integration import (calculate_token_cost,
                                     check_credits_available, deduct_credits,
                                     get_usage_stats, get_user_credits,
                                     track_token_usage as core_track_token_usage,
                                     count_tokens)

# Logger konfigurieren
logger = logging.getLogger(__name__)

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
        return core_track_token_usage(
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

# Für einfacheren Import und Abwärtskompatibilität
track_token_usage = core_track_token_usage

# Alias für track_token_usage für Abwärtskompatibilität
update_token_usage = track_token_usage
