"""
Routes-Modul für das Questions-Paket (Refaktoriert)
------------------------------------

Enthält keine Routen mehr, da die Generierung im Worker stattfindet
und das Abrufen der Fragen zentral über /api/results/<session_id> erfolgt.
Diese Datei könnte potenziell gelöscht werden, wenn keine spezifischen
Questions-Routen mehr benötigt werden.
"""

import logging
import os

# Keine Routen mehr hier definiert, api_bp wird nicht mehr benötigt
# from api import api_bp 
# from api.auth import token_required
# from flask import current_app, g, jsonify, request

# Entferne Controller-Imports, da keine Routen mehr darauf zugreifen
# from .controllers import (
#    process_generate_more_questions,
#    process_generate_questions)
# from .schemas import QuestionRequestSchema

logger = logging.getLogger(__name__)

# CORS-Konfiguration entfernt, da keine Routen
# CORS_CONFIG = { ... }

# --- Veraltete Generierungs-Routen entfernt --- #

# @api_bp.route('/generate-more-questions', methods=['POST', 'OPTIONS'])
# def generate_more_questions_route():
#    ...

# @api_bp.route('/questions/generate/<session_id>', methods=['POST', 'OPTIONS'])
# def generate_questions_route(session_id):
#    ...

# --- Keine weiteren Routen in dieser Datei --- #
