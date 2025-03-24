"""
Verbessertes Token-Tracking-System für die Monetarisierung
-----------------------------------------------------------
Dieses Modul stellt erweiterte Funktionen für das Token-Tracking und die Credit-Berechnung bereit.
Es verfolgt den Input- und Output-Tokenverbrauch jeder Funktion und speichert sie in der Datenbank.

Seit dem Update: Dieses Modul integriert sich mit dem openaicache/token_tracker.py-System für Redis-basiertes
Caching und verbessertes Token-Tracking.
"""

from flask import current_app, g, jsonify
from . import api_bp
from .auth import token_required
from openaicache.token_tracker import update_token_usage
from core.models import db, User, TokenUsage
import tiktoken
import logging
import math
import uuid
import os
import time
import json
import threading
import inspect
import traceback

# Lokales Caching von Kosten für höhere Leistung
_pricing_cache = {}

# Integriere mit dem neuen Caching-System für Kostenberechnung und Token-Tracking
try:
    from openaicache import calculate_token_cost as cache_calculate_token_cost
    from openaicache import track_token_usage as cache_track_token_usage
    _use_redis_cache = True
    logging.info("Redis-Cache für Token-Tracking aktiviert")
except ImportError:
    _use_redis_cache = False
    logging.warning("Redis-Cache für Token-Tracking nicht verfügbar")

logger = logging.getLogger(__name__)

# Kosten pro 1000 Tokens (in Credits) - aus credit_service.py übernommen
GPT4_INPUT_COST_PER_1K = 10
GPT4_OUTPUT_COST_PER_1K = 30
GPT35_INPUT_COST_PER_1K = 1.5
GPT35_OUTPUT_COST_PER_1K = 2

def count_tokens(text, model="gpt-4o"):
    """
    Zählt die Tokens in einem Text für ein bestimmtes Modell
    
    Args:
        text (str): Der zu zählende Text
        model (str): Das Modell, für das die Tokens gezählt werden sollen
        
    Returns:
        int: Die Anzahl der Tokens
    """
    if not text:
        return 0
        
    try:
        encoder = tiktoken.encoding_for_model(model)
        token_count = len(encoder.encode(text))
        logger.info(f"Tiktoken-Zählung: {token_count} Tokens für {len(text)} Zeichen")
        return token_count
    except Exception as e:
        logger.warning(f"Fehler beim Zählen der Tokens mit tiktoken: {str(e)}")
        # Fallback: Ungefähre Schätzung (1 Token ≈ 4 Zeichen)
        fallback_count = len(text) // 4
        logger.warning(f"Fallback-Zählung verwendet: {fallback_count} Tokens (ca.)")
        return fallback_count

def calculate_token_cost(input_tokens, output_tokens, model="gpt-4o", document_tokens=None):
    """
    Berechnet die Kosten basierend auf Token-Anzahl und Modell.
    
    Args:
        input_tokens (int): Anzahl der Input-Token
        output_tokens (int): Anzahl der Output-Token
        model (str): Das verwendete OpenAI-Modell
        document_tokens (int, optional): Die tatsächliche Anzahl der Tokens im Dokument (ohne Systemprompt)
        
    Returns:
        int: Kosten in Credits (gerundet auf die nächste ganze Zahl)
    """
    # WICHTIG: Nicht mehr auf das Cache-System verweisen, um Rekursion zu vermeiden
    # Verwende direkt die bestehende Logik
    
    # Für sehr kleine Dokumente (<500 Tokens), unabhängig vom Gesamtprompt
    if input_tokens < 500:
        return 100  # Pauschale Mindestgebühr für kleine Dokumente
        
    # Für mittlere Dokumente (500-3000 Tokens)
    if input_tokens < 3000:
        return 200  # Pauschale Gebühr für mittlere Dokumente
    
    # Basis-Kosten pro 1000 Token
    if model.startswith("gpt-4"):
        input_cost_per_1k = 150  # 15 Credits pro 1000 Tokens (Entspricht 15.000 für 100.000)
        output_cost_per_1k = 300  # 30 Credits pro 1000 Tokens
    else:  # GPT-3.5
        input_cost_per_1k = 15  # 1,5 Credits pro 1000 Tokens
        output_cost_per_1k = 20  # 2 Credits pro 1000 Tokens
    
    # Direkte Berechnung der Kosten basierend auf Token-Anzahl
    input_cost = (input_tokens / 1000) * input_cost_per_1k
    output_cost = (output_tokens / 1000) * output_cost_per_1k
    
    # Gesamtkosten berechnen und auf die nächste ganze Zahl aufrunden
    total_cost = math.ceil(input_cost + output_cost)
    
    # Mindestkosten von 100 Credits pro API-Aufruf für größere Dokumente
    return max(100, total_cost)

