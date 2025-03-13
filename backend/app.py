import os
import uuid
from flask import Flask, session
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
from api.routes import api_bp
import time
import shutil

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "your-secret-key")
    CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": "*"}})
    
    # Verzeichnis für temporäre Dateien
    app.config['TEMP_FOLDER'] = os.path.join(os.path.dirname(__file__), 'temp')
    os.makedirs(app.config['TEMP_FOLDER'], exist_ok=True)
    
    app.config['OPENAI_CLIENT'] = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    app.config['MAX_AGE'] = 3600  # 1 Stunde Lebensdauer für temporäre Dateien
    
    # Cleanup-Funktion für alte Dateien
    @app.before_request
    def cleanup_temp_files():
        now = time.time()
        temp_folder = app.config['TEMP_FOLDER']
        for session_id in os.listdir(temp_folder):
            session_path = os.path.join(temp_folder, session_id)
            if os.path.isdir(session_path):
                mod_time = os.path.getmtime(session_path)
                if now - mod_time > app.config['MAX_AGE']:
                    shutil.rmtree(session_path)
                    print(f"Deleted old session: {session_id}")
    
    app.register_blueprint(api_bp, url_prefix='/api')
    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)