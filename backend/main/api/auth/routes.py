"""
Routen für die Authentifizierungsschnittstelle.
Definiert die HTTP-Endpunkte für die Benutzerauthentifizierung und -verwaltung.
"""

import logging
import uuid
import requests
from urllib.parse import urlencode
from datetime import datetime

from core.models import Payment, User, UserActivity, db
from flask import current_app, jsonify, redirect, request, url_for, Response
from flask_jwt_extended import get_jwt_identity, jwt_required

from . import auth_bp
from .controllers import (create_user_activity, handle_oauth_callback,
                          process_payment)
from .oauth_providers import get_oauth_client, get_user_info, validate_provider, get_authorization_url
from .token_auth import token_required, handle_token_refresh
from core.redis_client import get_redis_client

# Logger konfigurieren
logger = logging.getLogger(__name__)


def get_token(provider, code):
    """
    OAuth-Token vom Provider mit dem Authorization-Code abrufen.
    
    Args:
        provider (str): Der OAuth-Provider (z.B. 'github', 'google')
        code (str): Der Authorization-Code vom Provider
        
    Returns:
        str: Das Access-Token oder None bei Fehler
    """
    try:
        oauth_client = get_oauth_client(provider)
        if not oauth_client:
            logger.error(f"Kein OAuth-Client für Provider {provider} gefunden")
            return None
            
        # Redirect URI muss genau mit der in der OAuth-App-Konfiguration übereinstimmen
        redirect_uri = url_for('api.auth.callback', provider=provider, _external=True, _scheme='http')
        
        # Parameter für Token-Request
        token_params = {
            'client_id': oauth_client['client_id'],
            'client_secret': oauth_client['client_secret'],
            'code': code,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }
        
        # Token-Endpunkt vom Provider
        token_url = oauth_client['token_url']
        
        # Token anfordern
        response = requests.post(token_url, data=token_params, headers={
            'Accept': 'application/json'
        })
        
        # Antwort überprüfen und Token extrahieren
        if response.status_code == 200:
            token_data = response.json()
            # Bei den meisten Providern wird das Token als 'access_token' zurückgegeben
            return token_data.get('access_token')
        else:
            logger.error(f"Fehler beim Token-Request: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des Tokens von {provider}: {str(e)}")
        return None


