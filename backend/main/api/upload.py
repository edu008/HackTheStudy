"""
Upload-Funktionalität für das Backend - WRAPPER
---------------------------------------------

WARNUNG: Diese Datei wird aus Gründen der Abwärtskompatibilität beibehalten.
Für neue Implementierungen verwenden Sie bitte das Modul `api.uploads`.

Diese Datei importiert alle nötigen Funktionen aus dem neuen modularen Upload-Modul,
um Abwärtskompatibilität mit bestehendem Code zu gewährleisten.
"""

# Importiere alle öffentlichen Komponenten aus dem neuen modularen System
from api.uploads import *

# Logger, der Verwendung der alten API dokumentiert
import logging
logger = logging.getLogger(__name__)
logger.warning(
    "Die Datei upload.py wird verwendet, die aus Gründen der Abwärtskompatibilität beibehalten wird. "
    "Bitte verwenden Sie für neue Implementierungen das api.uploads-Modul."
) 