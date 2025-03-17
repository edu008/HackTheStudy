from flask import Blueprint

# Erstelle den Blueprint
api_bp = Blueprint('api', __name__)

# Importiere die Routen aus den Untermodulen
from .upload import upload_file, get_results
from .flashcards import generate_more_flashcards
from .questions import generate_more_questions
from .topics import generate_related_topics, get_topics
from .user import get_user_uploads
from .auth import auth_bp, setup_oauth

# Registriere den auth Blueprint
api_bp.register_blueprint(auth_bp, url_prefix='/auth')
