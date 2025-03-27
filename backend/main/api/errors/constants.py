"""
Fehlerkonstanten und Statuscodes
------------------------------

Dieses Modul definiert einheitliche Fehlerkonstanten und ihre zugehörigen HTTP-Statuscodes,
die in der gesamten Anwendung verwendet werden.
"""

# Fehlertyp-Konstanten für einheitliche Fehlerbehandlung
ERROR_INVALID_INPUT = "invalid_input"
ERROR_AUTHENTICATION = "authentication_error"
ERROR_PERMISSION = "permission_denied"
ERROR_NOT_FOUND = "resource_not_found"
ERROR_DATABASE = "database_error"
ERROR_PROCESSING = "processing_error"
ERROR_INSUFFICIENT_CREDITS = "insufficient_credits"
ERROR_API_ERROR = "api_error"
ERROR_TOKEN_LIMIT = "token_limit"
ERROR_RATE_LIMIT = "rate_limit"
ERROR_MAX_RETRIES = "max_retries"
ERROR_CACHE_ERROR = "cache_error"
ERROR_CREDIT_DEDUCTION_FAILED = "credit_deduction_failed"
ERROR_FILE_PROCESSING = "file_processing_error"
ERROR_SESSION_CONFLICT = "session_conflict"
ERROR_UNKNOWN = "unknown_error"

# HTTP-Statuscodes für verschiedene Fehlertypen
ERROR_STATUS_CODES = {
    ERROR_INVALID_INPUT: 400,
    ERROR_AUTHENTICATION: 401,
    ERROR_PERMISSION: 403,
    ERROR_NOT_FOUND: 404,
    ERROR_DATABASE: 500,
    ERROR_PROCESSING: 500,
    ERROR_INSUFFICIENT_CREDITS: 402,
    ERROR_API_ERROR: 500,
    ERROR_TOKEN_LIMIT: 413,
    ERROR_RATE_LIMIT: 429,
    ERROR_MAX_RETRIES: 503,
    ERROR_CACHE_ERROR: 500,
    ERROR_CREDIT_DEDUCTION_FAILED: 402,
    ERROR_FILE_PROCESSING: 400,
    ERROR_SESSION_CONFLICT: 409,
    ERROR_UNKNOWN: 500
}
