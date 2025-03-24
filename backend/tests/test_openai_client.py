"""
Tests für den OpenAI-Client mit Mocks.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from api.openai_client import chat_completion_with_backoff, get_openai_client, generate_cache_key
from openai import APIError, RateLimitError, APITimeoutError

@pytest.fixture
def mock_openai():
    """Fixture zum Mocken des OpenAI-Clients."""
    with patch('api.openai_client._thread_local') as mock_thread_local:
        mock_client = MagicMock()
        mock_thread_local.client = mock_client
        
        mock_completion = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        
        mock_completion.usage.prompt_tokens = 10
        mock_completion.usage.completion_tokens = 20
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "Dies ist eine Testantwort."
        mock_completion.model_dump.return_value = {
            "choices": [{
                "message": {"role": "assistant", "content": "Dies ist eine Testantwort."},
                "index": 0,
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
        }
        
        yield mock_client

@pytest.fixture
def mock_redis():
    """Fixture zum Mocken des Redis-Clients."""
    with patch('api.openai_client.redis_client') as mock_redis:
        yield mock_redis

def test_get_openai_client():
    """Testet das Abrufen des OpenAI-Clients."""
    with patch('api.openai_client.OpenAI') as mock_openai_class:
        with patch('api.openai_client.os') as mock_os:
            mock_os.environ.get.return_value = 'test_api_key'
            
            # Erste Anfrage erstellt einen neuen Client
            client1 = get_openai_client()
            mock_openai_class.assert_called_once()
            
            # Zweite Anfrage verwendet den vorhandenen Client
            client2 = get_openai_client()
            mock_openai_class.assert_called_once()
            
            assert client1 == client2

def test_generate_cache_key():
    """Testet die Generierung von Cache-Schlüsseln."""
    messages = [{"role": "user", "content": "Test"}]
    key1 = generate_cache_key("gpt-4", messages)
    key2 = generate_cache_key("gpt-4", messages)
    key3 = generate_cache_key("gpt-3.5-turbo", messages)
    key4 = generate_cache_key("gpt-4", [{"role": "user", "content": "Anderer Text"}])
    
    # Gleiche Parameter erzeugen den gleichen Schlüssel
    assert key1 == key2
    
    # Unterschiedliche Parameter erzeugen unterschiedliche Schlüssel
    assert key1 != key3
    assert key1 != key4

def test_chat_completion_success(mock_openai, mock_redis):
    """Testet erfolgreiche Chat-Completion-Anfragen."""
    # Cache deaktivieren für diesen Test
    mock_redis.get.return_value = None
    
    messages = [{"role": "user", "content": "Test"}]
    response = chat_completion_with_backoff("gpt-4", messages, use_cache=True)
    
    # Überprüfe, ob die OpenAI-Methode aufgerufen wurde
    mock_openai.chat.completions.create.assert_called_once_with(
        model="gpt-4",
        messages=messages
    )
    
    # Überprüfe, ob die Antwort korrekt ist
    assert "choices" in response
    assert response["choices"][0]["message"]["content"] == "Dies ist eine Testantwort."

def test_chat_completion_with_cache(mock_openai, mock_redis):
    """Testet Chat-Completion mit Cache-Treffer."""
    # Cache-Treffer simulieren
    cached_response = {
        "choices": [{
            "message": {"role": "assistant", "content": "Dies ist eine gecachte Antwort."},
            "index": 0,
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 10,
            "total_tokens": 15
        }
    }
    
    mock_redis.get.return_value = json.dumps(cached_response)
    
    messages = [{"role": "user", "content": "Test"}]
    response = chat_completion_with_backoff("gpt-4", messages, use_cache=True)
    
    # Überprüfe, ob die OpenAI-Methode NICHT aufgerufen wurde
    mock_openai.chat.completions.create.assert_not_called()
    
    # Überprüfe, ob die gecachte Antwort zurückgegeben wurde
    assert "choices" in response
    assert response["choices"][0]["message"]["content"] == "Dies ist eine gecachte Antwort."

@patch('api.openai_client.track_token_usage')
def test_token_tracking(mock_track, mock_openai, mock_redis):
    """Testet das Tracking der Token-Nutzung."""
    # Cache deaktivieren für diesen Test
    mock_redis.get.return_value = None
    
    messages = [{"role": "user", "content": "Test"}]
    chat_completion_with_backoff("gpt-4", messages, user_id="user123", 
                             session_id="session123", function_name="test_function")
    
    # Überprüfe, ob die Tracking-Funktion aufgerufen wurde
    mock_track.assert_called_once_with(
        user_id="user123",
        session_id="session123",
        model="gpt-4",
        input_tokens=10,
        output_tokens=20,
        function_name="test_function",
        cached=False
    )

@patch('api.openai_client.backoff.on_exception')
def test_retry_on_error(mock_backoff, mock_openai):
    """Testet das Wiederholungsverhalten bei API-Fehlern."""
    # Simuliere einen API-Fehler
    mock_openai.chat.completions.create.side_effect = APIError("Test-Fehler")
    
    messages = [{"role": "user", "content": "Test"}]
    
    # Der patch für backoff.on_exception ist nur für die Validierung
    # Die eigentliche Wiederholung wird durch den Decorator gesteuert
    
    with pytest.raises(APIError):
        chat_completion_with_backoff("gpt-4", messages)
    
    # Überprüfe, ob die OpenAI-Methode aufgerufen wurde
    mock_openai.chat.completions.create.assert_called()

@patch('api.openai_client.logger')
def test_error_logging(mock_logger, mock_openai):
    """Testet das Logging von Fehlern."""
    # Simuliere einen API-Fehler
    mock_openai.chat.completions.create.side_effect = APITimeoutError("Timeout-Fehler")
    
    messages = [{"role": "user", "content": "Test"}]
    
    with pytest.raises(APITimeoutError):
        chat_completion_with_backoff("gpt-4", messages)
    
    # Überprüfe, ob der Fehler protokolliert wurde
    mock_logger.error.assert_called_once()
    assert "Fehler bei OpenAI-Anfrage" in mock_logger.error.call_args[0][0]