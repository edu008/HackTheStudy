"""
Zentrale OpenAI-Integration für HackTheStudy.

Dieses Modul vereinheitlicht alle Komponenten für die Interaktion mit der OpenAI-API:
- Token-Tracking und Kostenberechnung
- Caching von API-Anfragen
- Fehlerbehandlung und Backoff-Logik
- Kreditsystem und Abrechnungsfunktionen
"""

import functools
import hashlib
import json
import logging
import math
import os
import threading
import time
import traceback
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union

import backoff
import tiktoken
from core.models import TokenUsage, User, db
from core.redis_client import RedisClient, redis_client
from openai import APIError, APITimeoutError, OpenAI, RateLimitError

# Logger konfigurieren
logger = logging.getLogger('core.openai_integration')

# Thread-lokaler Speicher für Client-Instanzen
_thread_local = threading.local()

# Konfigurationswerte aus Umgebungsvariablen
DEFAULT_MODEL = os.environ.get('OPENAI_DEFAULT_MODEL', 'gpt-4o')
CACHE_TTL = int(os.environ.get('OPENAI_CACHE_TTL', 86400))  # 24 Stunden Standard-TTL
CACHE_ENABLED = os.environ.get('OPENAI_CACHE_ENABLED', 'true').lower() == 'true'
MAX_RETRIES = int(os.environ.get('OPENAI_MAX_RETRIES', 3))
MAX_TIMEOUT = int(os.environ.get('OPENAI_TIMEOUT', 120))  # Timeout in Sekunden

# Modell-Preiskonfiguration pro 1000 Tokens (in Credits)
MODEL_PRICING = {
    'gpt-4o': {'input': 150, 'output': 300},
    'gpt-4-turbo': {'input': 150, 'output': 300},
    'gpt-3.5-turbo': {'input': 15, 'output': 20},
    'gpt-4-vision-preview': {'input': 150, 'output': 300},
    'gpt-4': {'input': 300, 'output': 600},
    'gpt-4-32k': {'input': 600, 'output': 1200},
}

# Singleton-Klasse für OpenAI-Cache