def track_token_usage(user_id, session_id, function_name, input_tokens, output_tokens, model="gpt-4o", details=None):
    """
    Verfolgt die Token-Nutzung für einen bestimmten Benutzer und eine Funktion.
    
    Args:
        user_id (str): Die ID des Benutzers
        session_id (str): Die ID der Session
        function_name (str): Der Name der Funktion, die die Tokens verwendet hat
        input_tokens (int): Die Anzahl der Input-Tokens
        output_tokens (int): Die Anzahl der Output-Tokens
        model (str): Das verwendete OpenAI-Modell
        details (dict, optional): Zusätzliche Details zur Anfrage
        
    Returns:
        bool: True, wenn das Tracking erfolgreich war, False sonst
    """
    try:
        # Logging für Tracking-Informationen
        logger.info(f"Token-Tracking für Benutzer {user_id} (Funktion: {function_name}): Input={input_tokens}, Output={output_tokens}, Modell={model}")
        
        # Wenn details vorhanden sind, logge eine Zusammenfassung
        if details:
            # Extrahiere wichtige Informationen aus details, falls vorhanden
            prompt_info = f"Prompt: {details.get('prompt_length', '?')} Zeichen" if 'prompt_length' in details else ""
            response_info = f"Antwort: {details.get('response_length', '?')} Zeichen" if 'response_length' in details else ""
            
            if prompt_info or response_info:
                logger.info(f"Details für {function_name}: {prompt_info}, {response_info}")
                
            # Wenn der Prompt oder die Antwort in den Details enthalten sind, zeige Ausschnitte an
            if 'prompt' in details:
                prompt = details['prompt']
                logger.info(f"Prompt-Ausschnitt: {prompt[:500]}...")
                
            if 'response' in details:
                response = details['response']
                logger.info(f"Antwort-Ausschnitt: {response[:500]}...")
        
        # Wenn Redis-Cache aktiviert ist, nutze das externe Tracking-System
        if _use_redis_cache:
            try:
                # Erstelle ein eindeutiges Token für das Tracking
                tracking_id = str(uuid.uuid4())
                details_for_cache = details or {}
                
                # Zusätzliche Details für das Caching
                details_for_cache.update({
                    "tracking_id": tracking_id,
                    "timestamp": time.time(),
                    "user_id": user_id,
                    "session_id": session_id,
                    "function": function_name
                })
                
                # Übergebe die Tracking-Daten an das Cache-System
                tracking_result = cache_track_token_usage(
                    session_id=session_id,
                    function_name=function_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=model,
                    details=details_for_cache
                )
                
                # Protokolliere das Ergebnis des Cachings
                if isinstance(tracking_result, dict) and tracking_result.get('success'):
                    logger.info(f"Token-Tracking für {tracking_id} erfolgreich im Redis-Cache gespeichert")
                else:
                    logger.warning(f"Token-Tracking für {tracking_id} konnte nicht im Redis-Cache gespeichert werden")
                
                return True
                
            except Exception as cache_err:
                logger.error(f"Fehler beim Redis-Cache-Tracking: {str(cache_err)}")
                # Fallback auf DB-Tracking
        
        # Speichere die Token-Nutzung in der Datenbank
        try:
            from core.models import TokenUsage, db
            
            # Berechne die Kosten in Credits
            cost = calculate_token_cost(input_tokens, output_tokens, model)
            
            # Erstelle einen neuen TokenUsage-Eintrag
            usage = TokenUsage(
                user_id=user_id,
                session_id=session_id,
                function_name=function_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
                credits_cost=cost,
                details=json.dumps(details) if details else None
            )
            
            db.session.add(usage)
            db.session.commit()
            
            logger.info(f"Token-Nutzung in Datenbank gespeichert: {cost} Credits für {function_name}")
            return True
            
        except Exception as db_err:
            logger.error(f"Fehler beim Speichern der Token-Nutzung in der Datenbank: {str(db_err)}")
            return False
            
    except Exception as e:
        logger.error(f"Fehler beim Token-Tracking: {str(e)}")
        return False

