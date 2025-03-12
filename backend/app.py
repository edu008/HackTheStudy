from flask import Flask, session
from flask_cors import CORS
import os
from dotenv import load_dotenv
from openai import OpenAI
from api.routes import api_bp

# Lade die .env-Datei aus dem Hauptverzeichnis
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "your-secret-key")  # Erforderlich für flask.session
    
    # Konfiguriere CORS, um Cookies und Credentials zu unterstützen
    CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": "*"}})
    
    # OpenAI configuration
    openai_api_key = os.getenv("OPENAI_API_KEY", "")  # Lade API-Schlüssel aus .env
    app.config['OPENAI_CLIENT'] = OpenAI(api_key=openai_api_key)
    
    # Speichere den letzten hochgeladenen Text in der App-Konfiguration
    # als Fallback, falls die Session nicht funktioniert
    app.config['LAST_UPLOADED_TEXT'] = ""
    
    # Register blueprints
    app.register_blueprint(api_bp, url_prefix='/api')
    
    return app

# Create the Flask application
app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
