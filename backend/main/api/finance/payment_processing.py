"""
Zahlungsverarbeitungsfunktionen für das Finanzmodul.
Enthält Funktionen zur Verarbeitung von Zahlungen über verschiedene Zahlungsanbieter.
"""

import json
import logging
import os

import stripe
from core.models import Payment, User, db
from flask import current_app, jsonify, redirect, request, url_for

from .constants import PRICES, calculate_credits

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Stripe initialisieren


def init_stripe():
    """
    Initialisiert Stripe mit dem API-Key aus den Umgebungsvariablen.
    """
    stripe_key = os.getenv('STRIPE_API_KEY')
    if stripe_key:
        stripe.api_key = stripe_key.strip()
        logger.info("Stripe wurde mit API-Schlüssel initialisiert")
        stripe.api_version = '2023-10-16'  # Neueste API-Version verwenden
        return True
    
    # Zeige nur eine Warnung, ohne einen Dummy-Key zu setzen
    logger.warning("STRIPE_API_KEY ist nicht gesetzt. Stripe-Zahlungen werden nicht funktionieren.")
    return False


# Stripe initialisieren beim Laden des Moduls
init_stripe()


def create_checkout_session():
    """
    Erstellt eine Stripe-Checkout-Session für ein Kreditpaket.

    Returns:
        tuple: JSON-Antwort mit der Session-ID und URL, sowie HTTP-Statuscode
    """
    data = request.get_json()
    tier = data.get('tier')

    if tier not in PRICES:
        return jsonify({'error': 'Ungültige Preisstufe'}), 400

    price_data = PRICES[tier]
    user_id = request.user_id

    try:
        # Stripe Checkout Session erstellen
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'chf',
                    'product_data': {
                        'name': f'{calculate_credits(price_data)} Credits',
                        'description': 'Credits für API-Abfragen'
                    },
                    'unit_amount': price_data,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=os.getenv('FRONTEND_URL').strip() + '/payment/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=os.getenv('FRONTEND_URL').strip() + '/payment/cancel',
            metadata={
                'user_id': user_id,
                'credits': calculate_credits(price_data)
            }
        )

        return jsonify({'sessionId': checkout_session.id, 'url': checkout_session.url})

    except Exception as e:
        logger.error("Fehler beim Erstellen der Checkout-Session: %s", str(e))
        return jsonify({'error': str(e)}), 500


def stripe_webhook():
    """
    Webhook für Stripe-Zahlungsbenachrichtigungen.

    Returns:
        tuple: JSON-Antwort und HTTP-Statuscode
    """
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    # Webhook-Secret abrufen
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')

    if not webhook_secret:
        logger.warning("STRIPE_WEBHOOK_SECRET ist nicht gesetzt. Webhook-Validierung wird übersprungen.")
        try:
            # Payload ohne Signaturprüfung verwenden
            event = json.loads(payload)
        except ValueError as e:
            logger.error("Webhook-Fehler: Ungültige JSON-Payload - %s", str(e))
            return jsonify({'error': 'Ungültige Payload'}), 400
    else:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret.strip()
            )
        except ValueError as e:
            # Ungültige Payload
            logger.error("Webhook-Fehler: Ungültige Payload - %s", str(e))
            return jsonify({'error': str(e)}), 400
        except stripe.error.SignatureVerificationError as e:
            # Ungültige Signatur
            logger.error("Webhook-Fehler: Ungültige Signatur - %s", str(e))
            return jsonify({'error': str(e)}), 400

    # Verarbeite das checkout.session.completed Event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']

        # Metadata aus der Session abrufen
        user_id = session.get('metadata', {}).get('user_id')
        credit_amount = int(session.get('metadata', {}).get('credits', 0))

        if user_id and credit_amount:
            process_successful_payment(
                user_id=user_id,
                amount=session.get('amount_total', 0) / 100.0,  # Von Rappen zu CHF umwandeln
                credit_amount=credit_amount,
                transaction_id=session.get('id'),
                payment_method='stripe'
            )

    return jsonify({'status': 'success'})


def payment_success():
    """
    Endpunkt für die erfolgreiche Zahlungsbestätigung.

    Returns:
        tuple: JSON-Antwort und HTTP-Statuscode
    """
    session_id = request.args.get('session_id')

    if not session_id:
        return jsonify({'error': 'Keine Session-ID angegeben'}), 400

    try:
        # Session abrufen
        session = stripe.checkout.Session.retrieve(session_id)

        # Prüfen, ob die Zahlung für den aktuellen Benutzer ist
        if session.metadata.get('user_id') != request.user_id:
            return jsonify({'error': 'Ungültige Session'}), 403

        # Zahlungsstatus prüfen
        if session.payment_status == 'paid':
            # Prüfen, ob diese Zahlung bereits in der Datenbank existiert
            existing_payment = Payment.query.filter_by(transaction_id=session_id).first()

            # Wenn die Zahlung noch nicht existiert, füge sie hinzu (Fallback für Webhook)
            if not existing_payment:
                # Credits aus den Metadaten abrufen
                credit_amount = int(session.metadata.get('credits', 0))

                process_successful_payment(
                    user_id=request.user_id,
                    amount=session.amount_total / 100.0,  # Von Rappen zu CHF umwandeln
                    credit_amount=credit_amount,
                    transaction_id=session_id,
                    payment_method='stripe'
                )

            return jsonify({
                'status': 'success',
                'credits': session.metadata.get('credits')
            })
        
        return jsonify({'status': 'pending'})

    except Exception as e:
        logger.error("Fehler bei der Zahlungsbestätigung: %s", str(e))
        return jsonify({'error': str(e)}), 500


def process_successful_payment(user_id, amount, credit_amount, transaction_id, payment_method):
    """
    Verarbeitet eine erfolgreiche Zahlung und fügt dem Benutzer Credits hinzu.

    Args:
        user_id (str): Die ID des Benutzers
        amount (float): Der bezahlte Betrag in CHF
        credit_amount (int): Die Anzahl der Credits
        transaction_id (str): Die Transaktions-ID
        payment_method (str): Die Zahlungsmethode (z.B. 'stripe')

    Returns:
        bool: True, wenn erfolgreich, False sonst
    """
    try:
        # Zahlungsdatensatz erstellen
        payment = Payment(
            user_id=user_id,
            amount=amount,
            credits=credit_amount,
            payment_method=payment_method,
            transaction_id=transaction_id,
            status='completed'
        )

        # Credits dem Benutzer gutschreiben
        user = User.query.get(user_id)
        if user:
            user.credits += credit_amount
            logger.info("Zahlung erfolgreich: %s Credits für Benutzer %s gutgeschrieben", credit_amount, user_id)
        else:
            logger.error("Benutzer %s nicht gefunden für Gutschrift", user_id)
            return False

        # Speichern
        db.session.add(payment)
        db.session.commit()

        return True
    except Exception as e:
        db.session.rollback()
        logger.error("Fehler bei der Zahlungsverarbeitung: %s", str(e))
        return False
