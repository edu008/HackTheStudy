"""
Pytest-Konfiguration und gemeinsame Fixtures für Tests.
"""

import os
import tempfile
import pytest
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from core.models import db as _db
from werkzeug.security import generate_password_hash
import uuid
from datetime import datetime, timedelta

# Testumgebungsvariablen
TEST_DATABASE_URI = 'sqlite:///:memory:'

@pytest.fixture(scope='session')
def app():
    """Erstellt eine Flask-Testanwendung."""
    # Erstelle eine temporäre .env Datei für Tests
    env_fd, env_path = tempfile.mkstemp(suffix='.env')
    with os.fdopen(env_fd, 'w') as f:
        f.write(f'DATABASE_URL={TEST_DATABASE_URI}\n')
        f.write('FLASK_ENV=testing\n')
        f.write('TESTING=true\n')
        f.write('JWT_SECRET=test_secret_key\n')
        f.write('REDIS_URL=redis://localhost:6379/1\n')  # Separate Redis-DB für Tests
        f.write('OPENAI_API_KEY=test_api_key\n')
        f.write('LOG_LEVEL=ERROR\n')  # Weniger Logging für Tests
    
    # Lade die App mit Testeinstellungen
    from app import create_app
    app = create_app(testing=True)
    
    # Konfiguriere die App für Tests
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=TEST_DATABASE_URI,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SERVER_NAME='test.local',
        JWT_SECRET_KEY='test_secret_key',
        PRESERVE_CONTEXT_ON_EXCEPTION=False,
        WTF_CSRF_ENABLED=False
    )
    
    # Stelle den Anwendungskontext bereit
    with app.app_context():
        yield app
    
    # Räume auf
    os.unlink(env_path)

@pytest.fixture(scope='session')
def db(app):
    """Erstellt eine Testdatenbank und fügt Tabellen ein."""
    _db.app = app
    _db.create_all()
    
    yield _db
    
    _db.drop_all()

@pytest.fixture(scope='function')
def session(db):
    """Erstellt eine neue Datenbanksitzung für einen Test."""
    connection = db.engine.connect()
    transaction = connection.begin()
    
    session = db.create_scoped_session(
        options=dict(bind=connection, binds={})
    )
    
    db.session = session
    
    yield session
    
    transaction.rollback()
    connection.close()
    session.remove()

@pytest.fixture
def client(app):
    """Erstellt einen Testclient für Flask."""
    with app.test_client() as client:
        yield client

@pytest.fixture
def auth_headers():
    """Erstellt Auth-Header für Tests."""
    import jwt
    from datetime import datetime, timedelta
    
    # Erstelle ein Test-Token
    payload = {
        'sub': str(uuid.uuid4()),
        'email': 'test@example.com',
        'name': 'Test User',
        'exp': datetime.utcnow() + timedelta(days=1)
    }
    
    token = jwt.encode(payload, 'test_secret_key', algorithm='HS256')
    
    return {'Authorization': f'Bearer {token}'}

@pytest.fixture
def test_user(db, session):
    """Erstellt einen Testbenutzer."""
    from core.models import User
    
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        email='test@example.com',
        name='Test User',
        credits=100
    )
    
    session.add(user)
    session.commit()
    
    return user

@pytest.fixture
def test_upload(db, session, test_user):
    """Erstellt einen Testupload."""
    from core.models import Upload
    
    session_id = str(uuid.uuid4())
    upload = Upload(
        id=str(uuid.uuid4()),
        session_id=session_id,
        user_id=test_user.id,
        file_name_1='test_document.pdf',
        content='Dies ist ein Testinhalt für die Upload-Verarbeitung.',
        processing_status='completed'
    )
    
    session.add(upload)
    session.commit()
    
    return upload

@pytest.fixture
def mock_openai_response():
    """Mock-Antwort für OpenAI API-Aufrufe."""
    class MockUsage:
        def __init__(self):
            self.prompt_tokens = 10
            self.completion_tokens = 20
    
    class MockChoice:
        def __init__(self, content):
            self.message = {"role": "assistant", "content": content}
            self.index = 0
            self.finish_reason = "stop"
    
    class MockResponse:
        def __init__(self, content):
            self.choices = [MockChoice(content)]
            self.usage = MockUsage()
        
        def model_dump(self):
            return {
                "choices": [{
                    "message": self.choices[0].message,
                    "index": 0,
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": self.usage.prompt_tokens,
                    "completion_tokens": self.usage.completion_tokens,
                    "total_tokens": self.usage.prompt_tokens + self.usage.completion_tokens
                }
            }
    
    return MockResponse 