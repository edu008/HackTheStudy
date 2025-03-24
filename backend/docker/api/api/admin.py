from flask import Blueprint, jsonify, request, current_app, g
from functools import wraps
import os
import logging
from .auth import token_required
from core.models import db, User, TokenUsage
from openaicache.openai_wrapper import CachedOpenAI as OpenAICacheManager
from openaicache.token_tracker import TokenTracker
from sqlalchemy import func, cast, Float, desc
from datetime import datetime, timedelta
from api.log_utils import AppLogger
import json

# Blueprint erstellen und zentrale CORS-Konfiguration verwenden
admin_bp = Blueprint('admin', __name__)

logger = logging.getLogger(__name__)

def admin_required(f):
    """
    Dekorator, der überprüft, ob der aktuell authentifizierte Benutzer Admin ist.
    Verwendet token_required als Basis für die Authentifizierung.
    """
    @wraps(f)
    @token_required
    def decorated_function(*args, **kwargs):
        # Hier wurde bereits sichergestellt, dass ein Token gültig ist (durch token_required)
        # Prüfen, ob der Benutzer ein Admin ist
        admin_emails = os.getenv('ADMIN_EMAILS', '').strip().split(',')
        if g.user.email not in admin_emails:
            return jsonify({"success": False, "error": {"code": "NOT_AUTHORIZED", "message": "Admin access required"}}), 403
        
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/cache-stats', methods=['GET'])
@admin_required
def get_cache_stats():
    """
    Gibt Statistiken zum Redis-Cache für OpenAI-API-Anfragen zurück.
    """
    cache_stats = OpenAICacheManager.get_cache_stats()
    
    return jsonify({
        "success": True,
        "data": cache_stats
    })

@admin_bp.route('/token-stats', methods=['GET'])
@admin_required
def get_token_stats():
    """
    Gibt Statistiken zur Token-Nutzung zurück.
    """
    # Zeitraum aus Query-Parameter holen
    time_range = request.args.get('time_range', 'all')
    user_id = request.args.get('user_id')
    
    # Statistiken aus dem Redis-Cache holen
    redis_stats = TokenTracker.get_token_stats(user_id, time_range)
    
    # Statistiken aus der Datenbank holen
    db_stats = {}
    
    # Abfrage-Datum basierend auf dem Zeitraum festlegen
    start_date = None
    if time_range == 'day':
        start_date = datetime.utcnow() - timedelta(days=1)
    elif time_range == 'week':
        start_date = datetime.utcnow() - timedelta(weeks=1)
    elif time_range == 'month':
        start_date = datetime.utcnow() - timedelta(days=30)
    
    try:
        # Query für alle Einträge oder gefiltert nach Benutzer-ID und Zeitraum
        query = db.session.query(
            func.sum(TokenUsage.input_tokens).label('total_input_tokens'),
            func.sum(TokenUsage.output_tokens).label('total_output_tokens'),
            func.sum(TokenUsage.cost).label('total_cost'),
            func.count(TokenUsage.id).label('total_requests'),
            func.sum(cast(TokenUsage.cached, Float)).label('cached_requests')
        )
        
        if user_id:
            query = query.filter(TokenUsage.user_id == user_id)
        
        if start_date:
            query = query.filter(TokenUsage.timestamp >= start_date)
        
        result = query.one()
        
        db_stats = {
            "total_tokens": {
                "input": result.total_input_tokens or 0,
                "output": result.total_output_tokens or 0,
                "total": (result.total_input_tokens or 0) + (result.total_output_tokens or 0)
            },
            "costs": {
                "total_cost": float(result.total_cost or 0)
            },
            "requests": {
                "total_requests": result.total_requests or 0,
                "cached_requests": int(result.cached_requests or 0),
                "api_requests": (result.total_requests or 0) - int(result.cached_requests or 0)
            }
        }
        
        # Cache-Trefferquote berechnen
        if db_stats["requests"]["total_requests"] > 0:
            db_stats["requests"]["cache_hit_rate"] = (db_stats["requests"]["cached_requests"] / db_stats["requests"]["total_requests"]) * 100
        else:
            db_stats["requests"]["cache_hit_rate"] = 0
        
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Datenbankstatistiken: {str(e)}")
        db_stats = {
            "error": str(e),
            "total_tokens": {"input": 0, "output": 0, "total": 0},
            "costs": {"total_cost": 0},
            "requests": {"total_requests": 0, "cached_requests": 0, "api_requests": 0, "cache_hit_rate": 0}
        }
    
    return jsonify({
        "success": True,
        "data": {
            "redis_stats": redis_stats,
            "database_stats": db_stats
        }
    })

