"""
Controller-Funktionen für die Authentifizierungslogik.
Enthält die Hauptgeschäftslogik für die Benutzerauthentifizierung.
"""

import logging
from datetime import datetime, timedelta
from uuid import uuid4

from core.models import OAuthToken, Payment, User, UserActivity, db
from flask import current_app, jsonify, redirect, request
from flask_jwt_extended import create_access_token

# Logger konfigurieren
logger = logging.getLogger(__name__)


def handle_oauth_callback(provider: str, user_info: dict, token_data: dict = None):
    """Zentrale Funktion zur Verarbeitung von OAuth-Callbacks."""
    try:
        # Initialisiere existing_user mit None
        existing_user = None

        # Suche nach existierendem Benutzer mit OAuth-Provider und ID
        user = User.query.filter_by(oauth_provider=provider, oauth_id=user_info['id']).first()

        # Wenn kein Benutzer gefunden wurde, suche nach E-Mail
        if not user:
            existing_user = User.query.filter_by(email=user_info['email']).first()
            if existing_user:
                # Aktualisiere existierenden Benutzer mit OAuth-Informationen
                existing_user.oauth_provider = provider
                existing_user.oauth_id = user_info['id']
                existing_user.avatar = user_info.get('avatar')
                user = existing_user
            else:
                # Erstelle neuen Benutzer
                user = User(
                    id=str(uuid4()),
                    email=user_info['email'],
                    name=user_info['name'],
                    avatar=user_info.get('avatar'),
                    oauth_provider=provider,
                    oauth_id=user_info['id'],
                    credits=0
                )
                db.session.add(user)

        try:
            # Schneller Commit, um die User-ID zu erhalten
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error("Fehler beim Speichern des Benutzers: %s", str(e))
            raise

        # Speichere OAuth-Token, falls token_data vorhanden ist
        if token_data:
            # Prüfe, ob bereits ein Token für diesen Benutzer und Provider existiert
            existing_token = OAuthToken.query.filter_by(
                user_id=user.id,
                provider=provider
            ).first()

            # Lösche das alte Token, falls vorhanden
            if existing_token:
                db.session.delete(existing_token)

            # Erstelle neues Token
            oauth_token = OAuthToken(
                id=str(uuid4()),
                user_id=user.id,
                provider=provider,
                access_token=token_data.get('access_token'),
                refresh_token=token_data.get('refresh_token'),
                expires_at=datetime.utcnow() + timedelta(seconds=token_data.get('expires_in', 3600))
            )
            db.session.add(oauth_token)

        # Speichere alle Änderungen
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error("Fehler beim Speichern der OAuth-Daten: %s", str(e))
            raise

        # Erstelle JWT-Token mit flask_jwt_extended
        token = create_access_token(identity=user.id)

        # Prüfe ob es ein API-Request ist (Accept: application/json)
        if request.headers.get('Accept') == 'application/json':
            # Bei API-Anfragen JSON zurückgeben
            return jsonify({
                'access_token': token,
                'user': user.to_dict()
            }), 200
            
        # Bei normalen Anfragen zum Frontend weiterleiten
        # Bestimme die richtige Frontend-URL
        referer = request.headers.get('Referer', '')
        if 'localhost' in referer or '127.0.0.1' in referer:
            # Wenn die Anfrage von localhost kommt, verwende die lokale URL
            frontend_url = 'http://localhost:3000'
            logger.info("Lokale Entwicklungsumgebung erkannt, verwende: %s", frontend_url)
        else:
            # Ansonsten verwende die konfigurierte Frontend-URL
            frontend_url = current_app.config.get('FRONTEND_URL', 'https://www.hackthestudy.ch')
            
        redirect_url = f"{frontend_url}/auth-callback?token={token}"
        logger.info("Weiterleitung nach erfolgreicher Authentifizierung zu: %s", redirect_url)
        return redirect(redirect_url)

    except Exception as e:
        logger.error("Fehler bei OAuth Callback Verarbeitung: %s", str(e))
        return jsonify({
            'error': 'Authentication failed',
            'message': str(e)
        }), 500


def create_user_activity(user_id, activity_type, title, **kwargs):
    """Erstellt eine neue Benutzeraktivität."""
    try:
        # Begrenze auf 5 Einträge
        existing_activities = UserActivity.query.filter_by(user_id=user_id).order_by(UserActivity.timestamp.asc()).all()
        if len(existing_activities) >= 5:
            oldest_activity = existing_activities[0]
            db.session.delete(oldest_activity)
            logger.info("Alte Aktivität gelöscht: %s", oldest_activity.id)

        activity = UserActivity(
            id=str(uuid4()),
            user_id=user_id,
            activity_type=activity_type,
            title=title,
            main_topic=kwargs.get('main_topic'),
            subtopics=kwargs.get('subtopics'),
            session_id=kwargs.get('session_id'),
            details=kwargs.get('details'),
            timestamp=datetime.utcnow()
        )
        db.session.add(activity)
        db.session.commit()
        return activity
    except Exception as e:
        db.session.rollback()
        logger.error("Fehler beim Erstellen der Benutzeraktivität: %s", str(e))
        raise


def process_payment(user_id, amount, credit_amount, payment_method):
    """Verarbeitet eine Zahlung und aktualisiert das Benutzerkonto."""
    try:
        # Erstelle Zahlungsdatensatz
        payment = Payment(
            id=str(uuid4()),
            user_id=user_id,
            amount=amount,
            credits=credit_amount,
            payment_method=payment_method,
            transaction_id=str(uuid4()),
            status='completed'
        )
        db.session.add(payment)

        # Aktualisiere Benutzerguthaben
        user = User.query.get(user_id)
        user.credits += credit_amount

        # Erstelle Aktivitätseintrag
        create_user_activity(
            user_id=user_id,
            activity_type='payment',
            title=f"Purchased {credit_amount} credits",
            details={'amount': amount, 'payment_method': payment_method}
        )

        db.session.commit()
        return payment, user
    except Exception as e:
        db.session.rollback()
        logger.error("Fehler bei der Zahlungsverarbeitung: %s", str(e))
        raise
