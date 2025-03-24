#!/usr/bin/env python
"""
Zahlungs-Service für HackTheStudy

Dieser Service verarbeitet alle Zahlungs-bezogenen API-Anfragen.
"""

import os
import sys
import json
import logging
import datetime
from flask import Flask, request, jsonify, Blueprint

# Stellen sicher, dass das App-Verzeichnis im Python-Pfad ist
sys.path.insert(0, '/app')

# Konfiguriere Logging
logging.basicConfig(
    level=logging.INFO, 
    # Optimiertes Format für DigitalOcean App Platform Logs
    format='[%(asctime)s] [PID:%(process)d] [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('payment_service')

# Deaktiviere Pufferung für DigitalOcean App Platform
sys.stdout.reconfigure(line_buffering=True)

# Initialisiere Flask-App
app = Flask(__name__)

# Wichtige Startup-Logs für DigitalOcean
logger.info("================== PAYMENT SERVICE STARTET ==================")
logger.info("DIGITAL_OCEAN_APP_PLATFORM: TRUE")
logger.info("DO_SERVICE_TYPE: payment")
logger.info(f"PID: {os.getpid()}")
logger.info(f"Python-Version: {sys.version}")
logger.info(f"Hostname: {os.environ.get('HOSTNAME', 'unbekannt')}")
logger.info(f"DigitalOcean App Name: {os.environ.get('DIGITAL_OCEAN_APP_NAME', 'nicht gesetzt')}")
logger.info(f"Port: {os.environ.get('PAYMENT_PORT', '5001')}")
logger.info("===========================================================")

# Importiere Umgebungsvariablen-Handler
try:
    from config.env_handler import load_env
    load_env()
except ImportError:
    logger.warning("Umgebungsvariablen-Handler konnte nicht importiert werden")

# Stripe-API importieren (falls verfügbar)
try:
    import stripe
    stripe.api_key = os.environ.get('STRIPE_API_KEY')
    has_stripe = True
except ImportError:
    logger.warning("Stripe konnte nicht importiert werden. Zahlungsfunktionen deaktiviert.")
    has_stripe = False

# Payment-Blueprint
payment_bp = Blueprint('payment', __name__)

@payment_bp.route('/health', methods=['GET'])
def health():
    """Endpoint für Health-Checks"""
    status = {
        "status": "healthy",
        "services": {
            "payment": {"status": "healthy"},
            "stripe": {"status": "disabled" if not has_stripe else "healthy"}
        }
    }
    return jsonify(status)

@payment_bp.route('/create-checkout', methods=['POST'])
def create_checkout():
    """Erstellt eine Checkout-Session für Stripe"""
    if not has_stripe:
        return jsonify({"error": "Stripe ist nicht konfiguriert"}), 503
    
    data = request.json
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': data.get('currency', 'eur'),
                    'product_data': {
                        'name': data.get('product_name', 'Credits'),
                    },
                    'unit_amount': data.get('amount', 1000),
                },
                'quantity': data.get('quantity', 1),
            }],
            mode='payment',
            success_url=data.get('success_url', 'https://example.com/success'),
            cancel_url=data.get('cancel_url', 'https://example.com/cancel'),
            customer_email=data.get('email')
        )
        return jsonify({'id': checkout_session.id})
    except Exception as e:
        logger.error(f"Fehler bei Stripe-Checkout: {e}")
        return jsonify({"error": str(e)}), 500

# Registriere Blueprints
app.register_blueprint(payment_bp, url_prefix='/api/v1/payment')

# Root-Route für Health-Checks hinzufügen für DigitalOcean
@app.route('/')
def root_health():
    """Root-Route für DigitalOcean Health Checks - einfach, minimal, zuverlässig"""
    return jsonify({
        "status": "healthy",
        "service": os.environ.get('DIGITAL_OCEAN_APP_NAME', 'hackthestudy-payment'),
        "timestamp": __import__('datetime').datetime.now().isoformat()
    }), 200

# Standard-Health-Check-Route für DigitalOcean
@app.route('/.well-known/healthcheck')
def do_health_check():
    """DigitalOcean spezifischer Health-Check-Pfad"""
    return jsonify({
        "status": "healthy",
        "service": os.environ.get('DIGITAL_OCEAN_APP_NAME', 'hackthestudy-payment'),
        "timestamp": __import__('datetime').datetime.now().isoformat()
    }), 200

if __name__ == '__main__':
    # Starte den Server
    # Verwende PAYMENT_PORT (5001) als Standard, aber ermögliche Überschreibung durch PORT-Umgebungsvariable
    # Im Container-Umfeld ist es wichtig, dass dieser Service nicht den gleichen Port wie der Hauptservice verwendet
    default_port = 5001
    port = int(os.environ.get('PAYMENT_PORT', default_port))
    # Wenn PORT gesetzt ist (DigitalOcean), prüfe, ob dieser Port bereits verwendet wird
    if 'PORT' in os.environ and int(os.environ.get('PORT')) != port:
        logger.info(f"PORT-Umgebungsvariable ({os.environ.get('PORT')}) unterscheidet sich vom Standard-Port ({port})")
        logger.info(f"Verwende Port {port} für den Payment-Server, um Portkonflikte zu vermeiden")
    
    logger.info(f"Starte Payment-Server auf Port {port}")
    app.run(host='0.0.0.0', port=port) 