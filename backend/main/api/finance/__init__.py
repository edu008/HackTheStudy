"""
Finanzmodul für den API-Container.
Enthält Funktionen für Zahlungen, Kreditverwaltung und Abrechnungen.
"""

import logging

from flask import Blueprint

from .constants import CREDITS, PRICES, calculate_credits
from .controllers import get_payment_history, get_user_credit_info
from .credit_management import (add_credits, check_and_deduct_credits,
                                check_and_deduct_dynamic_credits,
                                deduct_credits, get_user_credits)
from .payment_processing import (create_checkout_session, payment_success,
                                 stripe_webhook)
from .routes import register_routes

# Blueprint erstellen
finance_bp = Blueprint('finance', __name__)

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Lade alle Untermodule

# Registriere alle Routen
register_routes()

# Exportiere wichtige Komponenten
__all__ = [
    'finance_bp',
    'PRICES',
    'CREDITS',
    'calculate_credits',
    'check_and_deduct_credits',
    'check_and_deduct_dynamic_credits',
    'get_user_credits',
    'add_credits',
    'deduct_credits'
]
