"""
Utility-Modul für allgemeine Hilfsfunktionen
-------------------------------------------

Dieses Modul bietet eine modulare Struktur für verschiedene Hilfsfunktionen,
aufgeteilt in thematisch organisierte Komponenten:

- file_utils: Funktionen zur Dateiverarbeitung
- text_processing: Funktionen zur Textverarbeitung und -analyse
- ai_utils: Funktionen für die OpenAI-Integration
- content_analysis: Funktionen zur Inhaltsanalyse
- learning_materials: Funktionen zur Generierung von Lernmaterialien
- session_utils: Funktionen zur Session-Verwaltung
- utils_common: Gemeinsame Hilfsfunktionen
"""

from .ai_utils import *
from .content_analysis import *
# Importiere alle öffentlichen Komponenten aus den Submodulen
from .file_utils import *
from .learning_materials import *
from .session_utils import *
from .text_processing import *
from .utils_common import *

# Setze die __all__ Variable, um sicherzustellen, dass nur die gewünschten Elemente exportiert werden
__all__ = [
    # file_utils exports
    'save_file', 'read_file', 'validate_file_type', 'get_file_extension', 'get_file_hash',
    'get_mime_type', 'normalize_filename', 'is_valid_file',

    # text_processing exports
    'extract_text', 'split_text', 'count_tokens', 'detect_language', 'summarize_text',
    'get_text_statistics',

    # ai_utils exports
    'generate_embeddings', 'semantic_search', 'classify_text', 'extract_keywords',

    # content_analysis exports
    'analyze_content', 'extract_concepts', 'generate_concept_map', 'identify_topics',

    # learning_materials exports
    'generate_flashcards', 'generate_questions', 'generate_quiz', 'create_summary_notes',

    # session_utils exports
    'create_session', 'validate_session', 'extend_session', 'end_session',

    # utils_common exports
    'generate_uuid', 'format_timestamp', 'validate_input', 'sanitize_input'
]
