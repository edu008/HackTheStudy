from flask import Blueprint, redirect

# In app.py oder api/__init__.py
api_bp = Blueprint('api', __name__)

# Vorhandene Routen-Imports bleiben gleich
from .upload import upload_file, get_results
from .flashcards import generate_more_flashcards
from .questions import generate_more_questions
from .topics import generate_related_topics, get_topics
from .user import get_user_uploads, get_user_history, update_activity_timestamp
from .auth import auth_bp, setup_oauth

# Registriere den auth Blueprint
api_bp.register_blueprint(auth_bp, url_prefix='/auth')

# Füge eine Umleitung für /api/v1/ hinzu
@api_bp.route('/v1/<path:path>')
def redirect_v1(path):
    return redirect(f'/api/{path}', code=301)

# Beispielanwendung in app.py
from flask import Flask
app = Flask(__name__)
app.register_blueprint(api_bp, url_prefix='/api')

if __name__ == '__main__':
    app.run(debug=True)