"""
Utility-Funktionen für das Backend - WRAPPER
------------------------------------------

WARNUNG: Diese Datei wird aus Gründen der Abwärtskompatibilität beibehalten.
Für neue Implementierungen verwenden Sie bitte das Modul `api.utils`.

Diese Datei importiert alle nötigen Funktionen aus dem neuen modularen Utility-Modul,
um Abwärtskompatibilität mit bestehendem Code zu gewährleisten.
"""

# Importiere alle öffentlichen Komponenten aus dem neuen modularen System
from api.utils import *

# Logger, der Verwendung der alten API dokumentiert
import logging
logger = logging.getLogger(__name__)
logger.warning(
    "Die Datei utils.py wird verwendet, die aus Gründen der Abwärtskompatibilität beibehalten wird. "
    "Bitte verwenden Sie für neue Implementierungen das api.utils-Modul."
) 