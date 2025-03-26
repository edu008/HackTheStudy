from flask import Blueprint, request, jsonify, redirect, url_for, current_app, g
import os
import requests
import uuid
from authlib.integrations.flask_client import OAuth
from datetime import datetime, timedelta
import functools
from . import api_bp
from core.models import db, User, OAuthToken, UserActivity, Payment
from functools import wraps
import logging
from uuid import uuid4
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required, decode_token

# Blueprint erstellen und zentrale CORS-Konfiguration verwenden
auth_bp = Blueprint('auth', __name__)

logger = logging.getLogger(__name__)

# OAuth-Objekt für die spätere Initialisierung
oauth = OAuth()

# Unterstützte OAuth-Provider
SUPPORTED_PROVIDERS = ['google', 'github']

def setup_oauth(app):
    """Initialisiert die OAuth-Konfiguration für die App."""
    # Prüfe zuerst, ob die OAuth-Konfiguration vorhanden ist
    google_client_id = os.getenv('GOOGLE_CLIENT_ID')
    google_client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    github_client_id = os.getenv('GITHUB_CLIENT_ID')
    github_client_secret = os.getenv('GITHUB_CLIENT_SECRET')
    
    # Initialisiere OAuth mit der App
    oauth.init_app(app)
    
    # Stelle sicher, dass oauth im App-Kontext verfügbar ist
    app.extensions['oauth'] = oauth
    
    # Registriere OAuth-Provider nur, wenn die notwendigen Schlüssel vorhanden sind
    if google_client_id and google_client_secret:
        oauth.register(
            name='google',
            client_id=google_client_id.strip(),
            client_secret=google_client_secret.strip(),
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={
                'scope': 'openid email profile',
                'token_endpoint_auth_method': 'client_secret_post',
                'code_challenge_method': None
            }
        )
        logger.info("Google OAuth konfiguriert.")
    else:
        logger.warning("WARNUNG: Google OAuth nicht konfiguriert (fehlende Umgebungsvariablen).")
    
    if github_client_id and github_client_secret:
        oauth.register(
            name='github',
            client_id=github_client_id.strip(),
            client_secret=github_client_secret.strip(),
            authorize_url='https://github.com/login/oauth/authorize',
            authorize_params=None,
            access_token_url='https://github.com/login/oauth/access_token',
            access_token_params=None,
            refresh_token_url=None,
            client_kwargs={'scope': 'user:email'},
        )
        logger.info("GitHub OAuth konfiguriert.")
    else:
        logger.warning("WARNUNG: GitHub OAuth nicht konfiguriert (fehlende Umgebungsvariablen).")