class OpenAICache:
    """
    Cache für OpenAI-API-Aufrufe zur Reduzierung von Kosten und Wartezeiten.
    Verwendet den zentralen Redis-Client als Backend-Speicher.
    """

    # Singleton-Instanz
    _instance = None

    def __new__(cls):
        """Stellt sicher, dass nur eine Instanz existiert (Singleton)."""
        if cls._instance is None:
            cls._instance = super(OpenAICache, cls).__new__(cls)
            # Initialisiere Attribute hier, um 'access before definition' zu vermeiden
            cls._instance._initialized = False
            cls._instance.ttl = CACHE_TTL
            cls._instance.enabled = CACHE_ENABLED
        return cls._instance
        
    def __init__(self, ttl: int = CACHE_TTL):
        """
        Initialisiert den OpenAI-Cache.

        Args:
            ttl: Time-to-Live für Cache-Einträge in Sekunden
        """
        if self._initialized:
            return

        # Attribute bereits in __new__ initialisiert
        self.ttl = ttl  # Aktualisiere TTL, falls ein anderer Wert übergeben wurde
        
        self._initialized = True
        logger.info("OpenAI-Cache initialisiert. TTL: %s Sekunden. Aktiviert: %s", ttl, self.enabled)

    def enable(self):
        """Aktiviert den Cache."""
        self.enabled = True
        logger.info("OpenAI-Cache aktiviert")

    def disable(self):
        """Deaktiviert den Cache."""
        self.enabled = False
        logger.info("OpenAI-Cache deaktiviert")

    def generate_key(self, model: str, messages: List[Dict], **kwargs) -> str:
        """
        Generiert einen Cache-Schlüssel aus den Anfrageparametern.

        Args:
            model: OpenAI-Modellname
            messages: Nachrichten-Liste
            **kwargs: Weitere Parameter für die API

        Returns:
            Cache-Schlüssel als String
        """
        # Hauptparameter zusammenfassen
        cache_params = {
            'model': model,
            'messages': messages,
        }

        # Optionale Parameter hinzufügen, die das Ergebnis beeinflussen
        for param in ['temperature', 'top_p', 'n', 'stop', 'max_tokens',
                      'presence_penalty', 'frequency_penalty', 'logit_bias', 'functions']:
            if param in kwargs and kwargs[param] is not None:
                cache_params[param] = kwargs[param]

        # Runde numerische Werte für konsistente Schlüssel
        if 'temperature' in cache_params:
            cache_params['temperature'] = round(cache_params['temperature'], 2)

        # JSON-String erstellen und hashen
        json_str = json.dumps(cache_params, sort_keys=True)
        return f"openai:chat:{hashlib.md5(json_str.encode()).hexdigest()}"

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Holt einen Wert aus dem Cache.

        Args:
            key: Cache-Schlüssel

        Returns:
            Gecachte Antwort oder None, falls nicht im Cache
        """
        if not self.enabled:
            return None

        try:
            value = redis_client.get(key, default=None, as_json=True)
            if value:
                logger.debug("Cache-Treffer für Schlüssel: %s", key)
                return value
            logger.debug("Cache-Fehltreffer für Schlüssel: %s", key)
        except Exception as e:
            logger.error("Fehler beim Lesen aus dem Cache: %s", str(e))

        return None

    def set(self, key: str, value: Dict[str, Any]) -> bool:
        """
        Speichert einen Wert im Cache.

        Args:
            key: Cache-Schlüssel
            value: Zu cachender Wert

        Returns:
            True bei Erfolg, False bei Fehler
        """
        if not self.enabled:
            return False

        try:
            # Füge einen Zeitstempel hinzu, um das Caching-Datum zu verfolgen
            value["_cached_at"] = int(time.time())
            result = redis_client.set(key, value, ex=self.ttl)
            if result:
                logger.debug("Wert erfolgreich gecached für Schlüssel: %s", key)
            return result
        except Exception as e:
            logger.error("Fehler beim Schreiben in den Cache: %s", str(e))
            return False

    def invalidate(self, key: str) -> bool:
        """
        Ungültigmacht einen Cache-Eintrag.

        Args:
            key: Cache-Schlüssel

        Returns:
            True bei Erfolg, False bei Fehler
        """
        try:
            result = redis_client.delete(key)
            if result:
                logger.debug("Cache-Eintrag ungültig gemacht für Schlüssel: %s", key)
            return result
        except Exception as e:
            logger.error("Fehler beim Löschen aus dem Cache: %s", str(e))
            return False

    def clear(self, pattern: str = "openai:chat:*") -> int:
        """
        Löscht alle Cache-Einträge, die dem Muster entsprechen.

        Args:
            pattern: Redis-Schlüsselmuster zum Löschen

        Returns:
            Anzahl der gelöschten Einträge
        """
        try:
            client = redis_client.get_client()
            keys = client.keys(pattern)
            count = 0

            if keys:
                count = client.delete(*keys)
                logger.info("%s Cache-Einträge gelöscht (Muster: %s)", count, pattern)

            return count
        except Exception as e:
            logger.error("Fehler beim Löschen der Cache-Einträge: %s", str(e))
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Gibt Statistiken über den Cache zurück.

        Returns:
            Dict mit Cache-Statistiken
        """
        try:
            client = redis_client.get_client()
            keys = client.keys("openai:chat:*")
            total_size = 0

            # Stichprobe für die durchschnittliche Größe
            sample_size = min(len(keys), 10)
            if sample_size > 0:
                sample_keys = keys[:sample_size]
                for key in sample_keys:
                    size = len(client.get(key) or b'')
                    total_size += size

                avg_size = total_size / sample_size
                estimated_total_size = avg_size * len(keys)
            else:
                avg_size = 0
                estimated_total_size = 0

            return {
                "total_entries": len(keys),
                "sample_size": sample_size,
                "avg_entry_size_bytes": int(avg_size),
                "estimated_total_size_kb": int(estimated_total_size / 1024),
                "estimated_total_size_mb": round(estimated_total_size / (1024 * 1024), 2)
            }
        except Exception as e:
            logger.error("Fehler beim Abrufen der Cache-Statistiken: %s", e)
            return {
                "error": str(e),
                "total_entries": 0
            }

# Token-Tracking-Funktionen


