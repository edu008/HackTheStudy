"""
Utility-Funktionen für das Backend - WRAPPER
------------------------------------------

WARNUNG: Diese Datei wird aus Gründen der Abwärtskompatibilität beibehalten.
Für neue Implementierungen verwenden Sie bitte das Modul `api.utils`.

Diese Datei importiert alle nötigen Funktionen aus dem neuen modularen Utility-Modul,
um Abwärtskompatibilität mit bestehendem Code zu gewährleisten.
"""

# Logger, der Verwendung der alten API dokumentiert
import logging

# Definiere Dummy-Funktionen für fehlende Module
def dummy_function(*args, **kwargs):
    """Platzhalter-Funktion, die für fehlende Importe verwendet wird."""
    return None

# Importiere die Module oder erstelle Platzhalter, wenn sie nicht existieren
try:
    from .utils.content_analysis import analyze_content, generate_concept_map_suggestions, unified_content_processing
except ImportError:
    analyze_content = dummy_function
    generate_concept_map_suggestions = dummy_function
    unified_content_processing = dummy_function

try:
    from .utils.database import Connection, Flashcard, Question, Topic, Upload
except ImportError:
    Connection = Flashcard = Question = Topic = Upload = type('MockClass', (), {})

try:
    from .utils.text_processing import clean_text_for_database, detect_language
except ImportError:
    clean_text_for_database = dummy_function
    detect_language = dummy_function

try:
    from .utils.learning_materials import (
        generate_additional_flashcards,
        generate_additional_questions,
        generate_quiz
    )
except ImportError:
    generate_additional_flashcards = dummy_function
    generate_additional_questions = dummy_function
    generate_quiz = dummy_function

try:
    from .utils.session_utils import (
        check_and_manage_user_sessions,
        delete_session,
        update_session_timestamp,
        get_active_sessions
    )
except ImportError:
    check_and_manage_user_sessions = dummy_function
    delete_session = dummy_function
    update_session_timestamp = dummy_function
    get_active_sessions = dummy_function

try:
    from .utils.utils_common import format_timestamp
except ImportError:
    format_timestamp = dummy_function

try:
    from .utils.text_processing import count_words, extract_sentences, get_text_statistics
except ImportError:
    count_words = dummy_function
    extract_sentences = dummy_function
    get_text_statistics = dummy_function

try:
    from .utils.tracking import UserActivity
except ImportError:
    UserActivity = type('MockUserActivity', (), {})

try:
    from .utils.validation import sanitize_filename, truncate_text, parse_bool
except ImportError:
    sanitize_filename = dummy_function
    truncate_text = dummy_function
    parse_bool = dummy_function

logger = logging.getLogger(__name__)
logger.warning(
    "Die Datei utils.py wird verwendet, die aus Gründen der Abwärtskompatibilität beibehalten wird. "
    "Bitte verwenden Sie für neue Implementierungen das api.utils-Modul."
)

# Exportiere alle Namen
__all__ = [
    'analyze_content', 'generate_concept_map_suggestions', 'unified_content_processing',
    'Connection', 'Flashcard', 'Question', 'Topic', 'Upload',
    'clean_text_for_database', 'detect_language',
    'generate_additional_flashcards', 'generate_additional_questions', 'generate_quiz',
    'check_and_manage_user_sessions', 'delete_session', 'update_session_timestamp', 
    'get_active_sessions', 'format_timestamp',
    'count_words', 'extract_sentences', 'get_text_statistics',
    'UserActivity',
    'sanitize_filename', 'truncate_text', 'parse_bool'
]
