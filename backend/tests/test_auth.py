"""
Tests für die Authentifizierungsfunktionen.
"""

import pytest
import json
import jwt
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

def test_token_validation(client, auth_headers):
    """Testet die Token-Validierung."""
    # Route, die Authentifizierung erfordert
    response = client.get('/user/profile', headers=auth_headers)
    assert response.status_code != 401

def test_missing_token(client):
    """Testet den Zugriff ohne Token."""
    response = client.get('/user/profile')
    assert response.status_code == 401
    data = json.loads(response.data)
    assert 'message' in data
    assert 'Authentifizierung erforderlich' in data['message']

def test_invalid_token(client):
    """Testet den Zugriff mit ungültigem Token."""
    headers = {'Authorization': 'Bearer invalid_token'}
    response = client.get('/user/profile', headers=headers)
    assert response.status_code == 401
    data = json.loads(response.data)
    assert 'message' in data
    assert 'Ungültiges Token' in data['message']

def test_expired_token(client):
    """Testet den Zugriff mit abgelaufenem Token."""
    # Erstelle ein abgelaufenes Token
    payload = {
        'sub': '12345',
        'email': 'test@example.com',
        'name': 'Test User',
        'exp': datetime.utcnow() - timedelta(days=1)  # Abgelaufen
    }
    
    token = jwt.encode(payload, 'test_secret_key', algorithm='HS256')
    headers = {'Authorization': f'Bearer {token}'}
    
    response = client.get('/user/profile', headers=headers)
    assert response.status_code == 401
    data = json.loads(response.data)
    assert 'message' in data
    assert 'Abgelaufenes Token' in data['message']

@patch('api.auth.requests.post')
def test_oauth_login_google(mock_post, client):
    """Testet den Google OAuth-Login."""
    # Mock für die Google API
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'access_token': 'fake_access_token',
        'id_token': 'fake_id_token',
        'expires_in': 3600
    }
    mock_post.return_value = mock_response
    
    # Mock für den Google-Userinfo-Endpunkt
    with patch('api.auth.requests.get') as mock_get:
        mock_userinfo = MagicMock()
        mock_userinfo.status_code = 200
        mock_userinfo.json.return_value = {
            'sub': '12345',
            'email': 'test@example.com',
            'name': 'Test User',
            'picture': 'https://example.com/profile.jpg'
        }
        mock_get.return_value = mock_userinfo
        
        # Sende Anfrage
        response = client.post('/auth/login', json={
            'provider': 'google',
            'code': 'fake_auth_code'
        })
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'token' in data
        assert 'user' in data
        assert data['user']['email'] == 'test@example.com'

@patch('api.auth.requests.post')
def test_oauth_login_github(mock_post, client):
    """Testet den GitHub OAuth-Login."""
    # Mock für die GitHub API
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'access_token': 'fake_github_token'
    }
    mock_post.return_value = mock_response
    
    # Mock für den GitHub-User-Endpunkt
    with patch('api.auth.requests.get') as mock_get:
        mock_userinfo = MagicMock()
        mock_userinfo.status_code = 200
        mock_userinfo.json.return_value = {
            'id': '54321',
            'email': 'test@example.com',
            'name': 'Test User',
            'avatar_url': 'https://example.com/avatar.jpg'
        }
        mock_get.return_value = mock_userinfo
        
        # Sende Anfrage
        response = client.post('/auth/login', json={
            'provider': 'github',
            'code': 'fake_auth_code'
        })
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'token' in data
        assert 'user' in data
        assert data['user']['email'] == 'test@example.com'

def test_oauth_invalid_provider(client):
    """Testet Login mit ungültigem Provider."""
    response = client.post('/auth/login', json={
        'provider': 'invalid_provider',
        'code': 'fake_auth_code'
    })
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'message' in data
    assert 'Ungültiger Provider' in data['message'] 