"""
Benutzerdefinierte Ausnahmen
-----------------------

Dieses Modul definiert spezialisierte Ausnahmeklassen für verschiedene Fehlertypen
in der API mit einheitlichem Verhalten und Mapping zu HTTP-Statuscodes.
"""

from .constants import (ERROR_AUTHENTICATION, ERROR_DATABASE,
                        ERROR_FILE_PROCESSING, ERROR_INSUFFICIENT_CREDITS,
                        ERROR_INVALID_INPUT, ERROR_NOT_FOUND, ERROR_PERMISSION,
                        ERROR_UNKNOWN)
from .responses import create_error_response


class APIError(Exception):
    """
    Basisklasse für benutzerdefinierte API-Fehler.
    Ermöglicht eine einfache Erzeugung von standardisierten Fehlerantworten.
    """

    def __init__(self, message, error_type=ERROR_UNKNOWN, additional_data=None, http_status=None):
        self.message = message
        self.error_type = error_type
        self.additional_data = additional_data or {}
        self.http_status = http_status
        super().__init__(self.message)

    def to_response(self):
        """Konvertiert den Fehler in eine standardisierte API-Antwort."""
        return create_error_response(
            self.message,
            self.error_type,
            self.additional_data,
            self.http_status
        )

# Spezialisierte Fehlerklassen für häufige Fehlertypen


class InvalidInputError(APIError):
    """Fehler bei ungültigen Eingabedaten."""

    def __init__(self, message, additional_data=None):
        super().__init__(message, ERROR_INVALID_INPUT, additional_data)


class AuthenticationError(APIError):
    """Fehler bei der Authentifizierung."""

    def __init__(self, message, additional_data=None):
        super().__init__(message, ERROR_AUTHENTICATION, additional_data)


class APIPermissionError(APIError):
    """Fehler bei fehlenden Berechtigungen."""

    def __init__(self, message, additional_data=None):
        super().__init__(message, ERROR_PERMISSION, additional_data)


class ResourceNotFoundError(APIError):
    """Fehler bei nicht gefundenen Ressourcen."""

    def __init__(self, message, additional_data=None):
        super().__init__(message, ERROR_NOT_FOUND, additional_data)


class DatabaseError(APIError):
    """Fehler bei Datenbankoperationen."""

    def __init__(self, message, additional_data=None):
        super().__init__(message, ERROR_DATABASE, additional_data)


class InsufficientCreditsError(APIError):
    """Fehler bei unzureichenden Guthaben."""

    def __init__(self, message, required_credits=None, available_credits=None):
        additional_data = {}
        if required_credits is not None:
            additional_data["credits_required"] = required_credits
        if available_credits is not None:
            additional_data["credits_available"] = available_credits
        super().__init__(message, ERROR_INSUFFICIENT_CREDITS, additional_data)


class FileProcessingError(APIError):
    """Fehler bei der Dateiverarbeitung."""

    def __init__(self, message, additional_data=None):
        super().__init__(message, ERROR_FILE_PROCESSING, additional_data)