def check_credits_available(cost, user_id=None):
    """
    Überprüft, ob der Benutzer genügend Credits hat, ohne sie abzuziehen
    
    Args:
        cost (int): Anzahl der Credits, die benötigt werden
        user_id (str, optional): Die ID des Benutzers (falls nicht in g.user)
        
    Returns:
        bool: True, wenn genügend Credits vorhanden sind, False sonst
    """
    # Wenn eine spezifische Benutzer-ID angegeben wurde, verwende diese
    if user_id:
        user = User.query.get(user_id)
        if not user:
            return False
        return user.credits >= cost
    
    # Ansonsten den aktuellen Benutzer aus g verwenden
    if not hasattr(g, 'user') or not g.user:
        return False
    
    user_id = g.user.id
    user = User.query.get(user_id)
    
    if not user:
        return False
    
    return user.credits >= cost

def update_user_credits(user_id, credit_change):
    """
    Aktualisiert die Credits eines Benutzers und gibt den neuen Stand zurück.
    
    Args:
        user_id (str): Die ID des Benutzers
        credit_change (int): Die Änderung der Credits (positiv für Hinzufügen, negativ für Abziehen)
        
    Returns:
        int: Der neue Credit-Stand des Benutzers oder None bei Fehler
    """
    try:
        from core.models import User, db
        
        user = User.query.get(user_id)
        if not user:
            logger.error(f"Benutzer mit ID {user_id} nicht gefunden")
            return None
        
        # Überprüfe, ob der Benutzer genügend Credits hat, wenn credits_change negativ ist
        if credit_change < 0 and user.credits < abs(credit_change):
            logger.warning(f"Benutzer {user_id} hat nicht genügend Credits: {user.credits}/{abs(credit_change)}")
            return user.credits  # Keine Änderung vorgenommen
        
        # Credits aktualisieren
        user.credits += credit_change
        db.session.commit()
        
        logger.info(f"Benutzer {user_id}: {credit_change} Credits geändert, neuer Stand: {user.credits}")
        
        return user.credits
        
    except Exception as e:
        logger.error(f"Fehler beim Aktualisieren der Credits: {str(e)}")
        if 'db' in locals():
            db.session.rollback()
        return None

def deduct_credits(user_id, credits, session_id=None, function_name="unspecified", input_tokens=0, output_tokens=0, model="gpt-4o"):
    """
    Zieht Credits vom Benutzer ab und führt gleichzeitig Token-Tracking durch.
    
    Args:
        user_id (str): Die ID des Benutzers
        credits (int): Die abzuziehenden Credits
        session_id (str, optional): Die ID der Session
        function_name (str): Der Name der Funktion für das Token-Tracking
        input_tokens (int): Die Anzahl der Input-Tokens
        output_tokens (int): Die Anzahl der Output-Tokens
        model (str): Das verwendete OpenAI-Modell
        
    Returns:
        dict: {"success": bool, "credits_remaining": int, "error": str}
    """
    try:
        from core.models import User
        from flask import current_app, g
        
        # Tracking der Token-Nutzung
        if input_tokens > 0 or output_tokens > 0:
            tracking_result = track_token_usage(
                user_id=user_id,
                session_id=session_id,
                function_name=function_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model
            )
            
            if not tracking_result:
                logger.warning("Token-Tracking fehlgeschlagen")
        
        return {
            "success": True,
            "credits_remaining": update_user_credits(user_id, -credits),
            "error": None
        }
    except Exception as e:
        logger.error(f"Fehler beim Abziehen von Credits: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "credits_remaining": None
        }

