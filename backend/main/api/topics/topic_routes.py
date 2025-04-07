"""
Blueprint-Registrierungsfunktion für Topics
"""

import logging # Import logging
from flask import Blueprint, current_app
from . import topics_bp  # Importiere topics_bp aus dem api.topics-Modul

logger = logging.getLogger(__name__) # Erstelle den Logger

def register_topic_routes(api_bp):
    """
    Registriert die Topics-Routen am angegebenen Blueprint
    """
    # Verwende den Standard-Logger
    logger.info(f"Registriere topics_bp an Blueprint {api_bp.name} unter /topics")
    # current_app.logger.info(f"Registriere topics_bp an Blueprint {api_bp.name} unter /topics")
    api_bp.register_blueprint(topics_bp, url_prefix='/topics') 