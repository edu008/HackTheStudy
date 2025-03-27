"""
Finanzmodul für den API-Container.
Enthält Funktionen für Zahlungen, Kreditverwaltung und Abrechnungen.
"""

import logging
from flask import Blueprint

# Blueprint erstellen
finance_bp = Blueprint('finance', __name__)

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Lade alle Untermodule
from .constants import PRICES, CREDITS, calculate_credits
from .credit_management import (
    check_and_deduct_credits, check_and_deduct_dynamic_credits,
    get_user_credits, add_credits, deduct_credits
)
from .payment_processing import create_checkout_session, stripe_webhook, payment_success
from .controllers import get_user_credit_info, get_payment_history
from .routes import register_routes

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