@admin_bp.route('/top-users', methods=['GET'])
@admin_required
def get_top_users():
    """
    Gibt die Top-Benutzer basierend auf Token-Nutzung und API-Aufrufen zurück.
    """
    # Zeitraum aus Query-Parameter holen
    time_range = request.args.get('time_range', 'month')
    limit = int(request.args.get('limit', 10))
    
    # Abfrage-Datum basierend auf dem Zeitraum festlegen
    start_date = None
    if time_range == 'day':
        start_date = datetime.utcnow() - timedelta(days=1)
    elif time_range == 'week':
        start_date = datetime.utcnow() - timedelta(weeks=1)
    elif time_range == 'month':
        start_date = datetime.utcnow() - timedelta(days=30)
    elif time_range == 'year':
        start_date = datetime.utcnow() - timedelta(days=365)
    
    try:
        # Query für Token-Nutzung pro Benutzer
        query = db.session.query(
            TokenUsage.user_id,
            User.email,
            User.name,
            func.sum(TokenUsage.input_tokens).label('total_input_tokens'),
            func.sum(TokenUsage.output_tokens).label('total_output_tokens'),
            func.sum(TokenUsage.cost).label('total_cost'),
            func.count(TokenUsage.id).label('total_requests'),
            func.sum(cast(TokenUsage.cached, Float)).label('cached_requests')
        ).join(User, User.id == TokenUsage.user_id)
        
        if start_date:
            query = query.filter(TokenUsage.timestamp >= start_date)
        
        result = query.group_by(TokenUsage.user_id, User.email, User.name).order_by(desc('total_cost')).limit(limit).all()
        
        users = []
        for row in result:
            users.append({
                "user_id": row.user_id,
                "email": row.email,
                "name": row.name,
                "tokens": {
                    "input": row.total_input_tokens,
                    "output": row.total_output_tokens,
                    "total": row.total_input_tokens + row.total_output_tokens
                },
                "cost": float(row.total_cost),
                "requests": {
                    "total": row.total_requests,
                    "cached": int(row.cached_requests or 0),
                    "api": row.total_requests - int(row.cached_requests or 0),
                    "cache_hit_rate": (int(row.cached_requests or 0) / row.total_requests * 100) if row.total_requests > 0 else 0
                }
            })
        
        return jsonify({
            "success": True,
            "data": users
        })
        
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Top-Benutzer: {str(e)}")
        return jsonify({
            "success": False,
            "error": {"code": "DATABASE_ERROR", "message": str(e)}
        }), 500

@admin_bp.route('/clear-cache', methods=['POST'])
@admin_required
def clear_cache():
    """
    Löscht den Redis-Cache für OpenAI-API-Anfragen.
    """
    try:
        deleted = OpenAICacheManager.clear_all_cache()
        
        return jsonify({
            "success": True,
            "data": {
                "deleted_entries": deleted,
                "message": f"{deleted} Cache-Einträge wurden gelöscht."
            }
        })
        
    except Exception as e:
        logger.error(f"Fehler beim Löschen des Caches: {str(e)}")
        return jsonify({
            "success": False,
            "error": {"code": "CACHE_ERROR", "message": str(e)}
        }), 500