def count_tokens(text_or_messages, model: str = DEFAULT_MODEL) -> int:
    """
    Zählt die Tokens in einem Text oder einer Liste von Nachrichten.

    Args:
        text_or_messages: Der Text oder die Nachrichten
        model: Das zu verwendende Modell für die Token-Zählung

    Returns:
        Anzahl der Tokens
    """
    if not text_or_messages:
        return 0

    try:
        # Konvertiere Text oder Nachrichten in einen String für die Zählung
        if isinstance(text_or_messages, list):
            if all(isinstance(item, dict) and "content" in item for item in text_or_messages):
                # Format: [{"role": "user", "content": "..."}, ...]
                text = " ".join([msg.get("content", "") for msg in text_or_messages])
            else:
                # Anderes Listenformat
                text = str(text_or_messages)
        else:
            # Einfacher String
            text = str(text_or_messages)

        # Verwende tiktoken für genaue Zählung
        encoder = tiktoken.encoding_for_model(model)
        token_count = len(encoder.encode(text))
        logger.debug("Tiktoken-Zählung: %s Tokens für %s Zeichen", token_count, len(text))
        return token_count
    except Exception as e:
        logger.warning("Fehler beim Zählen der Tokens mit tiktoken: %s", str(e))
        # Fallback: Ungefähre Schätzung (1 Token ≈ 4 Zeichen)
        if isinstance(text_or_messages, str):
            fallback_count = len(text_or_messages) // 4
        elif isinstance(text_or_messages, list):
            fallback_count = len(str(text_or_messages)) // 4
        else:
            fallback_count = 0
        logger.warning("Fallback-Zählung verwendet: %s Tokens (ca.)", fallback_count)
        return fallback_count


def calculate_token_cost(model: str, input_tokens: int, output_tokens: int) -> int:
    """
    Berechnet die Kosten basierend auf Token-Anzahl und Modell.

    Args:
        model: Das verwendete OpenAI-Modell
        input_tokens: Anzahl der Input-Tokens
        output_tokens: Anzahl der Output-Tokens

    Returns:
        Kosten in Credits
    """
    # Für sehr kleine Anfragen (<500 Tokens), Mindestgebühr
    if input_tokens < 500:
        return 100  # Pauschale Mindestgebühr für kleine Dokumente

    # Für mittlere Anfragen (500-3000 Tokens)
    if input_tokens < 3000:
        return 200  # Pauschale Gebühr für mittlere Dokumente

    # Lookup im MODEL_PRICING-Dictionary für das richtige Modell
    model_key = model
    # Fallback für unbekannte Modelle
    if model not in MODEL_PRICING:
        if "gpt-4" in model:
            model_key = "gpt-4"
        else:
            model_key = "gpt-3.5-turbo"

    pricing = MODEL_PRICING[model_key]

    # Berechne Kosten pro Token
    input_cost = (input_tokens / 1000) * pricing['input']
    output_cost = (output_tokens / 1000) * pricing['output']

    # Gesamtkosten berechnen und auf die nächste ganze Zahl aufrunden
    total_cost = math.ceil(input_cost + output_cost)

    # Mindestkosten von 100 Credits pro API-Aufruf für größere Dokumente
    return max(100, total_cost)


