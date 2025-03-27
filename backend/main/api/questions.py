"""
Wrapper-Modul für das Questions-Paket
-------------------------------------

HINWEIS: Diese Datei dient nur der Abwärtskompatibilität.
Neue Entwicklungen sollten direkt das Paket api.questions.*
verwenden.

Dieses Modul importiert und re-exportiert alle öffentlichen
Komponenten des questions-Pakets, um bestehenden Code, der diese Datei
importiert, weiterhin funktionsfähig zu halten.
"""

# Importiere die Blueprint-Definition
from .questions import questions_bp

# Importiere API-Endpunkte
from .questions.routes import (
    generate_questions_route,
    generate_more_questions_route
)

# Importiere Geschäftslogik
from .questions.controllers import (
    process_generate_questions,
    process_generate_more_questions
)

# Importiere Generatorfunktionen
from .questions.generation import (
    generate_questions,
    generate_additional_questions,
    generate_fallback_questions
)

# Importiere Datenbankfunktionen
from .questions.models import (
    get_questions,
    save_question
)

# Importiere Schemas
from .questions.schemas import QuestionRequestSchema

# Importiere Validierungslogik
from .questions.validation import (
    validate_question_data,
    validate_generated_questions,
    sanitize_question,
    sanitize_question_text,
    sanitize_question_options,
    QuestionDataSchema
)

# Importiere Hilfsfunktionen
from .questions.utils import (
    format_questions,
    detect_language_wrapper
)

# Stelle sicher, dass alles exportiert wird, was vorher verfügbar war
__all__ = [
    'questions_bp',
    'generate_questions_route',
    'generate_more_questions_route',
    'process_generate_questions',
    'process_generate_more_questions',
    'generate_questions',
    'generate_additional_questions',
    'generate_fallback_questions',
    'get_questions',
    'save_question',
    'QuestionRequestSchema',
    'QuestionDataSchema',
    'validate_question_data',
    'validate_generated_questions',
    'sanitize_question',
    'sanitize_question_text',
    'sanitize_question_options',
    'format_questions',
    'detect_language_wrapper'
]