"""
Token-Tracking-Logik für den Worker.
Kopiert und angepasst aus main/api/token_tracking.py
"""
import logging
import uuid
from datetime import datetime
import json

# Worker-spezifische Imports
from tasks.models import TokenUsage, User, get_db_session # Nutze Worker-Modelle und DB Session

logger = logging.getLogger(__name__)

# Kosten pro 1000 Tokens (in Credits) - Konsistent halten mit Main!
# Sollte idealerweise aus einer zentralen Konfigurationsquelle kommen.
GPT4_INPUT_COST_PER_1K = 10
GPT4_OUTPUT_COST_PER_1K = 30
GPT35_INPUT_COST_PER_1K = 1.5
GPT35_OUTPUT_COST_PER_1K = 2

def calculate_token_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Berechnet die Kosten in Credits basierend auf dem Modell und den Tokens."""
    cost = 0.0
    model_lower = model.lower()
    
    # Vereinfachte Kostenberechnung (Modellnamen anpassen!)
    if 'gpt-4'.casefold() in model_lower:
        cost = (input_tokens / 1000 * GPT4_INPUT_COST_PER_1K) + (output_tokens / 1000 * GPT4_OUTPUT_COST_PER_1K)
    elif 'gpt-3.5-turbo'.casefold() in model_lower:
        cost = (input_tokens / 1000 * GPT35_INPUT_COST_PER_1K) + (output_tokens / 1000 * GPT35_OUTPUT_COST_PER_1K)
    else:
        # Fallback oder Kosten für andere Modelle
        logger.warning(f"Unbekanntes Modell '{model}' für Kostenberechnung, verwende gpt-3.5 Kosten.")
        cost = (input_tokens / 1000 * GPT35_INPUT_COST_PER_1K) + (output_tokens / 1000 * GPT35_OUTPUT_COST_PER_1K)
        
    return max(1, round(cost)) # Mindestens 1 Credit, aufrunden

def update_token_usage(user_id: str, session_id: str, input_tokens: int, output_tokens: int, model: str,
                       endpoint: str = None, function_name: str = None, is_cached: bool = False, metadata: dict = None) -> dict:
    """
    Aktualisiert die Token-Nutzungsstatistik für einen Benutzer und zieht die Credits ab.
    Verwendet die Worker-DB-Session.
    """
    db_session = None
    credits_cost = 0 # Sicherstellen, dass definiert
    try:
        db_session = get_db_session()
        
        # Kosten berechnen
        credits_cost = calculate_token_cost(model=model, input_tokens=input_tokens, output_tokens=output_tokens)

        user = db_session.query(User).get(user_id)
        if not user:
            logger.warning(f"[Token Worker] Benutzer {user_id} nicht gefunden.")
            # Hier keinen Fehler werfen, nur loggen und Nutzungsdaten trotzdem speichern?
            # Oder Fehler zurückgeben? Fürs Erste: Speichern ohne Credit-Abzug.
            user_credits = None
        else:
            user_credits = user.credits
            # Wenn User gefunden, Credits prüfen und abziehen
            if user_credits is not None and user_credits < credits_cost:
                logger.warning(f"[Token Worker] Benutzer {user_id} hat nicht genügend Credits: {user_credits} < {credits_cost}. Token-Nutzung wird trotzdem gespeichert.")
                # Credits nicht abziehen, aber Nutzung speichern
            elif user_credits is not None:
                user.credits -= credits_cost
                logger.info(f"[Token Worker] Credits abgezogen: {credits_cost} von Benutzer {user_id}, neue Bilanz: {user.credits}")
            else:
                logger.warning(f"[Token Worker] Credit-Anzahl für Benutzer {user_id} ist None. Kann Credits nicht abziehen.")

        # Token-Nutzung speichern
        token_usage = TokenUsage(
            id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id, # Session ID aus Main übergeben?
            timestamp=datetime.utcnow(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=credits_cost,
            endpoint=endpoint or "worker_task",
            function_name=function_name or "unknown_ai_task",
            cached=is_cached,
            request_metadata=metadata
        )
        db_session.add(token_usage)
        db_session.commit()

        logger.info(f"[Token Worker] Token-Nutzung für User {user_id} gespeichert (ID: {token_usage.id}). Kosten: {credits_cost}")

        return {
            "success": True,
            "credits_cost": credits_cost,
            "remaining_credits": user.credits if user else None,
            "token_usage_id": token_usage.id
        }

    except Exception as e:
        logger.error(f"[Token Worker] Fehler beim Aktualisieren der Token-Nutzung für User {user_id}: {e}", exc_info=True)
        if db_session:
            db_session.rollback()
        return {
            "success": False,
            "error": str(e),
            "credits_cost": credits_cost 
        }
    finally:
        if db_session:
            db_session.close() 