def track_token_usage(user_id: Optional[str] = None,
                      session_id: Optional[str] = None,
                      model: Optional[str] = None,
                      input_tokens: int = 0,
                      output_tokens: int = 0,
                      function_name: Optional[str] = None,
                      cached: bool = False,
                      metadata: Optional[Dict] = None) -> bool:
    """
    Verfolgt die Token-Nutzung für eine API-Anfrage und speichert sie in der Datenbank.

    Args:
        user_id: ID des Benutzers (optional)
        session_id: ID der Session (optional)
        model: Verwendetes Modell (optional)
        input_tokens: Anzahl der Input-Tokens
        output_tokens: Anzahl der Output-Tokens
        function_name: Name der aufrufenden Funktion (optional)
        cached: Ob die Antwort aus dem Cache kam
        metadata: Zusätzliche Metadaten zur Anfrage

    Returns:
        True bei Erfolg, False bei Fehler
    """
    try:
        # Logging für Tracking-Informationen
        logger.info(
            f"Token-Tracking: user_id={user_id}, session_id={session_id}, "
            f"model={model}, input_tokens={input_tokens}, output_tokens={output_tokens}, "
            f"function={function_name}, cached={cached}"
        )

        # Berechne die Kosten in Credits
        if model and input_tokens and output_tokens:
            cost = calculate_token_cost(model, input_tokens, output_tokens)
            if cached:
                # Reduzierte Kosten für gecachte Anfragen
                cost = max(1, cost // 10)  # 10% der normalen Kosten, mindestens 1
        else:
            cost = 0

        # Erstelle einen neuen TokenUsage-Eintrag
        usage = TokenUsage(
            id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
            timestamp=datetime.utcnow(),
            model=model or DEFAULT_MODEL,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            endpoint=function_name,
            function_name=function_name,
            cached=cached,
            request_metadata=metadata
        )

        db.session.add(usage)
        db.session.commit()

        logger.info("Token-Nutzung in Datenbank gespeichert: %s Credits für %s", cost, function_name)
        return True
    except Exception as e:
        logger.error("Fehler beim Token-Tracking: %s", str(e))
        db.session.rollback()
        return False


def check_credits_available(cost: int, user_id: Optional[str] = None) -> bool:
    """
    Überprüft, ob der Benutzer genügend Credits hat, ohne sie abzuziehen.

    Args:
        cost: Anzahl der Credits, die benötigt werden
        user_id: ID des Benutzers

    Returns:
        True, wenn genügend Credits vorhanden sind, False sonst
    """
    if not user_id:
        # Ohne Benutzer-ID erlauben wir die Anfrage
        return True

    try:
        user = User.query.get(user_id)
        if not user:
            logger.warning("Benutzer %s nicht gefunden für Credits-Prüfung", user_id)
            return False

        has_enough = user.credits >= cost
        if not has_enough:
            logger.warning("Benutzer %s hat nicht genügend Credits: %s < %s", user_id, user.credits, cost)

        return has_enough
    except Exception as e:
        logger.error("Fehler bei der Credits-Prüfung: %s", str(e))
        return False


def deduct_credits(user_id: str, cost: int, session_id: Optional[str] = None,
                   function_name: Optional[str] = None) -> bool:
    """
    Zieht Credits von einem Benutzer ab.

    Args:
        user_id: ID des Benutzers
        cost: Anzahl der Credits, die abgezogen werden sollen
        session_id: ID der Session (optional)
        function_name: Name der aufrufenden Funktion (optional)

    Returns:
        True bei Erfolg, False bei Fehler
    """
    if not user_id:
        # Ohne Benutzer-ID können wir keine Credits abziehen
        return False

    try:
        user = User.query.get(user_id)
        if not user:
            logger.warning("Benutzer %s nicht gefunden für Credits-Abzug", user_id)
            return False

        if user.credits < cost:
            logger.warning("Benutzer %s hat nicht genügend Credits: %s < %s", user_id, user.credits, cost)
            return False

        # Credits abziehen
        user.credits -= cost
        db.session.commit()

        logger.info("Credits abgezogen: %s von Benutzer %s, neue Bilanz: %s", cost, user_id, user.credits)
        return True
    except Exception as e:
        logger.error("Fehler beim Abziehen von Credits: %s", str(e))
        db.session.rollback()
        return False


def get_user_credits(user_id: str) -> int:
    """
    Gibt die aktuelle Anzahl der Credits eines Benutzers zurück.

    Args:
        user_id: ID des Benutzers

    Returns:
        Anzahl der Credits oder 0 bei Fehler
    """
    try:
        user = User.query.get(user_id)
        if not user:
            logger.warning("Benutzer %s nicht gefunden für Credits-Abfrage", user_id)
            return 0

        return user.credits
    except Exception as e:
        logger.error("Fehler bei der Credits-Abfrage: %s", str(e))
        return 0

# OpenAI-Client-Funktionen


def get_openai_client() -> OpenAI:
    """
    Holt oder erstellt einen OpenAI-Client für den aktuellen Thread.

    Returns:
        OpenAI: Eine thread-lokale OpenAI-Client-Instanz
    """
    if not hasattr(_thread_local, 'client'):
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY nicht konfiguriert")

        # Client mit angepassten Timeout-Einstellungen erstellen
        _thread_local.client = OpenAI(
            api_key=api_key,
            timeout=MAX_TIMEOUT,
            max_retries=MAX_RETRIES,
            default_headers={
                "OpenAI-Beta": "assistants=v2"
            }
        )

    return _thread_local.client

# Backoff-Decorator für API-Aufrufe


def with_backoff(max_tries: int = MAX_RETRIES + 1):
    """
    Decorator für API-Aufrufe mit exponentiellen Backoff.

    Args:
        max_tries: Maximale Anzahl von Versuchen

    Returns:
        Decorator-Funktion
    """
    def decorator(func):
        @backoff.on_exception(
            backoff.expo,
            (APIError, APITimeoutError, RateLimitError),
            max_tries=max_tries,
            giveup=lambda e: isinstance(e, RateLimitError) and "exceeded your quota" in str(e),
            on_backoff=lambda details: logger.warning(
                f"Wiederhole OpenAI-Anfrage nach {details['wait']:.1f}s "
                f"(Versuch {details['tries']}/{max_tries})"
            )
        )
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


@with_backoff()
def chat_completion(model: str, messages: List[Dict], user_id: Optional[str] = None,
                    session_id: Optional[str] = None, function_name: Optional[str] = None,
                    use_cache: bool = True, **kwargs) -> Dict[str, Any]:
    """
    Führt eine OpenAI-Chat-Completion durch mit Caching, Fehlerbehandlung und Token-Tracking.

    Args:
        model: Modellname
        messages: Liste von Nachrichten
        user_id: ID des Benutzers für Tracking (optional)
        session_id: ID der Session für Tracking (optional)
        function_name: Name der aufrufenden Funktion (optional)
        use_cache: Ob der Cache verwendet werden soll
        **kwargs: Weitere Parameter für die OpenAI-API

    Returns:
        Die OpenAI-Antwort als Dictionary
    """
    # Cache initialisieren
    cache = OpenAICache()

    # Cache-Schlüssel generieren
    cache_key = cache.generate_key(model, messages, **kwargs)

    # Prüfe, ob der Cache aktiviert ist und ob die Antwort im Cache ist
    if use_cache:
        cached_response = cache.get(cache_key)
        if cached_response:
            # Token-Nutzung für gecachte Antwort tracken
            try:
                # Token-Zählung aus der gecachten Antwort extrahieren
                input_tokens = cached_response.get('usage', {}).get('prompt_tokens', 0)
                output_tokens = cached_response.get('usage', {}).get('completion_tokens', 0)

                # Wenn keine Token-Zählung verfügbar, schätzen wir sie
                if input_tokens == 0:
                    input_tokens = count_tokens(messages, model)

                if output_tokens == 0 and 'choices' in cached_response:
                    content = cached_response['choices'][0].get('message', {}).get('content', '')
                    output_tokens = count_tokens(content, model)

                # Token-Nutzung tracken mit reduziertem Preis
                track_token_usage(
                    user_id=user_id,
                    session_id=session_id,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    function_name=function_name,
                    cached=True
                )
            except Exception as e:
                logger.warning("Fehler beim Tracking der Cache-Nutzung: %s", e)

            # Gibt die gecachte Antwort zurück
            return cached_response

    # Client abrufen
    client = get_openai_client()

    # Metadata für Anfrage speichern
    metadata = {
        "model": model,
        "request_time": datetime.now().isoformat(),
        "message_count": len(messages),
        **{k: v for k, v in kwargs.items() if isinstance(v, (str, int, float, bool))}
    }

    start_time = time.time()
    try:
        # Anfrage an OpenAI senden
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )

        # Zeitmessung für Anfrage
        request_time = time.time() - start_time

        # Response in Dict umwandeln
        response_dict = response.model_dump()

        # Im Cache speichern, wenn aktiviert
        if use_cache:
            cache.set(cache_key, response_dict)

        # Token-Nutzung tracken
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

        # Füge zeitbezogene Metadaten hinzu
        metadata.update({
            "request_duration_ms": int(request_time * 1000),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        })

        track_token_usage(
            user_id=user_id,
            session_id=session_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            function_name=function_name,
            cached=False,
            metadata=metadata
        )

        # Erfolgreiche Anfrage protokollieren
        logger.info(
            f"OpenAI-Anfrage erfolgreich: Modell={model}, "
            f"Tokens={input_tokens}+{output_tokens}, "
            f"Zeit={int(request_time * 1000)}ms"
        )

        return response_dict

    except Exception as e:
        # Fehler protokollieren
        error_time = time.time() - start_time
        logger.error("Fehler bei OpenAI-Anfrage: %s: %s", type(e).__name__, e)

        # Füge Fehlerinformationen zu Metadaten hinzu
        metadata.update({
            "error_type": type(e).__name__,
            "error_message": str(e),
            "error_time_ms": int(error_time * 1000)
        })

        # Tracke Token-Nutzung für fehlgeschlagene Anfragen (schätze Tokens)
        try:
            estimated_tokens = count_tokens(messages, model)
            track_token_usage(
                user_id=user_id,
                session_id=session_id,
                model=model,
                input_tokens=estimated_tokens,
                output_tokens=0,  # Keine Output-Tokens bei Fehler
                function_name=function_name,
                cached=False,
                metadata=metadata
            )
        except Exception as track_error:
            logger.warning("Fehler beim Tracking der fehlgeschlagenen Anfrage: %s", track_error)

        # Weitergabe des Fehlers
        raise


