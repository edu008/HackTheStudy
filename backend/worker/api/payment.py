import os
import stripe
from flask import Blueprint, request, jsonify, current_app, redirect, url_for
from . import api_bp
from core.models import db, User, Payment
from api.auth import token_required
import json
import logging

# Blueprint erstellen und zentrale CORS-Konfiguration verwenden
payment_bp = Blueprint('payment', __name__)

# Initialisierung von Stripe mit dem API-Key
stripe_key = os.getenv('STRIPE_API_KEY')
if stripe_key:
    stripe.api_key = stripe_key.strip()
    logging.info("Stripe wurde mit API-Schlüssel initialisiert")
    stripe.api_version = '2023-10-16'  # Neueste API-Version verwenden
else:
    # Zeige nur eine Warnung, ohne einen Dummy-Key zu setzen
    logging.warning("STRIPE_API_KEY ist nicht gesetzt. Stripe-Zahlungen werden nicht funktionieren.")

# Definiere Preise und Credits
PRICES = {
    'standard': 1990,  # 19,90 CHF in Rappen
    'premium': 2990,   # 29,90 CHF in Rappen
    'ultimate': 4990   # 49,90 CHF in Rappen
}

# Definiere Credits pro Paket
CREDITS = {
    'standard': 300,
    'premium': 500,
    'ultimate': 1000
}

# Hilfsfunktion zum Berechnen der Credits
def calculate_credits(amount_in_cents):
    """Berechnet die Credits basierend auf dem Betrag in Rappen"""
    if amount_in_cents == PRICES['standard']:
        return CREDITS['standard']
    elif amount_in_cents == PRICES['premium']:
        return CREDITS['premium']
    elif amount_in_cents == PRICES['ultimate']:
        return CREDITS['ultimate']
    else:
        # Fallback für unbekannte Beträge: 10 Credits pro Franken
        return amount_in_cents // 100 * 10

@payment_bp.route('/create-checkout-session', methods=['POST', 'OPTIONS'])
@token_required
def create_checkout_session():
    # Bei OPTIONS-Anfragen gib sofort eine Antwort zurück
    if request.method == 'OPTIONS':
        response = current_app.make_response("")
        return response
        
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
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/webhook', methods=['POST', 'OPTIONS'])
def stripe_webhook():
    # Bei OPTIONS-Anfragen gib sofort eine Antwort zurück
    if request.method == 'OPTIONS':
        response = current_app.make_response("")
        return response
        
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    
    # Webhook-Secret abrufen - unterstützt mehrere Variablennamen
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    if not webhook_secret:
        logging.warning("STRIPE_WEBHOOK_SECRET ist nicht gesetzt. Webhook-Validierung wird übersprungen.")
        try:
            # Payload ohne Signaturprüfung verwenden
            event = json.loads(payload)
        except ValueError as e:
            return jsonify({'error': 'Ungültige Payload'}), 400
    else:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret.strip()
            )
        except ValueError as e:
            # Ungültige Payload
            logging.error(f"Webhook-Fehler: Ungültige Payload - {str(e)}")
            return jsonify({'error': str(e)}), 400
        except stripe.error.SignatureVerificationError as e:
            # Ungültige Signatur
            logging.error(f"Webhook-Fehler: Ungültige Signatur - {str(e)}")
            return jsonify({'error': str(e)}), 400
    
    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # Metadata aus der Session abrufen
        user_id = session.get('metadata', {}).get('user_id')
        credits = int(session.get('metadata', {}).get('credits', 0))
        
        if user_id and credits:
            # Zahlungsdatensatz erstellen
            payment = Payment(
                user_id=user_id,
                amount=session.get('amount_total', 0) / 100.0,  # Von Rappen zu CHF umwandeln
                credits=credits,
                payment_method='stripe',
                transaction_id=session.get('id'),
                status='completed'
            )
            
            # Credits dem Benutzer gutschreiben
            user = User.query.get(user_id)
            if user:
                user.credits += credits
                logging.info(f"Zahlung erfolgreich: {credits} Credits für Benutzer {user_id} gutgeschrieben")
            
            # Speichern
            db.session.add(payment)
            db.session.commit()
    
    return jsonify({'status': 'success'})

@payment_bp.route('/payment-success', methods=['GET', 'OPTIONS'])
@token_required
def payment_success():
    # Bei OPTIONS-Anfragen gib sofort eine Antwort zurück
    if request.method == 'OPTIONS':
        response = current_app.make_response("")
        return response
        
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
                credits = int(session.metadata.get('credits', 0))
                
                # Zahlungsdatensatz erstellen
                payment = Payment(
                    user_id=request.user_id,
                    amount=session.amount_total / 100.0,  # Von Rappen zu CHF umwandeln
                    credits=credits,
                    payment_method='stripe',
                    transaction_id=session_id,
                    status='completed'
                )
                
                # Credits dem Benutzer gutschreiben
                user = User.query.get(request.user_id)
                if user:
                    user.credits += credits
                
                # Speichern
                db.session.add(payment)
                db.session.commit()
                
            return jsonify({
                'status': 'success',
                'credits': session.metadata.get('credits')
            })
        else:
            return jsonify({'status': 'pending'})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/get-credits', methods=['GET', 'OPTIONS'])
@token_required
def get_user_credits():
    # Bei OPTIONS-Anfragen gib sofort eine Antwort zurück
    if request.method == 'OPTIONS':
        response = current_app.make_response("")
        return response
    
    user = User.query.get(request.user_id)
    if not user:
        return jsonify({
            "success": False, 
            "error": {"code": "USER_NOT_FOUND", "message": "User not found"}
        }), 404
    else:
        return jsonify({
            "success": True, 
            "data": {"credits": user.credits}
        }), 200

@payment_bp.route('/payment-history', methods=['GET', 'OPTIONS'])
@token_required
def payment_history():
    # Bei OPTIONS-Anfragen gib sofort eine Antwort zurück
    if request.method == 'OPTIONS':
        response = current_app.make_response("")
        return response
        
    payments = Payment.query.filter_by(user_id=request.user_id).order_by(Payment.created_at.desc()).all()
    
    history = []
    for payment in payments:
        history.append({
            'id': payment.id,
            'amount': payment.amount,
            'credits': payment.credits,
            'status': payment.status,
            'created_at': payment.created_at.isoformat()
        })
    
    return jsonify({'history': history}) 