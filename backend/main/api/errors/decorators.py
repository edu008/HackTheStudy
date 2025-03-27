"""
Fehlerbehandlungs-Dekoratoren
-------------------------

Dieses Modul bietet Dekoratoren für Funktionen, die eine einheitliche
Fehlerbehandlung und -absicherung benötigen.
"""

from functools import wraps

from .logging import log_error


def safe_transaction(func):
    """
    Dekorator für sichere Datenbanktransaktionen.
    Stellt sicher, dass bei Ausnahmen ein Rollback durchgeführt wird.

    Usage:
        @safe_transaction
        def my_db_function(db_session, ...):
            # Datenbank-Operationen

    Returns:
        Eine dekorierte Funktion mit automatischem Rollback bei Ausnahmen
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        from core.models import db

        try:
            return func(*args, **kwargs)
        except Exception as e:
            db.session.rollback()
            log_error(e, endpoint=func.__name__)
            raise

    return wrapper
