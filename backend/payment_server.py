#!/usr/bin/env python
from flask import Flask
from api.payment import payment_bp
from models import db
import os
from flask_cors import CORS

app = Flask(__name__)

# Konfiguration
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# CORS konfigurieren
CORS(app, supports_credentials=True, origins="*", 
     allow_headers=["Content-Type", "Authorization"])

# Datenbank initialisieren
db.init_app(app)

# Payment-Blueprint registrieren
app.register_blueprint(payment_bp, url_prefix='/api/payment')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True) 