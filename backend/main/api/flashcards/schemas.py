"""
Schemas-Modul für das Flashcards-Paket
------------------------------------

Dieses Modul enthält die Marshmallow-Schemas für die Validierung der API-Anfragen
und Antworten im Zusammenhang mit Flashcards.
"""

from marshmallow import Schema, fields, ValidationError

class FlashcardRequestSchema(Schema):
    """Schema für Anfragen zur Generierung von Flashcards."""
    session_id = fields.Str(required=True)
    count = fields.Int(required=True, validate=lambda n: n > 0)
    topic_filter = fields.List(fields.Str(), required=False)

class FlashcardDataSchema(Schema):
    """Schema für die Struktur einer Lernkarte."""
    front = fields.Str(required=True)
    back = fields.Str(required=True)
    category = fields.Str(required=False, allow_none=True)
    difficulty = fields.Int(required=False, allow_none=True, validate=lambda n: 1 <= n <= 5 if n is not None else True)

class FlashcardResponseSchema(Schema):
    """Schema für die Antwort bei Flashcard-Anfragen."""
    success = fields.Bool(required=True)
    message = fields.Str(required=False)
    flashcards = fields.List(fields.Nested(FlashcardDataSchema), required=False)
    error = fields.Str(required=False)
    error_type = fields.Str(required=False)
    credits_available = fields.Float(required=False)

class FlashcardStudySessionSchema(Schema):
    """Schema für Lernkarten-Studiensitzungen."""
    session_id = fields.Str(required=True)
    flashcard_ids = fields.List(fields.Int(), required=True)
    settings = fields.Dict(required=False)

class FlashcardFeedbackSchema(Schema):
    """Schema für Feedback zu Lernkarten."""
    flashcard_id = fields.Int(required=True)
    difficulty = fields.Int(required=True, validate=lambda n: 1 <= n <= 5)
    feedback = fields.Str(required=False)
    is_correct = fields.Bool(required=False)
    time_spent = fields.Int(required=False)  # Zeit in Sekunden 