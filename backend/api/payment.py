import os
import stripe
from flask import Blueprint, request, jsonify, current_app
from models import db, User, Payment
from flask_cors import cross_origin
from api.auth import token_required
import json

payment_bp = Blueprint('payment', __name__)

# Initialisierung von Stripe mit dem API-Key
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
stripe.api_version = '2023-10-16'  # Neueste API-Version verwenden

# CORS-Konfiguration für alle Endpoints
CORS_CONFIG = {
    "supports_credentials": True,
    "origins": "*",
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"]
}

# Die Preisstufen festlegen (in Rappen, da CHF)
PRICE_TIERS = {
    'tier1': {'amount': 500, 'credits': 250},  # 5 CHF für 250 Credits
    'tier2': {'amount': 1000, 'credits': 500},  # 10 CHF für 500 Credits
    'tier3': {'amount': 2500, 'credits': 1250},  # 25 CHF für 1250 Credits
    'tier4': {'amount': 5000, 'credits': 2500}   # 50 CHF für 2500 Credits
}

# Funktion zur Berechnung der Credits basierend auf dem Zahlungsbetrag
def calculate_credits(amount_in_cents):
    """Berechnet die Credits basierend auf dem Zahlungsbetrag
    Die Credits sind das Doppelte der API-Kosten (hier als Beispiel)
    """
    # In diesem Beispiel: 100 Rappen = 50 Credits
    return amount_in_cents // 2

@payment_bp.route('/create-checkout-session', methods=['POST'])
@cross_origin(**CORS_CONFIG)
@token_required
def create_checkout_session():
    data = request.get_json()
    tier = data.get('tier')
    
    if tier not in PRICE_TIERS:
        return jsonify({'error': 'Ungültige Preisstufe'}), 400
    
    price_data = PRICE_TIERS[tier]
    user_id = request.user_id
    
    try:
        # Stripe Checkout Session erstellen
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'chf',
                    'product_data': {
                        'name': f'{price_data["credits"]} Credits',
                        'description': 'Credits für API-Abfragen'
                    },
                    'unit_amount': price_data['amount'],
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=os.getenv('FRONTEND_URL') + '/payment/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=os.getenv('FRONTEND_URL') + '/payment/cancel',
            metadata={
                'user_id': user_id,
                'credits': price_data['credits']
            }
        )
        
        return jsonify({'sessionId': checkout_session.id, 'url': checkout_session.url})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.getenv('STRIPE_WEBHOOK_SECRET')
        )
    except ValueError as e:
        # Ungültige Payload
        return jsonify({'error': str(e)}), 400
    except stripe.error.SignatureVerificationError as e:
        # Ungültige Signatur
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
            
            # Speichern
            db.session.add(payment)
            db.session.commit()
    
    return jsonify({'status': 'success'})

@payment_bp.route('/payment-success', methods=['GET'])
@cross_origin(**CORS_CONFIG)
@token_required
def payment_success():
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

@payment_bp.route('/get-credits', methods=['GET'])
@cross_origin(**CORS_CONFIG)
@token_required
def get_credits():
    user = User.query.get(request.user_id)
    return jsonify({'credits': user.credits})

@payment_bp.route('/payment-history', methods=['GET'])
@cross_origin(**CORS_CONFIG)
@token_required
def payment_history():
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