def token_required(f):
    """
    Dekorator, der überprüft, ob ein gültiges JWT-Token in den Anfrage-Headern übergeben wurde.
    Verwendet flask_jwt_extended für die Token-Validierung.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Bei OPTIONS-Anfragen sofort eine Antwort zurückgeben
        if request.method == 'OPTIONS':
            return jsonify({"success": True})
        
        # Prüfe, ob der Authorization-Header im Request vorhanden ist
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"success": False, "error": {"code": "MISSING_TOKEN", "message": "Missing authorization token"}}), 401
        
        # Extrahiere das Token aus dem Authorization-Header
        token = auth_header.replace('Bearer ', '')
        
        try:
            # Verwende flask_jwt_extended für Token-Validierung
            # Der JWT-Secret-Key wird aus der App-Konfiguration gelesen
            # Validiere Token und hole user_id
            user_id = get_jwt_identity()
            
            # Füge den Benutzer zur Flask-g hinzu, um ihn in anderen Funktionen zu verwenden
            user = User.query.get(user_id)
            if not user:
                return jsonify({"success": False, "error": {"code": "INVALID_TOKEN", "message": "Invalid or expired token"}}), 401
            
            # Speichere den Benutzer in Flask-g und in request für einfachen Zugriff
            g.user = user
            request.user = user
            request.user_id = user_id
            
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Fehler bei Token-Validierung: {str(e)}")
            return jsonify({"success": False, "error": {"code": "INVALID_TOKEN", "message": "Invalid or expired token"}}), 401
    
    return decorated

def validate_provider(provider):
    """Validiert, ob der angegebene OAuth-Provider unterstützt wird."""
    if provider not in SUPPORTED_PROVIDERS:
        return False
    # Prüfe, ob der Provider konfiguriert ist
    if not hasattr(oauth, provider):
        logger.error(f"OAuth Provider {provider} nicht konfiguriert")
        return False
    return True

def get_user_info(provider, token):
    """Ruft Benutzerinformationen vom OAuth-Provider ab."""
    try:
        if provider == 'google':
            resp = requests.get('https://www.googleapis.com/oauth2/v1/userinfo', headers={'Authorization': f'Bearer {token}'})
            if resp.status_code == 200:
                user_info = resp.json()
                return {'provider': 'google', 'id': user_info['id'], 'email': user_info['email'], 'name': user_info.get('name', user_info['email'].split('@')[0]), 'avatar': user_info.get('picture')}
        elif provider == 'github':
            resp = requests.get('https://api.github.com/user', headers={'Authorization': f'token {token}'})
            if resp.status_code == 200:
                user_info = resp.json()
                email_resp = requests.get('https://api.github.com/user/emails', headers={'Authorization': f'token {token}'})
                email = user_info.get('email')
                if email_resp.status_code == 200:
                    emails = email_resp.json()
                    primary_email = next((e['email'] for e in emails if e['primary']), None)
                    if primary_email:
                        email = primary_email
                name = user_info.get('name') or user_info['login']
                return {'provider': 'github', 'id': str(user_info['id']), 'email': email or f"{user_info['login']}@github.com", 'name': name, 'avatar': user_info.get('avatar_url')}
    except Exception as e:
        logger.error(f"Fehler beim Abrufen von Benutzerinformationen von {provider}: {str(e)}")
    return None

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
        return jsonify({"success": False, "error": {"code": "MISSING_PARAMETERS", "message": "Provider and code are required"}}), 400
    
    if not validate_provider(provider):
        return jsonify({"success": False, "error": {"code": "INVALID_PROVIDER", "message": "Invalid or unconfigured provider"}}), 400
    
    try:
        # Token über OAuth-Provider abrufen
        oauth_client = oauth.create_client(provider)
        if not oauth_client:
            return jsonify({"success": False, "error": {"code": "PROVIDER_ERROR", "message": f"Error creating OAuth client for {provider}"}}), 500
        
        # Hier verwenden wir den vom Frontend gesendeten Code, um ein Token zu erhalten
        token = oauth_client.authorize_access_token(code=code)
        user_info = get_user_info(provider, token.get('access_token'))
        
        if not user_info:
            return jsonify({"success": False, "error": {"code": "USER_INFO_FAILED", "message": "Failed to get user info"}}), 400
        
        return handle_oauth_callback(provider, user_info, token)
        
    except Exception as e:
        logger.error(f"Fehler beim Login mit {provider}: {str(e)}")
        return jsonify({"success": False, "error": {"code": "LOGIN_FAILED", "message": str(e)}}), 500

@auth_bp.route('/login/<provider>', methods=['GET', 'OPTIONS'])
def login(provider):
    """Generische Login-Route für alle OAuth-Provider."""
    if request.method == 'OPTIONS':
        response = current_app.make_response("")
        return response
    
    if not validate_provider(provider):
        return jsonify({"success": False, "error": {"code": "INVALID_PROVIDER", "message": "Invalid or unconfigured provider"}}), 400
    
    try:
        # OAuth-Client erstellen und Redirect vorbereiten
        oauth_client = oauth.create_client(provider)
        if not oauth_client:
            return jsonify({"success": False, "error": {"code": "PROVIDER_ERROR", "message": f"Error creating OAuth client for {provider}"}}), 500
        
        # Use the exact redirect URI that matches the OAuth app configuration
        redirect_uri = url_for('api.auth.callback', provider=provider, _external=True)
        return oauth_client.authorize_redirect(redirect_uri)
    except Exception as e:
        logger.error(f"Fehler beim Redirect zu {provider}: {str(e)}")
        return jsonify({"success": False, "error": {"code": "REDIRECT_FAILED", "message": str(e)}}), 500

@auth_bp.route('/callback/<provider>', methods=['GET', 'OPTIONS'])
def callback(provider):
    """Generische Callback-Route für alle OAuth-Provider."""
    if request.method == 'OPTIONS':
        response = current_app.make_response("")
        return response
    
    if not validate_provider(provider):
        return jsonify({"success": False, "error": {"code": "INVALID_PROVIDER", "message": "Invalid or unconfigured provider"}}), 400
    
    try:
        # OAuth-Client erstellen und Token abrufen
        oauth_client = oauth.create_client(provider)
        if not oauth_client:
            return jsonify({"success": False, "error": {"code": "PROVIDER_ERROR", "message": f"Error creating OAuth client for {provider}"}}), 500
        
        token = oauth_client.authorize_access_token()
        user_info = get_user_info(provider, token.get('access_token'))
        
        if not user_info:
            return jsonify({"success": False, "error": {"code": "USER_INFO_FAILED", "message": "Failed to get user info"}}), 400
        
        return handle_oauth_callback(provider, user_info, token)
    except Exception as e:
        logger.error(f"Fehler bei {provider} OAuth Callback: {str(e)}")
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
            return jsonify({"success": False, "error": {"code": "USER_NOT_FOUND", "message": "User not found"}}), 404
        
        return jsonify({
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "avatar": user.avatar,
            "credits": user.credits
        }), 200
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des Benutzers: {str(e)}")
        return jsonify({"success": False, "error": {"code": "USER_FETCH_FAILED", "message": str(e)}}), 500

@auth_bp.route('/activity', methods=['GET', 'OPTIONS'])
@token_required
def get_user_activity():
    if request.method == 'OPTIONS':
        response = current_app.make_response("")
        return response
    
    activities = UserActivity.query.filter_by(user_id=request.user_id).order_by(UserActivity.timestamp.desc()).limit(20).all()
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
def create_user_activity():
    if request.method == 'OPTIONS':
        response = current_app.make_response("")
        return response
    
    data = request.json
    if not data or 'type' not in data or 'title' not in data:
        return jsonify({"success": False, "error": {"code": "INVALID_REQUEST", "message": "Invalid request"}}), 400
    
    # Begrenze auf 5 Einträge
    existing_activities = UserActivity.query.filter_by(user_id=request.user_id).order_by(UserActivity.timestamp.asc()).all()
    if len(existing_activities) >= 5:
        oldest_activity = existing_activities[0]
        db.session.delete(oldest_activity)
        current_app.logger.info(f"Deleted oldest activity: {oldest_activity.id}")
    
    activity = UserActivity(
        user_id=request.user_id,
        activity_type=data['type'],
        title=data['title'],
        main_topic=data.get('main_topic'),
        subtopics=data.get('subtopics'),
        session_id=data.get('session_id'),
        details=data.get('details')
    )
    db.session.add(activity)
    db.session.commit()
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

@auth_bp.route('/payment', methods=['POST', 'OPTIONS'])
@token_required
def create_payment():
    if request.method == 'OPTIONS':
        response = current_app.make_response("")
        return response
    
    data = request.json
    if not data or 'amount' not in data or 'credits' not in data or 'payment_method' not in data:
        return jsonify({"success": False, "error": {"code": "INVALID_REQUEST", "message": "Invalid request"}}), 400
    
    # Begrenze auf 5 Einträge
    existing_activities = UserActivity.query.filter_by(user_id=request.user_id).order_by(UserActivity.timestamp.asc()).all()
    if len(existing_activities) >= 5:
        oldest_activity = existing_activities[0]
        db.session.delete(oldest_activity)
        current_app.logger.info(f"Deleted oldest activity: {oldest_activity.id}")
    
    payment = Payment(user_id=request.user_id, amount=data['amount'], credits=data['credits'], payment_method=data['payment_method'], transaction_id=str(uuid.uuid4()), status='completed')
    db.session.add(payment)
    user = User.query.get(request.user_id)
    user.credits += data['credits']
    activity = UserActivity(
        user_id=request.user_id,
        activity_type='payment',
        title=f"Purchased {data['credits']} credits",
        details={'amount': data['amount'], 'payment_method': data['payment_method']}
    )
    db.session.add(activity)
    db.session.commit()
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

@auth_bp.route('/payments', methods=['GET', 'OPTIONS'])
@token_required
def get_payments():
    if request.method == 'OPTIONS':
        response = current_app.make_response("")
        return response
    
    payments = Payment.query.filter_by(user_id=request.user_id).order_by(Payment.created_at.desc()).all()
    return jsonify({
        "success": True,
        "data": {
            "payments": [{"id": p.id, "amount": p.amount, "credits": p.credits, "payment_method": p.payment_method, "transaction_id": p.transaction_id, "status": p.status, "created_at": p.created_at.isoformat()} for p in payments]
        }
    }), 200

def handle_oauth_callback(provider: str, user_info: dict, token_data: dict = None):
    """Zentrale Funktion zur Verarbeitung von OAuth-Callbacks."""
    try:
        # Initialisiere existing_user mit None
        existing_user = None
        
        # Suche nach existierendem Benutzer mit OAuth-Provider und ID
        user = User.query.filter_by(oauth_provider=provider, oauth_id=user_info['id']).first()
        
        # Wenn kein Benutzer gefunden wurde, suche nach E-Mail
        if not user:
            existing_user = User.query.filter_by(email=user_info['email']).first()
            if existing_user:
                # Aktualisiere existierenden Benutzer mit OAuth-Informationen
                existing_user.oauth_provider = provider
                existing_user.oauth_id = user_info['id']
                existing_user.avatar = user_info.get('avatar')
                user = existing_user
            else:
                # Erstelle neuen Benutzer
                user = User(
                    id=str(uuid4()),
                    email=user_info['email'],
                    name=user_info['name'],
                    avatar=user_info.get('avatar'),
                    oauth_provider=provider,
                    oauth_id=user_info['id'],
                    credits=0
                )
                db.session.add(user)
        
        try:
            # Schneller Commit, um die User-ID zu erhalten
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Fehler beim Speichern des Benutzers: {str(e)}")
            raise
        
        # Speichere OAuth-Token, falls token_data vorhanden ist
        if token_data:
            # Prüfe, ob bereits ein Token für diesen Benutzer und Provider existiert
            existing_token = OAuthToken.query.filter_by(
                user_id=user.id,
                provider=provider
            ).first()
            
            # Lösche das alte Token, falls vorhanden
            if existing_token:
                db.session.delete(existing_token)
            
            # Erstelle neues Token
            oauth_token = OAuthToken(
                id=str(uuid4()),
                user_id=user.id,
                provider=provider,
                access_token=token_data.get('access_token'),
                refresh_token=token_data.get('refresh_token'),
                expires_at=datetime.utcnow() + timedelta(seconds=token_data.get('expires_in', 3600))
            )
            db.session.add(oauth_token)
        
        # Protokolliere Aktivität
        activity = UserActivity(
            id=str(uuid4()),
            user_id=user.id,
            activity_type='account',
            title='Account created' if not existing_user else f'Account linked with {provider}',
            timestamp=datetime.utcnow()
        )
        db.session.add(activity)
        
        # Speichere alle Änderungen
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Fehler beim Speichern der OAuth-Daten: {str(e)}")
            raise
        
        # Erstelle JWT-Token mit flask_jwt_extended
        token = create_access_token(identity=user.id)
        
        # Erstelle Response mit Token und User-Info
        return jsonify({
            'access_token': token,
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        logger.error(f"Fehler bei OAuth Callback Verarbeitung: {str(e)}")
        return jsonify({
            'error': 'Authentication failed',
            'message': str(e)
        }), 500