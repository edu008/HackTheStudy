"""
Routenregistrierung für das Finanzmodul.
Definiert die HTTP-Endpunkte für die Zahlungs- und Kreditfunktionen.
"""

import logging

from api.auth.token_auth import token_required
from flask import current_app, make_response, request

from . import finance_bp
from .controllers import (get_payment_history, get_token_usage_stats,
                          get_user_credit_info)
from .payment_processing import (create_checkout_session, payment_success,
                                 stripe_webhook)

# Logger konfigurieren
logger = logging.getLogger(__name__)


def register_routes():
    """Registriert alle Routen für das Finanzmodul."""

    # Zahlungsrouten
    @finance_bp.route('/create-checkout-session', methods=['POST', 'OPTIONS'])
    @token_required
    def create_checkout_session_route():
        if request.method == 'OPTIONS':
            return make_response("")
        return create_checkout_session()

    @finance_bp.route('/webhook', methods=['POST', 'OPTIONS'])
    def stripe_webhook_route():
        if request.method == 'OPTIONS':
            return make_response("")
        return stripe_webhook()

    @finance_bp.route('/payment-success', methods=['GET', 'OPTIONS'])
    @token_required
    def payment_success_route():
        if request.method == 'OPTIONS':
            return make_response("")
        return payment_success()

    # Kreditinformationsrouten
    @finance_bp.route('/credits', methods=['GET', 'OPTIONS'])
    @token_required
    def get_credits_route():
        if request.method == 'OPTIONS':
            return make_response("")
        return get_user_credit_info()

    @finance_bp.route('/payment-history', methods=['GET', 'OPTIONS'])
    @token_required
    def payment_history_route():
        if request.method == 'OPTIONS':
            return make_response("")
        return get_payment_history()

    # Token-Nutzungsrouten
    @finance_bp.route('/token-usage', methods=['GET', 'OPTIONS'])
    @token_required
    def token_usage_route():
        if request.method == 'OPTIONS':
            return make_response("")
        time_range = request.args.get('time_range', 'month')
        return get_token_usage_stats(time_range)

    logger.info("Finanz-Routen erfolgreich registriert")

    return "Finance routes registered"
