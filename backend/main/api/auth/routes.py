"""
Routen für die Authentifizierungsschnittstelle.
Definiert die HTTP-Endpunkte für die Benutzerauthentifizierung und -verwaltung.
"""

import logging
import uuid

from core.models import Payment, User, UserActivity, db
from flask import current_app, jsonify, redirect, request, url_for
from flask_jwt_extended import get_jwt_identity, jwt_required

from . import auth_bp
from .controllers import (create_user_activity, handle_oauth_callback,
                          process_payment)
from .oauth_providers import get_oauth_client, get_user_info, validate_provider
from .token_auth import token_required

# Logger konfigurieren
logger = logging.getLogger(__name__)


def register_routes():
    """Registriert alle Routen für die Authentifizierung."""

    @auth_bp.route('/login', methods=['POST', 'OPTIONS'])
    def login_with_code():
        """Login mit OAuth-Code vom Frontend."""
        # Bei OPTIONS-Anfragen sofort eine Antwort zurückgeben
        if request.method == 'OPTIONS':
            response = current_app.make_response("")
            return response

        # Daten aus dem Request-Body holen
        data = request.json
        provider = data.get('provider')
        code = data.get('code')

        if not provider or not code:
            return jsonify({"success": False, "error": {"code": "MISSING_PARAMETERS",
                           "message": "Provider and code are required"}}), 400

        if not validate_provider(provider):
            return jsonify({"success": False, "error": {"code": "INVALID_PROVIDER",
                           "message": "Invalid or unconfigured provider"}}), 400

        try:
            # Token über OAuth-Provider abrufen
            oauth_client = get_oauth_client(provider)
            if not oauth_client:
                return jsonify({"success": False, "error": {"code": "PROVIDER_ERROR",
                               "message": f"Error creating OAuth client for {provider}"}}), 500

            # Hier verwenden wir den vom Frontend gesendeten Code, um ein Token zu erhalten
            token = oauth_client.authorize_access_token(code=code)
            user_info = get_user_info(provider, token.get('access_token'))

            if not user_info:
                return jsonify({"success": False, "error": {"code": "USER_INFO_FAILED",
                               "message": "Failed to get user info"}}), 400

            return handle_oauth_callback(provider, user_info, token)

        except Exception as e:
            logger.error("Fehler beim Login mit %s: %s", provider, str(e))
            return jsonify({"success": False, "error": {"code": "LOGIN_FAILED", "message": str(e)}}), 500

    @auth_bp.route('/login/<provider>', methods=['GET', 'OPTIONS'])
    def login(provider):
        """Generische Login-Route für alle OAuth-Provider."""
        if request.method == 'OPTIONS':
            response = current_app.make_response("")
            return response

        if not validate_provider(provider):
            return jsonify({"success": False, "error": {"code": "INVALID_PROVIDER",
                           "message": "Invalid or unconfigured provider"}}), 400

        try:
            # OAuth-Client erstellen und Redirect vorbereiten
            oauth_client = get_oauth_client(provider)
            if not oauth_client:
                return jsonify({"success": False, "error": {"code": "PROVIDER_ERROR",
                               "message": f"Error creating OAuth client for {provider}"}}), 500

            # Use the exact redirect URI that matches the OAuth app configuration
            # Erzwinge HTTPS für die Redirect-URI
            redirect_uri = url_for('api.auth.callback', provider=provider, _external=True, _scheme='https')
            logger.info("Redirect URI für %s: %s", provider, redirect_uri)
            return oauth_client.authorize_redirect(redirect_uri)
        except Exception as e:
            logger.error("Fehler beim Redirect zu %s: %s", provider, str(e))
            return jsonify({"success": False, "error": {"code": "REDIRECT_FAILED", "message": str(e)}}), 500

    @auth_bp.route('/callback/<provider>', methods=['GET', 'OPTIONS'])
    def callback(provider):
        """Generische Callback-Route für alle OAuth-Provider."""
        if request.method == 'OPTIONS':
            response = current_app.make_response("")
            return response

        if not validate_provider(provider):
            return jsonify({"success": False, "error": {"code": "INVALID_PROVIDER",
                           "message": "Invalid or unconfigured provider"}}), 400

        try:
            # OAuth-Client erstellen und Token abrufen
            oauth_client = get_oauth_client(provider)
            if not oauth_client:
                return jsonify({"success": False, "error": {"code": "PROVIDER_ERROR",
                               "message": f"Error creating OAuth client for {provider}"}}), 500

            token = oauth_client.authorize_access_token()
            user_info = get_user_info(provider, token.get('access_token'))

            if not user_info:
                return jsonify({"success": False, "error": {"code": "USER_INFO_FAILED",
                               "message": "Failed to get user info"}}), 400

            return handle_oauth_callback(provider, user_info, token)
        except Exception as e:
            logger.error("Fehler bei %s OAuth Callback: %s", provider, str(e))
            return jsonify({
                'error': f'{provider.capitalize()} authentication failed',
                'message': str(e)
            }), 500

    @auth_bp.route('/user', methods=['GET', 'OPTIONS'])
    @jwt_required()
    def get_user():
        """Gibt Informationen zum aktuellen Benutzer zurück."""
        # Bei OPTIONS-Anfragen sofort eine Antwort zurückgeben
        if request.method == 'OPTIONS':
            response = current_app.make_response("")
            return response

        try:
            user_id = get_jwt_identity()
            user = User.query.get(user_id)

            if not user:
                return jsonify({
                    "success": False, 
                    "error": {"code": "USER_NOT_FOUND", "message": "User not found"}
                }), 404

            return jsonify({
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "avatar": user.avatar,
                "credits": user.credits
            }), 200
        except Exception as e:
            logger.error("Fehler beim Abrufen des Benutzers: %s", str(e))
            return jsonify({"success": False, "error": {"code": "USER_FETCH_FAILED", "message": str(e)}}), 500

    @auth_bp.route('/activity', methods=['GET', 'OPTIONS'])
    @token_required
    def get_user_activity():
        """Gibt die letzten Aktivitäten des Benutzers zurück."""
        if request.method == 'OPTIONS':
            response = current_app.make_response("")
            return response

        activities = UserActivity.query.filter_by(
            user_id=request.user_id).order_by(
            UserActivity.timestamp.desc()).limit(20).all()
        return jsonify({
            "success": True,
            "data": {
                "activities": [{
                    "id": a.id,
                    "type": a.activity_type,
                    "title": a.title,
                    "main_topic": a.main_topic,
                    "subtopics": a.subtopics,
                    "session_id": a.session_id,
                    "details": a.details,
                    "timestamp": a.timestamp.isoformat()
                } for a in activities]
            }
        }), 200

    @auth_bp.route('/activity', methods=['POST', 'OPTIONS'])
    @token_required
    def create_user_activity_route():
        """Erstellt eine neue Benutzeraktivität."""
        if request.method == 'OPTIONS':
            response = current_app.make_response("")
            return response

        data = request.json
        if not data or 'type' not in data or 'title' not in data:
            return jsonify({"success": False, "error": {"code": "INVALID_REQUEST", "message": "Invalid request"}}), 400

        try:
            activity = create_user_activity(
                user_id=request.user_id,
                activity_type=data['type'],
                title=data['title'],
                main_topic=data.get('main_topic'),
                subtopics=data.get('subtopics'),
                session_id=data.get('session_id'),
                details=data.get('details')
            )

            return jsonify({
                "success": True,
                "data": {
                    "id": activity.id,
                    "type": activity.activity_type,
                    "title": activity.title,
                    "main_topic": activity.main_topic,
                    "subtopics": activity.subtopics,
                    "session_id": activity.session_id,
                    "details": activity.details,
                    "timestamp": activity.timestamp.isoformat()
                }
            }), 201
        except Exception as e:
            logger.error("Fehler beim Erstellen der Benutzeraktivität: %s", str(e))
            return jsonify({"success": False, "error": {"code": "ACTIVITY_CREATION_FAILED", "message": str(e)}}), 500

    @auth_bp.route('/payment', methods=['POST', 'OPTIONS'])
    @token_required
    def create_payment():
        """Erstellt eine neue Zahlung und aktualisiert das Benutzerguthaben."""
        if request.method == 'OPTIONS':
            response = current_app.make_response("")
            return response

        data = request.json
        if not data or 'amount' not in data or 'credits' not in data or 'payment_method' not in data:
            return jsonify({"success": False, "error": {"code": "INVALID_REQUEST", "message": "Invalid request"}}), 400

        try:
            payment, user = process_payment(
                user_id=request.user_id,
                amount=data['amount'],
                credit_amount=data['credits'],
                payment_method=data['payment_method']
            )

            return jsonify({
                "success": True,
                "data": {
                    "payment": {
                        "id": payment.id,
                        "amount": payment.amount,
                        "credits": payment.credits,
                        "payment_method": payment.payment_method,
                        "transaction_id": payment.transaction_id,
                        "status": payment.status,
                        "created_at": payment.created_at.isoformat()
                    },
                    "user": {"id": user.id, "credits": user.credits}
                }
            }), 201
        except Exception as e:
            logger.error("Fehler bei der Zahlungsverarbeitung: %s", str(e))
            return jsonify({"success": False, "error": {"code": "PAYMENT_PROCESSING_FAILED", "message": str(e)}}), 500

    @auth_bp.route('/payments', methods=['GET', 'OPTIONS'])
    @token_required
    def get_payments():
        """Gibt alle Zahlungen des Benutzers zurück."""
        if request.method == 'OPTIONS':
            response = current_app.make_response("")
            return response

        payments = Payment.query.filter_by(user_id=request.user_id).order_by(Payment.created_at.desc()).all()
        return jsonify({
            "success": True,
            "data": {
                "payments": [
                    {
                        "id": p.id, 
                        "amount": p.amount, 
                        "credits": p.credits, 
                        "payment_method": p.payment_method, 
                        "transaction_id": p.transaction_id, 
                        "status": p.status, 
                        "created_at": p.created_at.isoformat()
                    } for p in payments
                ]
            }
        }), 200

    # Rückgabe zur Bestätigung, dass alle Routen registriert wurden
    return "Auth routes registered"