def register_routes(bp):
    """Registriert alle Routen für die Authentifizierung am übergebenen Blueprint."""

    @bp.route('/login', methods=['POST', 'OPTIONS'])
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

            # Token über unsere manuelle Funktion bekommen statt über oauth_client.authorize_access_token()
            token = get_token(provider, code)
            if not token:
                return jsonify({"success": False, "error": {"code": "TOKEN_ERROR",
                              "message": "Failed to get token"}}), 400
                               
            user_info = get_user_info(provider, token)

            if not user_info:
                return jsonify({"success": False, "error": {"code": "USER_INFO_FAILED",
                               "message": "Failed to get user info"}}), 400

            return handle_oauth_callback(provider, user_info, {"access_token": token})

        except Exception as e:
            logger.error("Fehler beim Login mit %s: %s", provider, str(e))
            return jsonify({"success": False, "error": {"code": "LOGIN_FAILED", "message": str(e)}}), 500

    @bp.route('/login/<provider>', methods=['GET', 'OPTIONS'])
    def login(provider):
        """Generische Login-Route für alle OAuth-Provider."""
        if request.method == 'OPTIONS':
            response = current_app.make_response("")
            return response

        if not validate_provider(provider):
            return jsonify({"success": False, "error": {"code": "INVALID_PROVIDER",
                           "message": "Invalid or unconfigured provider"}}), 400

        try:
            # OAuth-Client erstellen
            oauth_client = get_oauth_client(provider)
            if not oauth_client:
                return jsonify({"success": False, "error": {"code": "PROVIDER_ERROR",
                               "message": f"Error creating OAuth client for {provider}"}}), 500

            # Use the exact redirect URI that matches the OAuth app configuration
            # Verwende HTTP statt HTTPS für lokale Entwicklung
            redirect_uri = url_for('api.auth.callback', provider=provider, _external=True, _scheme='http')
            logger.info("Redirect URI für %s: %s", provider, redirect_uri)
            
            # Anstatt oauth_client.authorize_redirect aufzurufen, erstellen wir die URL manuell
            # und leiten direkt dorthin weiter
            client_id = oauth_client['client_id']
            auth_url = oauth_client['authorize_url']
            scope = oauth_client['scope']
            
            # Parameter für die Auth-URL erstellen
            params = {
                'client_id': client_id,
                'redirect_uri': redirect_uri,
                'scope': scope,
                'response_type': 'code'
            }
            
            # URL mit Query-Parametern erstellen
            auth_redirect_url = f"{auth_url}?{urlencode(params)}"
            
            # Zum Provider weiterleiten
            return redirect(auth_redirect_url)
        except Exception as e:
            logger.error("Fehler beim Redirect zu %s: %s", provider, str(e))
            return jsonify({"success": False, "error": {"code": "REDIRECT_FAILED", "message": str(e)}}), 500

    @bp.route('/callback/<provider>', methods=['GET', 'OPTIONS'])
    def callback(provider):
        """Generische Callback-Route für alle OAuth-Provider."""
        if request.method == 'OPTIONS':
            response = current_app.make_response("")
            return response

        if not validate_provider(provider):
            return jsonify({"success": False, "error": {"code": "INVALID_PROVIDER",
                           "message": "Invalid or unconfigured provider"}}), 400

        try:
            # OAuth-Client abrufen
            oauth_client = get_oauth_client(provider)
            if not oauth_client:
                return jsonify({"success": False, "error": {"code": "PROVIDER_ERROR",
                               "message": f"Error creating OAuth client for {provider}"}}), 500

            # Code aus der Query-URL holen
            code = request.args.get('code')
            if not code:
                return jsonify({"success": False, "error": {"code": "INVALID_REQUEST",
                               "message": "Authorization code missing"}}), 400
            
            # Token über unsere manuelle Funktion bekommen statt über oauth_client.authorize_access_token()
            token = get_token(provider, code)
            if not token:
                return jsonify({"success": False, "error": {"code": "TOKEN_ERROR",
                               "message": "Failed to get token"}}), 400
                               
            user_info = get_user_info(provider, token)

            if not user_info:
                return jsonify({"success": False, "error": {"code": "USER_INFO_FAILED",
                               "message": "Failed to get user info"}}), 400

            return handle_oauth_callback(provider, user_info, {"access_token": token})
        except Exception as e:
            logger.error("Fehler bei %s OAuth Callback: %s", provider, str(e))
            return jsonify({
                'error': f'{provider.capitalize()} authentication failed',
                'message': str(e)
            }), 500

    @bp.route('/user', methods=['GET', 'OPTIONS'])
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

    @bp.route('/activity', methods=['GET', 'OPTIONS'])
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

    @bp.route('/activity', methods=['POST', 'OPTIONS'])
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

    @bp.route('/payment', methods=['POST', 'OPTIONS'])
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

    @bp.route('/payments', methods=['GET', 'OPTIONS'])
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

    @bp.route('/check-auth', methods=['GET', 'OPTIONS'])
    @jwt_required(optional=True)
    def check_auth():
        """
        Überprüft die Authentifizierung und erstellt eine neue Session, wenn der User eingeloggt ist.
        
        Returns:
            JSON-Antwort mit Authentifizierungs-Status und einer neuen Session-ID
        """
        if request.method == 'OPTIONS':
            # CORS-Preflight-Antwort
            return Response(status=200)
        
        try:
            # Überprüfe, ob ein JWT-Token vorhanden ist
            current_user_id = get_jwt_identity()
            
            if current_user_id:
                # Benutzer ist authentifiziert, importiere die Session-Erstellungsfunktion
                from api.uploads.session_management import create_or_refresh_session
                
                # Erstelle eine neue Session
                session_id = create_or_refresh_session()
                
                # Lade Benutzerinformationen
                user = User.query.get(current_user_id)
                
                if user:
                    # Verbinde die Session mit dem Benutzer
                    try:
                        # Speichere Benutzer-Session-Verknüpfung
                        redis_client = get_redis_client()
                        redis_client.hset(f"session:{session_id}:info", "user_id", current_user_id)
                        redis_client.hset(f"user:{current_user_id}:sessions", session_id, datetime.now().isoformat())
                        
                        # Rückgabe mit Benutzerinformationen
                        return jsonify({
                            "authenticated": True,
                            "user": {
                                "id": user.id,
                                "email": user.email,
                                "name": user.name
                            },
                            "session_id": session_id,
                            "message": "Authentifizierung erfolgreich, neue Session erstellt"
                        })
                    except Exception as redis_err:
                        logger.error(f"Redis-Fehler bei der Session-Verknüpfung: {str(redis_err)}")
                
                # Falls kein Benutzer gefunden wurde oder Redis-Fehler
                return jsonify({
                    "authenticated": True,
                    "session_id": session_id,
                    "message": "Authentifizierung erfolgreich, neue Session erstellt"
                })
            else:
                # Benutzer ist nicht authentifiziert
                return jsonify({
                    "authenticated": False,
                    "message": "Nicht authentifiziert"
                })
            
        except Exception as e:
            logger.error(f"Fehler bei der Authentifizierungsüberprüfung: {str(e)}")
            return jsonify({
                "authenticated": False,
                "error": {
                    "code": "AUTH_CHECK_ERROR",
                    "message": f"Fehler bei der Authentifizierungsüberprüfung: {str(e)}"
                }
            }), 500

    @bp.route('/refresh', methods=['POST', 'OPTIONS'])
    def refresh_token():
        """Erneuert das Access Token mittels eines gültigen Refresh Tokens."""
        # OPTIONS Preflight
        if request.method == 'OPTIONS':
             return jsonify({}), 200
        return handle_token_refresh()

    # Verwende den Standard-Logger statt current_app.logger
    logger.info(f"Authentifizierungs-Routen am Blueprint '{bp.name}' registriert.")
    return "Auth routes registered"
