"""
Fehlerantworten
------------

Dieses Modul bietet Funktionen zum Erstellen standardisierter Fehlerantworten
für API-Endpunkte mit konsistenter Struktur und Statuscodes.
"""

from flask import jsonify
from .constants import ERROR_STATUS_CODES, ERROR_UNKNOWN

def create_error_response(error_message, error_type=ERROR_UNKNOWN, additional_data=None, http_status=None):
    """
    Erstellt eine standardisierte Fehlerantwort.
    
    Args:
        error_message: Die Fehlermeldung
        error_type: Der Typ des Fehlers (aus den ERROR_* Konstanten)
        additional_data: Zusätzliche Daten, die in die Antwort aufgenommen werden sollen
        http_status: Optionaler HTTP-Statuscode (überschreibt den Standardwert)
        
    Returns:
        Ein jsonify-Response-Objekt mit standardisierter Fehlerstruktur 
        und passendem HTTP-Statuscode
    """
    if http_status is None:
        http_status = ERROR_STATUS_CODES.get(error_type, 500)
    
    response = {
        "success": False,
        "error": {
            "code": error_type,
            "message": error_message
        }
    }
    
    if additional_data:
        response["error"].update(additional_data)
    
    # CORS-Header werden automatisch durch den globalen after_request Handler in app.py hinzugefügt
    return jsonify(response), http_status 