"""
Controller-Funktionen für das Finanzmodul.
Enthält Funktionen zur Abfrage von Zahlungs- und Kreditinformationen.
"""

import logging
from datetime import datetime, timedelta

from core.models import Payment, TokenUsage, User, db
from flask import jsonify, request
from sqlalchemy import Float, case, cast, desc, func

# Logger konfigurieren
logger = logging.getLogger(__name__)


def get_user_credit_info():
    """
    Ruft die Kreditinformationen des aktuellen Benutzers ab.

    Returns:
        tuple: JSON-Antwort mit Kreditinformationen und HTTP-Statuscode
    """
    user = User.query.get(request.user_id)
    if not user:
        return jsonify({
            "success": False,
            "error": {"code": "USER_NOT_FOUND", "message": "User not found"}
        }), 404

    # Token-Nutzung des Benutzers abrufen
    try:
        # Abfrage-Datum für den letzten Monat festlegen
        month_ago = datetime.utcnow() - timedelta(days=30)

        # Token-Nutzung für den letzten Monat berechnen
        # Verwende case() für die Konvertierung von boolean nach numerisch
        usage_stats = db.session.query(
            func.sum(TokenUsage.input_tokens).label('total_input_tokens'),
            func.sum(TokenUsage.output_tokens).label('total_output_tokens'),
            func.sum(TokenUsage.cost).label('total_cost'),
            func.count().label('total_requests'),
            func.sum(case([(TokenUsage.cached == True, 1)], else_=0)).label('cached_requests')
        ).filter(
            TokenUsage.user_id == request.user_id,
            TokenUsage.timestamp >= month_ago
        ).one()

        # Zahlungen des Benutzers abrufen (letzte)
        last_payment = Payment.query.filter_by(
            user_id=request.user_id
        ).order_by(Payment.created_at.desc()).first()

        return jsonify({
            "success": True,
            "data": {
                "credits": user.credits,
                "usage": {
                    "last_30_days": {
                        "input_tokens": usage_stats.total_input_tokens or 0,
                        "output_tokens": usage_stats.total_output_tokens or 0,
                        "total_tokens": (usage_stats.total_input_tokens or 0) + (usage_stats.total_output_tokens or 0),
                        "cost": float(usage_stats.total_cost or 0),
                        "requests": usage_stats.total_requests or 0,
                        "cached_requests": int(usage_stats.cached_requests or 0)
                    }
                },
                "last_payment": {
                    "amount": last_payment.amount if last_payment else None,
                    "credits": last_payment.credits if last_payment else None,
                    "date": last_payment.created_at.isoformat() if last_payment else None
                }
            }
        }), 200
    except Exception as e:
        logger.error("Fehler beim Abrufen der Kreditinformationen: %s", str(e))
        return jsonify({
            "success": True,
            "data": {"credits": user.credits}
        }), 200


def get_payment_history():
    """
    Ruft die Zahlungshistorie des aktuellen Benutzers ab.

    Returns:
        tuple: JSON-Antwort mit Zahlungshistorie und HTTP-Statuscode
    """
    try:
        payments = Payment.query.filter_by(user_id=request.user_id).order_by(Payment.created_at.desc()).all()

        history = []
        for payment in payments:
            history.append({
                'id': payment.id,
                'amount': payment.amount,
                'credits': payment.credits,
                'status': payment.status,
                'created_at': payment.created_at.isoformat(),
                'payment_method': payment.payment_method
            })

        return jsonify({
            "success": True,
            "data": {"history": history}
        }), 200
    except Exception as e:
        logger.error("Fehler beim Abrufen der Zahlungshistorie: %s", str(e))
        return jsonify({
            "success": False,
            "error": {"code": "DATABASE_ERROR", "message": str(e)}
        }), 500


def get_token_usage_stats(time_range='month'):
    """
    Ruft detaillierte Token-Nutzungsstatistiken des aktuellen Benutzers ab.

    Args:
        time_range (str): Der Zeitraum für die Statistiken ('day', 'week', 'month', 'year')

    Returns:
        tuple: JSON-Antwort mit Token-Nutzungsstatistiken und HTTP-Statuscode
    """
    try:
        # Abfrage-Datum basierend auf dem Zeitraum festlegen
        if time_range == 'day':
            start_date = datetime.utcnow() - timedelta(days=1)
        elif time_range == 'week':
            start_date = datetime.utcnow() - timedelta(weeks=1)
        elif time_range == 'month':
            start_date = datetime.utcnow() - timedelta(days=30)
        elif time_range == 'year':
            start_date = datetime.utcnow() - timedelta(days=365)
        else:
            # Default: Monat
            start_date = datetime.utcnow() - timedelta(days=30)

        # Token-Nutzung nach Modell gruppieren
        model_usage = db.session.query(
            TokenUsage.model,
            func.sum(TokenUsage.input_tokens).label('input_tokens'),
            func.sum(TokenUsage.output_tokens).label('output_tokens'),
            func.sum(TokenUsage.cost).label('cost'),
            func.count().label('requests')
        ).filter(
            TokenUsage.user_id == request.user_id,
            TokenUsage.timestamp >= start_date
        ).group_by(TokenUsage.model).all()

        # Token-Nutzung nach Endpunkt gruppieren
        endpoint_usage = db.session.query(
            TokenUsage.endpoint,
            func.sum(TokenUsage.input_tokens).label('input_tokens'),
            func.sum(TokenUsage.output_tokens).label('output_tokens'),
            func.sum(TokenUsage.cost).label('cost'),
            func.count().label('requests')
        ).filter(
            TokenUsage.user_id == request.user_id,
            TokenUsage.timestamp >= start_date,
            TokenUsage.endpoint.isnot(None)
        ).group_by(TokenUsage.endpoint).all()

        # Ergebnisse formatieren
        models = []
        for row in model_usage:
            models.append({
                'model': row.model,
                'input_tokens': row.input_tokens,
                'output_tokens': row.output_tokens,
                'total_tokens': row.input_tokens + row.output_tokens,
                'cost': float(row.cost),
                'requests': row.requests
            })

        endpoints = []
        for row in endpoint_usage:
            endpoints.append({
                'endpoint': row.endpoint,
                'input_tokens': row.input_tokens,
                'output_tokens': row.output_tokens,
                'total_tokens': row.input_tokens + row.output_tokens,
                'cost': float(row.cost),
                'requests': row.requests
            })

        return jsonify({
            "success": True,
            "data": {
                "time_range": time_range,
                "models": models,
                "endpoints": endpoints
            }
        }), 200
    except Exception as e:
        logger.error("Fehler beim Abrufen der Token-Nutzungsstatistiken: %s", str(e))
        return jsonify({
            "success": False,
            "error": {"code": "DATABASE_ERROR", "message": str(e)}
        }), 500