def estimate_token_usage(text_length, model="gpt-4o", is_prompt=True):
    """
    Schätzt die Token-Anzahl basierend auf der Textlänge
    
    Args:
        text_length (int): Die Länge des Textes in Zeichen
        model (str): Das verwendete Modell
        is_prompt (bool): Ob es sich um einen Prompt handelt
        
    Returns:
        int: Geschätzte Anzahl an Tokens
    """
    # Ein Token entspricht ca. 4 Zeichen in englischem Text
    # Für Prompts rechnen wir konservativ, um Überschätzungen zu vermeiden
    chars_per_token = 4 if is_prompt else 3.5
    
    return int(text_length / chars_per_token)

def get_openai_client(use_cache=False):
    """
    Gibt einen OpenAI-Client zurück, der für Token-Tracking konfiguriert ist.
    
    Args:
        use_cache: Boolean, ob der Cache verwendet werden soll
        
    Returns:
        OpenAI: Ein OpenAI-Client mit Token-Tracking-Wrapper
    """
    from flask import current_app, g
    import os
    import logging
    import time
    
    logger = logging.getLogger(__name__)
    
    # DEBUG: Protokolliere detaillierte Umgebungsinformationen 
    start_time = time.time()
    caller_info = "unbekannt"
    try:
        # Versuche, den Aufrufer der Funktion zu identifizieren
        frame = inspect.currentframe().f_back
        if frame:
            caller_module = frame.f_globals.get('__name__', 'unbekannt')
            caller_function = frame.f_code.co_name
            caller_info = f"{caller_module}.{caller_function}"
    except:
        pass
    
    logger.critical(f"[DEBUG-TOKEN] get_openai_client aufgerufen mit use_cache={use_cache} von {caller_info}")
    logger.critical(f"[DEBUG-TOKEN] PID: {os.getpid()}, Zeit: {time.strftime('%H:%M:%S')}")
    logger.critical(f"[DEBUG-TOKEN] Umgebungsvariablen: OPENAI_API_KEY existiert: {'Ja' if 'OPENAI_API_KEY' in os.environ else 'Nein'}")
    
    # Falls möglich, info über App-Kontext
    try:
        if current_app:
            logger.critical(f"[DEBUG-TOKEN] Flask App-Kontext: {current_app._get_current_object()}")
            logger.critical(f"[DEBUG-TOKEN] App Config: {list(current_app.config.keys())}")
            if 'OPENAI_API_KEY' in current_app.config:
                logger.critical(f"[DEBUG-TOKEN] OPENAI_API_KEY in Config: vorhanden")
            else:
                logger.critical(f"[DEBUG-TOKEN] OPENAI_API_KEY in Config: FEHLT")
        else:
            logger.critical("[DEBUG-TOKEN] Kein Flask App-Kontext vorhanden")
    except Exception as e:
        logger.critical(f"[DEBUG-TOKEN] Fehler beim Zugriff auf Flask App-Kontext: {str(e)}")
    
    # Hole den API-Schlüssel aus verschiedenen Quellen
    api_key = None
    sources = [
        ('current_app.config', lambda: current_app.config.get('OPENAI_API_KEY')),
        ('os.environ', lambda: os.environ.get('OPENAI_API_KEY')),
    ]
    
    # Protokolliere Debugging-Informationen zur API-Schlüssel-Suche
    for source_name, getter in sources:
        try:
            key = getter()
            logger.critical(f"[DEBUG-TOKEN] Versuche API-Schlüssel aus {source_name} zu laden...")
            if key:
                api_key = key
                logger.critical(f"[DEBUG-TOKEN] API-Schlüssel in {source_name} gefunden!")
                logger.critical(f"[DEBUG-TOKEN] Schlüssel-Länge: {len(api_key)} Zeichen")
                logger.critical(f"[DEBUG-TOKEN] Erste 3 Zeichen: {api_key[:3]}")
                break
            else:
                logger.critical(f"[DEBUG-TOKEN] Kein API-Schlüssel in {source_name}")
        except Exception as e:
            logger.critical(f"[DEBUG-TOKEN] Fehler beim Lesen aus {source_name}: {str(e)}")
            logger.critical(f"[DEBUG-TOKEN] Stacktrace: {traceback.format_exc()}")
    
    if not api_key:
        logger.critical("[DEBUG-TOKEN] FATALER FEHLER: Kein API-Schlüssel gefunden!")
        logger.critical("[DEBUG-TOKEN] Alle Quellen durchsucht, kein Schlüssel vorhanden. Dies wird zu einem Fehler führen.")
        raise ValueError("OpenAI API-Schlüssel fehlt. Bitte konfigurieren Sie den Schlüssel in der Umgebungsvariable OPENAI_API_KEY oder der App-Konfiguration.")
    
    # Protokolliere Schlüsselvorhandensein (nicht den gesamten Schlüssel!)
    logger.critical(f"[DEBUG-TOKEN] API-Schlüssel Vorhandensein: {'Ja, gefunden' if api_key else 'FEHLT'}")
    if api_key:
        logger.critical(f"[DEBUG-TOKEN] API-Schlüssel-Typ: {type(api_key)}")
        logger.critical(f"[DEBUG-TOKEN] API-Schlüssel-Länge: {len(api_key)} Zeichen")
        logger.critical(f"[DEBUG-TOKEN] API-Schlüssel Anfangsbuchstaben: {api_key[:3]}...")
        logger.critical(f"[DEBUG-TOKEN] API-Schlüssel Endbuchstaben: ...{api_key[-3:]}")
    
    # Erstelle den OpenAI-Client
    try:
        logger.critical("[DEBUG-TOKEN] Importiere OpenAI und Cache-Module...")
        from openai import OpenAI
        logger.critical("[DEBUG-TOKEN] OpenAI Modul erfolgreich importiert")
        
        try:
            from openaicache.openai_wrapper import CachedOpenAI
            logger.critical("[DEBUG-TOKEN] CachedOpenAI Modul erfolgreich importiert")
            cache_available = True
        except ImportError as e:
            logger.critical(f"[DEBUG-TOKEN] Fehler beim Import von CachedOpenAI: {str(e)}")
            cache_available = False
        
        # Wenn Cache nicht verfügbar ist, deaktiviere ihn
        if not cache_available:
            use_cache = False
            logger.critical("[DEBUG-TOKEN] Cache deaktiviert, da Module nicht verfügbar sind")
        
        # Prüfe, ob der Cache aktiviert werden soll
        if use_cache and cache_available:
            # Erstelle einen OpenAI-Client mit Cache
            logger.critical("[DEBUG-TOKEN] Erstelle CachedOpenAI-Client...")
            try:
                # Erstelle zuerst einen regulären Client zum Testen
                logger.critical("[DEBUG-TOKEN] Erstelle Test-Client für Verfügbarkeitsprüfung...")
                test_client = OpenAI(api_key=api_key)
                logger.critical(f"[DEBUG-TOKEN] Test-Client erstellt: {type(test_client)}")
                
                # Prüfe, ob der Test-Client funktioniert
                logger.critical("[DEBUG-TOKEN] Prüfe, ob der Test-Client funktioniert...")
                if hasattr(test_client, 'api_key'):
                    logger.critical("[DEBUG-TOKEN] Test-Client hat API-Schlüssel-Attribut")
                else:
                    logger.critical("[DEBUG-TOKEN] ACHTUNG: Test-Client hat KEIN API-Schlüssel-Attribut")
                
                # Wenn der Test-Client funktioniert, erstelle den Cache-Client
                logger.critical("[DEBUG-TOKEN] Erstelle Base-Client für CachedOpenAI...")
                base_client = OpenAI(api_key=api_key)
                logger.critical("[DEBUG-TOKEN] Erstelle CachedOpenAI mit Base-Client...")
                
                user_id_for_cache = getattr(g, 'user_id', 'Anonymous')
                logger.critical(f"[DEBUG-TOKEN] User-ID für Cache: {user_id_for_cache}")
                
                client = CachedOpenAI(base_client=base_client, user_id=user_id_for_cache)
                logger.critical(f"[DEBUG-TOKEN] CachedOpenAI-Client erstellt: {type(client)}")
                
                if hasattr(client, 'base_client') and hasattr(client.base_client, 'api_key'):
                    logger.critical(f"[DEBUG-TOKEN] API-Schlüssel im Client: vorhanden")
                else:
                    logger.critical(f"[DEBUG-TOKEN] ACHTUNG: API-Schlüssel im Client: FEHLT")
                
                end_time = time.time()
                logger.critical(f"[DEBUG-TOKEN] Client-Erstellung abgeschlossen in {end_time - start_time:.2f} Sekunden")
                
                return client
            except Exception as e:
                logger.critical(f"[DEBUG-TOKEN] Fehler beim Erstellen des CachedOpenAI-Clients: {str(e)}")
                logger.critical(f"[DEBUG-TOKEN] Stacktrace: {traceback.format_exc()}")
                logger.critical("[DEBUG-TOKEN] Fallback auf regulären OpenAI-Client...")
        
        # Erstelle einen regulären OpenAI-Client, wenn Cache nicht aktiviert oder fehlgeschlagen ist
        try:
            # Erstelle einen direkten OpenAI-Client
            logger.critical("[DEBUG-TOKEN] Erstelle regulären OpenAI-Client...")
            client = OpenAI(api_key=api_key)
            logger.critical(f"[DEBUG-TOKEN] Regulärer OpenAI-Client erstellt: {type(client)}")
            
            if hasattr(client, 'api_key'):
                logger.critical(f"[DEBUG-TOKEN] API-Schlüssel im Client: vorhanden")
            else:
                logger.critical(f"[DEBUG-TOKEN] ACHTUNG: API-Schlüssel im Client: FEHLT")
                
            # Log client details
            logger.critical(f"[DEBUG-TOKEN] Client Attribute: {dir(client)}")
            if hasattr(client, 'base_url'):
                logger.critical(f"[DEBUG-TOKEN] Client Base URL: {client.base_url}")
            
            end_time = time.time()
            logger.critical(f"[DEBUG-TOKEN] Client-Erstellung abgeschlossen in {end_time - start_time:.2f} Sekunden")
            
            return client
        except Exception as e:
            logger.critical(f"[DEBUG-TOKEN] Kritischer Fehler beim Erstellen des OpenAI-Clients: {str(e)}")
            logger.critical(f"[DEBUG-TOKEN] Stacktrace: {traceback.format_exc()}")
            raise
    except ImportError as e:
        logger.critical(f"[DEBUG-TOKEN] Import-Fehler: {str(e)}")
        logger.critical(f"[DEBUG-TOKEN] Stacktrace: {traceback.format_exc()}")
        raise ValueError(f"Erforderliche Bibliotheken fehlen: {str(e)}")
    except Exception as e:
        logger.critical(f"[DEBUG-TOKEN] Unerwarteter Fehler: {str(e)}")
        logger.critical(f"[DEBUG-TOKEN] Stacktrace: {traceback.format_exc()}")
        raise 