"""
Wrapper-Modul für das Flashcards-Paket
-------------------------------------

HINWEIS: Diese Datei dient nur der Abwärtskompatibilität.
Neue Entwicklungen sollten direkt das Paket api.flashcards.*
verwenden.

Dieses Modul importiert und re-exportiert alle öffentlichen
Komponenten des flashcards-Pakets, um bestehenden Code, der diese Datei
importiert, weiterhin funktionsfähig zu halten.
"""

# Importiere die Blueprint-Definition
from .flashcards import flashcards_bp

# Importiere API-Endpunkte
from .flashcards.routes import (
    generate_flashcards_route,
    generate_more_flashcards_route,
    get_flashcards_route,
    update_flashcard_route,
    delete_flashcard_route,
    get_study_session_route,
    save_flashcard_feedback_route
)

# Importiere Geschäftslogik
from .flashcards.controllers import (
    process_generate_flashcards,
    process_generate_more_flashcards,
    process_get_flashcards,
    process_update_flashcard,
    process_delete_flashcard,
    process_get_study_session,
    process_save_flashcard_feedback
)

# Importiere Generatorfunktionen
from .flashcards.generation import (
    generate_flashcards,
    generate_additional_flashcards,
    generate_fallback_flashcards
)

# Importiere Datenbankfunktionen
from .flashcards.models import (
    get_flashcards,
    save_flashcard,
    update_flashcard_statistics,
    get_flashcards_by_category,
    delete_flashcard,
    get_flashcard_categories
)

# Importiere Schemas
from .flashcards.schemas import (
    FlashcardRequestSchema,
    FlashcardDataSchema,
    FlashcardResponseSchema,
    FlashcardStudySessionSchema,
    FlashcardFeedbackSchema
)

# Importiere Validierungslogik
from .flashcards.validation import (
    validate_flashcard_data,
    validate_generated_flashcards,
    sanitize_flashcard,
    sanitize_flashcard_front,
    sanitize_flashcard_back,
    validate_flashcard_category,
    validate_flashcard_difficulty
)

# Importiere Hilfsfunktionen
from .flashcards.utils import (
    format_flashcards,
    detect_language_wrapper,
    categorize_content,
    extract_terms_from_content,
    create_study_plan,
    parse_study_settings
)

# Importiere Lernfunktionen
from .flashcards.study import (
    create_study_session,
    update_card_scheduling,
    get_study_statistics,
    record_study_result
)

# Stelle sicher, dass alles exportiert wird, was vorher verfügbar war
__all__ = [
    'flashcards_bp',
    'generate_flashcards_route',
    'generate_more_flashcards_route',
    'get_flashcards_route',
    'update_flashcard_route',
    'delete_flashcard_route',
    'get_study_session_route',
    'save_flashcard_feedback_route',
    'process_generate_flashcards',
    'process_generate_more_flashcards',
    'process_get_flashcards',
    'process_update_flashcard',
    'process_delete_flashcard',
    'process_get_study_session',
    'process_save_flashcard_feedback',
    'generate_flashcards',
    'generate_additional_flashcards',
    'generate_fallback_flashcards',
    'get_flashcards',
    'save_flashcard',
    'update_flashcard_statistics',
    'get_flashcards_by_category',
    'delete_flashcard',
    'get_flashcard_categories',
    'FlashcardRequestSchema',
    'FlashcardDataSchema',
    'FlashcardResponseSchema',
    'FlashcardStudySessionSchema',
    'FlashcardFeedbackSchema',
    'validate_flashcard_data',
    'validate_generated_flashcards',
    'sanitize_flashcard',
    'sanitize_flashcard_front',
    'sanitize_flashcard_back',
    'validate_flashcard_category',
    'validate_flashcard_difficulty',
    'format_flashcards',
    'detect_language_wrapper',
    'categorize_content',
    'extract_terms_from_content',
    'create_study_plan',
    'parse_study_settings',
    'create_study_session',
    'update_card_scheduling',
    'get_study_statistics',
    'record_study_result'
] 