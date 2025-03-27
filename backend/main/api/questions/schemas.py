"""
Validierungsschemas für Fragen
---------------------------

Dieses Modul enthält Validierungsschemas für Fragen und Anfragen
zur Generierung von Fragen.
"""

from marshmallow import Schema, fields, ValidationError

class QuestionRequestSchema(Schema):
    """
    Schema zur Validierung von Anfragen zur Generierung von Fragen.
    
    Felder:
    - session_id: Die ID der Sitzung, für die Fragen generiert werden sollen
    - count: Die Anzahl der zu generierenden Fragen (muss > 0 sein)
    """
    session_id = fields.Str(required=True)
    count = fields.Int(required=True, validate=lambda n: n > 0)

class QuestionSchema(Schema):
    """
    Schema zur Validierung von Fragen.
    
    Felder:
    - text: Der Text der Frage
    - options: Die Antwortoptionen als Liste
    - correct: Der Index der korrekten Antwortoption
    - explanation: Die Erklärung zur korrekten Antwort (optional)
    """
    text = fields.Str(required=True)
    options = fields.List(fields.Str(), required=True)
    correct = fields.Int(required=True)
    explanation = fields.Str(required=False)

class GenerateQuestionsRequestSchema(Schema):
    """
    Schema zur Validierung von Anfragen zum Generieren von Fragen für eine Sitzung.
    
    Felder:
    - count: Die Anzahl der zu generierenden Fragen (optional, Default: 10)
    """
    count = fields.Int(required=False, validate=lambda n: n > 0, default=10)

class GenerateMoreQuestionsRequestSchema(Schema):
    """
    Schema zur Validierung von Anfragen zum Generieren zusätzlicher Fragen.
    
    Felder:
    - session_id: Die ID der Sitzung, für die Fragen generiert werden sollen
    - count: Die Anzahl der zu generierenden Fragen (optional, Default: 3)
    - timestamp: Ein Zeitstempel zur Vermeidung von Caching (optional)
    """
    session_id = fields.Str(required=True)
    count = fields.Int(required=False, validate=lambda n: n > 0, default=3)
    timestamp = fields.Str(required=False) 