def extract_content_from_response(response: Dict[str, Any]) -> str:
    """
    Extrahiert den Text aus einer OpenAI-Antwort.

    Args:
        response: Die OpenAI-Antwort

    Returns:
        Der extrahierte Text
    """
    try:
        if isinstance(response, str):
            return response

        # Struktur der Antwort prüfen
        if 'choices' in response and len(response['choices']) > 0:
            choice = response['choices'][0]

            # Format vom API v1
            if 'message' in choice and 'content' in choice['message']:
                return choice['message']['content'] or ""

            # Alternatives Format
            if 'text' in choice:
                return choice['text'] or ""

        # Wenn nichts gefunden wurde, gib einen leeren String zurück
        return ""
    except Exception as e:
        logger.error("Fehler beim Extrahieren des Inhalts: %s", str(e))
        return ""


def clear_cache(pattern: str = "openai:chat:*") -> int:
    """
    Löscht alle Cache-Einträge, die dem Muster entsprechen.

    Args:
        pattern: Redis-Schlüsselmuster zum Löschen

    Returns:
        Anzahl der gelöschten Einträge
    """
    cache = OpenAICache()
    return cache.clear(pattern)


def get_usage_stats(user_id: Optional[str] = None,
                    start_time: Optional[datetime] = None,
                    end_time: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Gibt Nutzungsstatistiken für OpenAI-API-Aufrufe zurück.

    Args:
        user_id: ID des Benutzers (optional)
        start_time: Startzeit für die Statistik (optional)
        end_time: Endzeit für die Statistik (optional)

    Returns:
        Statistik-Dictionary
    """
    try:
        query = db.session.query(TokenUsage)

        if user_id:
            query = query.filter(TokenUsage.user_id == user_id)

        if start_time:
            query = query.filter(TokenUsage.timestamp >= start_time)

        if end_time:
            query = query.filter(TokenUsage.timestamp <= end_time)

        # Gesamtnutzung
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0
        cached_count = 0
        model_stats = {}

        for usage in query.all():
            total_input_tokens += usage.input_tokens
            total_output_tokens += usage.output_tokens
            total_cost += usage.cost

            if usage.cached:
                cached_count += 1

            model_name = usage.model
            if model_name not in model_stats:
                model_stats[model_name] = {
                    "count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost": 0
                }

            model_stats[model_name]["count"] += 1
            model_stats[model_name]["input_tokens"] += usage.input_tokens
            model_stats[model_name]["output_tokens"] += usage.output_tokens
            model_stats[model_name]["cost"] += usage.cost

        return {
            "total_requests": query.count(),
            "cached_requests": cached_count,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "total_cost": round(total_cost, 4),
            "model_stats": model_stats
        }

    except Exception as e:
        logger.error("Fehler beim Abrufen der Nutzungsstatistiken: %s", e)
        return {
            "error": str(e),
            "total_requests": 0
        }


# Exportiere alle wichtigen Funktionen und Klassen
__all__ = [
    'OpenAICache',
    'get_openai_client',
    'chat_completion',
    'extract_content_from_response',
    'clear_cache',
    'count_tokens',
    'calculate_token_cost',
    'track_token_usage',
    'check_credits_available',
    'deduct_credits',
    'get_user_credits',
    'get_usage_stats'
]
