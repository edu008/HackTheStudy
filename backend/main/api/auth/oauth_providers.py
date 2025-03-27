"""
OAuth-Provider-Integration für die Authentifizierung.
Enthält Funktionen zur Konfiguration und Nutzung verschiedener OAuth-Provider.
"""

import os
import logging
import requests
from authlib.integrations.flask_client import OAuth

# Logger konfigurieren
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

def get_oauth_client(provider):
    """Erstellt einen OAuth-Client für den angegebenen Provider."""
    if not validate_provider(provider):
        return None
    return oauth.create_client(provider) 