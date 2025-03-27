"""
Topics-Funktionalität für das Backend - WRAPPER
--------------------------------------------

WARNUNG: Diese Datei wird zur Abwärtskompatibilität beibehalten.
Für neue Implementierungen verwenden Sie bitte das Modul `api.topics`.

Diese Datei importiert alle notwendigen Funktionen aus dem neuen modularen Topics-Modul,
um Abwärtskompatibilität mit bestehendem Code zu gewährleisten.
"""

# Importiere alle öffentlichen Komponenten aus dem neuen modularen System
from flask import Blueprint
from . import api_bp

# Steuere unsere Blueprint-Routen mit dem Blueprint des modularen Topics-Moduls
from api.topics.routes import *

# Importiere alle notwendigen Funktionen explizit
from api.topics.generation import generate_topics, generate_related_topics
from api.topics.concept_map import generate_concept_map_suggestions
from api.topics.models import get_topic_hierarchy, create_topic, create_connection
from api.topics.utils import process_topic_response, find_upload_by_session, build_topic_prompt

# Logger, der Verwendung der alten API dokumentiert
import logging
logger = logging.getLogger(__name__)
logger.warning(
    "Die Datei topics.py wird verwendet, die aus Gründen der Abwärtskompatibilität beibehalten wird. "
    "Bitte verwenden Sie für neue Implementierungen das api.topics-Modul."
)
