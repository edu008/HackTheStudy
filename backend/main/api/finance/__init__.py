"""
Finanzmodul für den API-Container.
Enthält Funktionen für Zahlungen, Kreditverwaltung und Abrechnungen.
"""

import logging

from flask import Blueprint

# Blueprint erstellen - MUSS vor allen anderen Importen geschehen, um zirkuläre Importe zu vermeiden
finance_bp = Blueprint('finance', __name__)

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Jetzt können wir die restlichen Module importieren
from .constants import CREDITS, PRICES, calculate_credits
from .controllers import get_payment_history, get_user_credit_info
from .credit_management import (add_credits, check_and_deduct_credits,
                                check_and_deduct_dynamic_credits,
                                deduct_credits, get_user_credits)
from .payment_processing import (create_checkout_session, payment_success,
                                 stripe_webhook)

# Register-Routes-Funktion importieren und mit Blueprint aufrufen
from .routes import register_routes
register_routes(finance_bp)

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
