import os
from dotenv import load_dotenv
from flask import Flask, redirect
from flask_cors import CORS
from openai import OpenAI
from models import db
from prometheus_flask_exporter import PrometheusMetrics
import logging

load_dotenv()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY')
    app.config['CELERY_BROKER_URL'] = os.getenv('REDIS_URL', 'redis://redis:6379/0')
    app.config['CELERY_RESULT_BACKEND'] = os.getenv('REDIS_URL', 'redis://redis:6379/0')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[logging.FileHandler('app.log'), logging.StreamHandler()]
    )

    CORS(app, supports_credentials=True)
    db.init_app(app)
    
    # Initialize Celery with the app context
    from tasks import init_celery
    init_celery(app)
    
    metrics = PrometheusMetrics(app)

    # Import api_bp after app initialization
    from api import api_bp, setup_oauth
    
    app.register_blueprint(api_bp, url_prefix='/api/v1')
    
    # Setup OAuth
    setup_oauth(app)

    @app.route('/')
    def index():
        return "Welcome to HackTheStudy Backend"

    with app.app_context():
        db.create_all()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)