@admin_bp.route('/debug/openai', methods=['POST'])
@admin_required
def toggle_openai_debug():
    """Aktiviert oder deaktiviert das OpenAI API-Debug-Logging."""
    data = request.get_json()
    enable = data.get('enable', True) if data else True
    
    # Debug-Logging aktivieren oder deaktivieren
    AppLogger.debug_openai_api(enable)
    
    return jsonify({
        "success": True,
        "message": f"OpenAI API Debug-Logging {'aktiviert' if enable else 'deaktiviert'}",
        "enabled": enable
    })

@admin_bp.route('/debug/openai-test', methods=['POST'])
@admin_required
def test_openai_api():
    """Sendet eine Test-Anfrage an die OpenAI API, um die Protokollierung zu testen."""
    import uuid
    from api.openai_client import OptimizedOpenAIClient
    from api.log_utils import AppLogger
    import logging
    
    # Temporäre Session-ID für das Tracking
    session_id = str(uuid.uuid4())
    logger = logging.getLogger(__name__)
    
    # Aktiviere Debug-Logging falls noch nicht aktiviert
    AppLogger.debug_openai_api(True)
    
    logger.info(f"Sende Test-Anfrage an OpenAI API mit Session-ID: {session_id}")
    
    try:
        client = OptimizedOpenAIClient()
        response = client.query(
            prompt="Sage 'Hallo Welt' und erkläre was ein Python-Logger ist.",
            system_content="Du bist ein hilfreicher Assistent, der Debugging-Tests durchführt.",
            session_id=session_id,
            function_name="test_openai_api"
        )
        
        return jsonify({
            "success": True,
            "message": "OpenAI API-Test erfolgreich",
            "response": response,
            "session_id": session_id
        })
    except Exception as e:
        logger.error(f"OpenAI API-Test fehlgeschlagen: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"OpenAI API-Test fehlgeschlagen: {str(e)}",
            "session_id": session_id
        }), 500

@admin_bp.route('/debug/openai-errors', methods=['GET'])
@admin_required
def get_openai_errors():
    """Ruft OpenAI-Fehler und -Anfragen aus Redis ab."""
    session_id = request.args.get('session_id')
    if not session_id:
        return jsonify({
            "success": False,
            "message": "session_id ist erforderlich"
        }), 400
    
    try:
        # Redis-Client importieren
        from tasks import redis_client
        
        # Alle relevanten OpenAI-Schlüssel für diese Session abrufen
        request_key = f"openai_last_request:{session_id}"
        response_key = f"openai_last_response:{session_id}"
        error_key = f"openai_error:{session_id}"
        error_details_key = f"error_details:{session_id}"
        
        # Daten aus Redis abrufen
        request_data = redis_client.get(request_key)
        response_data = redis_client.get(response_key)
        error_data = redis_client.get(error_key)
        error_details = redis_client.get(error_details_key)
        
        # JSON-Decode für alle Daten
        result = {
            "session_id": session_id,
            "last_request": json.loads(request_data.decode('utf-8')) if request_data else None,
            "last_response": json.loads(response_data.decode('utf-8')) if response_data else None,
            "openai_error": json.loads(error_data.decode('utf-8')) if error_data else None,
            "error_details": json.loads(error_details.decode('utf-8')) if error_details else None,
        }
        
        # Status-Informationen hinzufügen
        progress_key = f"processing_progress:{session_id}"
        status_key = f"processing_status:{session_id}"
        progress_data = redis_client.get(progress_key)
        status_data = redis_client.get(status_key)
        
        result["processing_progress"] = json.loads(progress_data.decode('utf-8')) if progress_data else None
        result["processing_status"] = status_data.decode('utf-8') if status_data else None
        
        return jsonify({
            "success": True,
            "data": result
        })
    except Exception as e:
        logger.error(f"Fehler beim Abrufen von OpenAI-Fehlern: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Fehler beim Abrufen von OpenAI-Fehlern: {str(e)}"
        }), 500 