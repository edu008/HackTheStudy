from flask import Blueprint, request, jsonify, redirect, url_for, current_app, g
import os
import requests
import uuid
from authlib.integrations.flask_client import OAuth
from datetime import datetime, timedelta
import jwt
import functools
from . import api_bp
from core.models import db, User, OAuthToken, UserActivity, Payment
from functools import wraps
import logging
from uuid import uuid4

# Blueprint erstellen und zentrale CORS-Konfiguration verwenden
auth_bp = Blueprint('auth', __name__)

logger = logging.getLogger(__name__)

# OAuth-Objekt für die spätere Initialisierung
oauth = OAuth()

def setup_oauth(app):
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
            access_token_url='https://github.com/login/oauth/access_token',
            access_token_params=None,
            authorize_url='https://github.com/login/oauth/authorize',
            authorize_params=None,
            api_base_url='https://api.github.com/',
            client_kwargs={
                'scope': 'user:email',
                'token_endpoint_auth_method': 'client_secret_post'
            }
        )
        logger.info("GitHub OAuth konfiguriert.")
    else:
        logger.warning("WARNUNG: GitHub OAuth nicht konfiguriert (fehlende Umgebungsvariablen).")
    
    return oauth

def get_user_info(provider, token):
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
    return None

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # OPTIONS-Anfragen immer erlauben, ohne Token zu überprüfen
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)
        
        token = None
        auth_header = request.headers.get('Authorization')
        
        if auth_header:
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        else:
            # Versuche den Token aus dem Cookie zu bekommen, falls vorhanden
            token = request.cookies.get('token')
        
        if not token:
            # Mit CORS-Headern antworten, auch bei Authentifizierungsfehlern
            response = jsonify({
                'success': False,
                'error': {
                    'code': 'NO_TOKEN',
                    'message': 'Token is missing'
                }
            }), 401
            
            return response
            
        try:
            # Token dekodieren
            jwt_secret = os.getenv('JWT_SECRET')
            data = jwt.decode(token, jwt_secret, algorithms=['HS256'])
            request.user_id = data['user_id']
        except:
            # Mit CORS-Headern antworten, auch bei Token-Dekodierungsfehlern
            response = jsonify({
                'success': False,
                'error': {
                    'code': 'INVALID_TOKEN',
                    'message': 'Token is invalid or expired'
                }
            }), 401
            
            return response
        
        return f(*args, **kwargs)
    return decorated

@auth_bp.route('/login/<provider>', methods=['GET', 'OPTIONS'])
def login(provider):
    if request.method == 'OPTIONS':
        response = current_app.make_response("")
        return response
    
    if provider not in ['google', 'github']:
        return jsonify({"success": False, "error": {"code": "INVALID_PROVIDER", "message": "Invalid provider"}}), 400
    # Use the exact redirect URI that matches the GitHub OAuth app configuration
    redirect_uri = url_for('api.auth.callback', provider=provider, _external=True)
    return oauth.create_client(provider).authorize_redirect(redirect_uri)

