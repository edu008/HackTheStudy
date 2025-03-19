from flask import Blueprint, request, jsonify, redirect, url_for, current_app
import os
import requests
import uuid
from authlib.integrations.flask_client import OAuth
from datetime import datetime, timedelta
import jwt
from models import db, User, OAuthToken, UserActivity, Payment
from functools import wraps

auth_bp = Blueprint('auth', __name__)
oauth = OAuth()

def setup_oauth(app):
    oauth.register(
        name='google',
        client_id=os.getenv('GOOGLE_CLIENT_ID'),
        client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile',
            'token_endpoint_auth_method': 'client_secret_post',
            'code_challenge_method': None
        }
    )
    oauth.register(
        name='github',
        client_id=os.getenv('GITHUB_CLIENT_ID'),
        client_secret=os.getenv('GITHUB_CLIENT_SECRET'),
        access_token_url='https://github.com/login/oauth/access_token',
        authorize_url='https://github.com/login/oauth/authorize',
        api_base_url='https://api.github.com/',
        client_kwargs={'scope': 'user:email'},
    )
    oauth.init_app(app)

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
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({"success": False, "error": {"code": "NO_TOKEN", "message": "Token missing"}}), 401
        try:
            data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
            request.user_id = data['user_id']  # Speichere user_id in request
        except jwt.ExpiredSignatureError:
            return jsonify({"success": False, "error": {"code": "TOKEN_EXPIRED", "message": "Token expired"}}), 401
        except jwt.InvalidTokenError:
            return jsonify({"success": False, "error": {"code": "INVALID_TOKEN", "message": "Invalid token"}}), 401
        return f(*args, **kwargs)
    return decorated

@auth_bp.route('/login/<provider>')
def login(provider):
    if provider not in ['google', 'github']:
        return jsonify({"success": False, "error": {"code": "INVALID_PROVIDER", "message": "Invalid provider"}}), 400
    # Use the exact redirect URI that matches the GitHub OAuth app configuration
    redirect_uri = url_for('api.auth.callback', provider=provider, _external=True)
    return oauth.create_client(provider).authorize_redirect(redirect_uri)

@auth_bp.route('/callback/<provider>')
def callback(provider):
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
            user = User(email=user_info['email'], name=user_info['name'], avatar=user_info.get('avatar'), oauth_provider=provider, oauth_id=user_info['id'], credits=100)
            db.session.add(user)
            db.session.commit()
        
        oauth_token = OAuthToken(user_id=user.id, provider=provider, access_token=token.get('access_token'), refresh_token=token.get('refresh_token'), expires_at=datetime.utcnow() + timedelta(seconds=token.get('expires_in', 3600)))
        db.session.add(oauth_token)
        activity = UserActivity(user_id=user.id, activity_type='account', title='Account created' if not existing_user else f'Account linked with {provider}')
        db.session.add(activity)
        db.session.commit()
    
    jwt_token = jwt.encode({'user_id': user.id, 'exp': datetime.utcnow() + timedelta(hours=24)}, current_app.config['SECRET_KEY'], algorithm='HS256')
    frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:8080')
    return redirect(f"{frontend_url}/auth-callback?token={jwt_token}")

@auth_bp.route('/user', methods=['GET'])
@token_required
def get_user():
    user = User.query.get(request.user_id)
    if not user:
        return jsonify({"success": False, "error": {"code": "USER_NOT_FOUND", "message": "User not found"}}), 404
    return jsonify({
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "avatar": user.avatar,
        "credits": user.credits
    }), 200

@auth_bp.route('/activity', methods=['GET'])
@token_required
def get_activity():
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

@auth_bp.route('/activity', methods=['POST'])
@token_required
def record_activity():
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

@auth_bp.route('/payment', methods=['POST'])
@token_required
def process_payment():
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

@auth_bp.route('/payments', methods=['GET'])
@token_required
def get_payments():
    payments = Payment.query.filter_by(user_id=request.user_id).order_by(Payment.created_at.desc()).all()
    return jsonify({
        "success": True,
        "data": {
            "payments": [{"id": p.id, "amount": p.amount, "credits": p.credits, "payment_method": p.payment_method, "transaction_id": p.transaction_id, "status": p.status, "created_at": p.created_at.isoformat()} for p in payments]
        }
    }), 200