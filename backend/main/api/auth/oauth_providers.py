"""
OAuth-Provider-Integration für die Authentifizierung.
Enthält Funktionen zur Konfiguration und Nutzung verschiedener OAuth-Provider.
"""

import logging
import os
import json
import requests
from flask import session, url_for, redirect
from urllib.parse import urlencode

# WICHTIG: Wir verwenden keine direkte Authlib-Integration mehr wegen Metaklassen-Konflikt
# from authlib.integrations.flask_client import OAuth

# Logger konfigurieren
logger = logging.getLogger(__name__)

# OAuth-Clients für die einzelnen Provider
oauth_clients = {}

# Unterstützte OAuth-Provider
SUPPORTED_PROVIDERS = ['google', 'github']


def setup_oauth(app):
    """Initialisiert die OAuth-Konfiguration für die App."""
    # Prüfe zuerst, ob die OAuth-Konfiguration vorhanden ist
    google_client_id = os.getenv('GOOGLE_CLIENT_ID')
    google_client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    github_client_id = os.getenv('GITHUB_CLIENT_ID')
    github_client_secret = os.getenv('GITHUB_CLIENT_SECRET')

    # Statt OAuth.init_app verwenden wir ein einfaches Dictionary für die Clients
    oauth_clients.clear()

    # Registriere OAuth-Provider nur, wenn die notwendigen Schlüssel vorhanden sind
    if google_client_id and google_client_secret:
        oauth_clients['google'] = {
            'client_id': google_client_id.strip(),
            'client_secret': google_client_secret.strip(),
            'authorize_url': 'https://accounts.google.com/o/oauth2/auth',
            'token_url': 'https://oauth2.googleapis.com/token',
            'userinfo_url': 'https://www.googleapis.com/oauth2/v1/userinfo',
            'scope': 'openid email profile',
            'redirect_uri': os.getenv('API_URL', 'http://localhost:8080') + '/api/v1/auth/callback/google'
        }
        logger.info("Google OAuth konfiguriert.")
    else:
        logger.warning("WARNUNG: Google OAuth nicht konfiguriert (fehlende Umgebungsvariablen).")

    if github_client_id and github_client_secret:
        oauth_clients['github'] = {
            'client_id': github_client_id.strip(),
            'client_secret': github_client_secret.strip(),
            'authorize_url': 'https://github.com/login/oauth/authorize',
            'token_url': 'https://github.com/login/oauth/access_token',
            'userinfo_url': 'https://api.github.com/user',
            'email_url': 'https://api.github.com/user/emails',
            'scope': 'user:email',
            'redirect_uri': os.getenv('API_URL', 'http://localhost:8080') + '/api/v1/auth/callback/github'
        }
        logger.info("GitHub OAuth konfiguriert.")
    else:
        logger.warning("WARNUNG: GitHub OAuth nicht konfiguriert (fehlende Umgebungsvariablen).")


def validate_provider(provider):
    """Validiert, ob der angegebene OAuth-Provider unterstützt wird."""
    if provider not in SUPPORTED_PROVIDERS:
        return False
    # Prüfe, ob der Provider konfiguriert ist
    if provider not in oauth_clients:
        logger.error("OAuth Provider %s nicht konfiguriert", provider)
        return False
    return True


def get_oauth_client(provider):
    """Gibt den OAuth-Client für den angegebenen Provider zurück.
    
    Diese Funktion wurde hinzugefügt, um die Kompatibilität mit routes.py herzustellen,
    die diese Funktion erwartet, um den OAuth-Client zu erhalten.
    
    Args:
        provider (str): Name des OAuth-Providers ('google', 'github', usw.)
        
    Returns:
        dict or None: Der OAuth-Client-Konfiguration oder None, wenn der Provider nicht unterstützt wird
    """
    if not validate_provider(provider):
        return None
        
    return oauth_clients.get(provider)


def get_authorization_url(provider, state=None):
    """Erzeugt eine Autorisierungs-URL für den OAuth-Prozess."""
    if not validate_provider(provider):
        return None
    
    client = oauth_clients.get(provider)
    if not client:
        return None
    
    params = {
        'client_id': client['client_id'],
        'redirect_uri': client['redirect_uri'],
        'response_type': 'code',
        'scope': client['scope']
    }
    
    if state:
        params['state'] = state
    
    return f"{client['authorize_url']}?{urlencode(params)}"


def get_token(provider, code):
    """Tauscht einen Autorisierungscode gegen ein Access-Token aus."""
    if not validate_provider(provider):
        return None
    
    client = oauth_clients.get(provider)
    if not client:
        return None
    
    data = {
        'client_id': client['client_id'],
        'client_secret': client['client_secret'],
        'code': code,
        'redirect_uri': client['redirect_uri'],
        'grant_type': 'authorization_code'
    }
    
    headers = {
        'Accept': 'application/json'
    }
    
    try:
        response = requests.post(
            client['token_url'],
            data=data,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            if 'application/json' in response.headers.get('content-type', ''):
                return response.json().get('access_token')
            else:
                # GitHub sendet application/x-www-form-urlencoded
                content = response.text
                if 'access_token=' in content:
                    return content.split('access_token=')[1].split('&')[0]
        
        logger.error(
            "Fehler beim Token-Abruf von %s: %s",
            provider,
            response.text if hasattr(response, 'text') else 'Kein Antworttext'
        )
    except Exception as e:
        logger.error("Ausnahme beim Token-Abruf von %s: %s", provider, str(e))
    
    return None


def get_user_info(provider, token):
    """Ruft Benutzerinformationen vom OAuth-Provider ab."""
    try:
        if provider == 'google':
            resp = requests.get(
                oauth_clients['google']['userinfo_url'],
                headers={'Authorization': f'Bearer {token}'},
                timeout=10  # 10 Sekunden Timeout
            )
            if resp.status_code == 200:
                user_info = resp.json()
                return {
                    'provider': 'google', 
                    'id': user_info['id'], 
                    'email': user_info['email'], 
                    'name': user_info.get('name', user_info['email'].split('@')[0]), 
                    'avatar': user_info.get('picture')
                }
        elif provider == 'github':
            resp = requests.get(
                oauth_clients['github']['userinfo_url'], 
                headers={'Authorization': f'token {token}'},
                timeout=10  # 10 Sekunden Timeout
            )
            if resp.status_code == 200:
                user_info = resp.json()
                email_resp = requests.get(
                    oauth_clients['github']['email_url'],
                    headers={'Authorization': f'token {token}'},
                    timeout=10  # 10 Sekunden Timeout
                )
                email = user_info.get('email')
                if email_resp.status_code == 200:
                    emails = email_resp.json()
                    primary_email = next((e['email'] for e in emails if e['primary']), None)
                    if primary_email:
                        email = primary_email
                name = user_info.get('name') or user_info['login']
                return {
                    'provider': 'github', 
                    'id': str(user_info['id']), 
                    'email': email or f"{user_info['login']}@github.com", 
                    'name': name, 
                    'avatar': user_info.get('avatar_url')
                }
    except Exception as e:
        logger.error("Fehler beim Abrufen von Benutzerinformationen von %s: %s", provider, str(e))
    return None