@auth_bp.route('/callback/<provider>', methods=['GET', 'OPTIONS'])
def callback(provider):
    if request.method == 'OPTIONS':
        response = current_app.make_response("")
        return response
    
    if provider not in ['google', 'github']:
        return jsonify({"success": False, "error": {"code": "INVALID_PROVIDER", "message": "Invalid provider"}}), 400
    token = oauth.create_client(provider).authorize_access_token()
    user_info = get_user_info(provider, token.get('access_token'))
    if not user_info:
        return jsonify({"success": False, "error": {"code": "USER_INFO_FAILED", "message": "Failed to get user info"}}), 400
    
    user = User.query.filter_by(oauth_provider=provider, oauth_id=user_info['id']).first()
    if not user:
        existing_user = User.query.filter_by(email=user_info['email']).first()
        if existing_user:
            existing_user.oauth_provider = provider
            existing_user.oauth_id = user_info['id']
            existing_user.avatar = user_info.get('avatar')
            user = existing_user
        else:
            user = User(email=user_info['email'], name=user_info['name'], avatar=user_info.get('avatar'), oauth_provider=provider, oauth_id=user_info['id'], credits=0)
            db.session.add(user)
        
        oauth_token = OAuthToken(user_id=user.id, provider=provider, access_token=token.get('access_token'), refresh_token=token.get('refresh_token'), expires_at=datetime.utcnow() + timedelta(seconds=token.get('expires_in', 3600)))
        db.session.add(oauth_token)
        activity = UserActivity(user_id=user.id, activity_type='account', title='Account created' if not existing_user else f'Account linked with {provider}')
        db.session.add(activity)
        db.session.commit()
    
    jwt_token = jwt.encode({'user_id': user.id, 'exp': datetime.utcnow() + timedelta(hours=24)}, current_app.config['SECRET_KEY'], algorithm='HS256')
    frontend_url = os.getenv('FRONTEND_URL').strip()
    if isinstance(jwt_token, bytes):
        jwt_token = jwt_token.decode('utf-8')
    jwt_token = jwt_token.strip()
    return redirect(f"{frontend_url}/auth-callback?token={jwt_token}")

@auth_bp.route('/user', methods=['GET', 'OPTIONS'])
@token_required
def get_user():
    # Bei OPTIONS-Anfragen gib sofort eine Antwort zurück
    if request.method == 'OPTIONS':
        response = current_app.make_response("")
        return response
        
    user = User.query.get(request.user_id)
    if not user:
        return jsonify({"success": False, "error": {"code": "USER_NOT_FOUND", "message": "User not found"}}), 404
    else:
        return jsonify({
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "avatar": user.avatar,
            "credits": user.credits
        }), 200

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

@auth_bp.route('/login/google')
def google_login():
    """Google OAuth Login Route"""
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@auth_bp.route('/login/github')
def github_login():
    """GitHub OAuth Login Route"""
    redirect_uri = url_for('auth.github_callback', _external=True)
    return oauth.github.authorize_redirect(redirect_uri)

@auth_bp.route('/callback/google')
def google_callback():
    """Google OAuth Callback Route"""
    try:
        token = oauth.google.authorize_access_token()
        user_info = oauth.google.parse_id_token(token)
        return handle_oauth_callback('google', user_info)
    except Exception as e:
        logger.error(f"Fehler bei Google OAuth Callback: {str(e)}")
        return jsonify({
            'error': 'Google authentication failed',
            'message': str(e)
        }), 500

@auth_bp.route('/callback/github')
def github_callback():
    """GitHub OAuth Callback Route"""
    try:
        token = oauth.github.authorize_access_token()
        resp = oauth.github.get('user')
        user_info = resp.json()
        # GitHub liefert keine ID-Token, wir müssen die E-Mail separat abrufen
        resp = oauth.github.get('user/emails')
        emails = resp.json()
        primary_email = next((email['email'] for email in emails if email['primary']), None)
        if primary_email:
            user_info['email'] = primary_email
        return handle_oauth_callback('github', user_info)
    except Exception as e:
        logger.error(f"Fehler bei GitHub OAuth Callback: {str(e)}")
        return jsonify({
            'error': 'GitHub authentication failed',
            'message': str(e)
        }), 500

def handle_oauth_callback(provider: str, user_info: dict):
    """Zentrale Funktion zur Verarbeitung von OAuth-Callbacks"""
    try:
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
        
        # Speichere OAuth-Token
        token = oauth.__getattr__(provider).token
        oauth_token = OAuthToken(
            id=str(uuid4()),
            user_id=user.id,
            provider=provider,
            access_token=token.get('access_token'),
            refresh_token=token.get('refresh_token'),
            expires_at=datetime.utcnow() + timedelta(seconds=token.get('expires_in', 3600))
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
        
        # Erstelle JWT-Token
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