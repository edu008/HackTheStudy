"""
Token-Nutzungsstatistiken für das Admin-Modul.
Enthält Funktionen zur Analyse und Überwachung der Token-Nutzung und -Kosten.
"""

import logging
from datetime import datetime, timedelta

from core.models import TokenUsage, User, db
from flask import jsonify, request
from openaicache.token_tracker import TokenTracker
from sqlalchemy import Float, cast, desc, func

# Logger konfigurieren
logger = logging.getLogger(__name__)


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
            db.func.count(TokenUsage.id).label('total_requests'),
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
            db_stats["requests"]["cache_hit_rate"] = (
                db_stats["requests"]["cached_requests"] / db_stats["requests"]["total_requests"]) * 100
        else:
            db_stats["requests"]["cache_hit_rate"] = 0

    except Exception as e:
        logger.error("Fehler beim Abrufen der Datenbankstatistiken: %s", str(e))
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
            db.func.count(TokenUsage.id).label('total_requests'),
            func.sum(cast(TokenUsage.cached, Float)).label('cached_requests')
        ).join(User, User.id == TokenUsage.user_id)

        if start_date:
            query = query.filter(TokenUsage.timestamp >= start_date)

        result = query.group_by(
            TokenUsage.user_id, User.email, User.name).order_by(
            desc('total_cost')).limit(limit).all()

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
                    "cache_hit_rate": (
                        (int(row.cached_requests or 0) / row.total_requests * 100) 
                        if row.total_requests > 0 else 0
                    )
                }
            })

        return jsonify({
            "success": True,
            "data": users
        })

    except Exception as e:
        logger.error("Fehler beim Abrufen der Top-Benutzer: %s", str(e))
        return jsonify({
            "success": False,
            "error": {"code": "DATABASE_ERROR", "message": str(e)}
        }), 500
