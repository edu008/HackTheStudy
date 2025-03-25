"""
Validierungsfunktionen für verschiedene Eingabedaten.
"""

import re
import uuid
import logging
from typing import Union, Tuple, Optional

# Logger konfigurieren
logger = logging.getLogger(__name__)

def validate_session_id(session_id: str) -> bool:
    """
    Validiert eine Session-ID.
    
    Args:
        session_id: Die zu validierende Session-ID
    
    Returns:
        True wenn gültig, False sonst
    """
    try:
        # Versuche, die Session-ID als UUID zu parsen
        uuid_obj = uuid.UUID(session_id)
        # Prüfe, ob die UUID im String-Format der übergebenen ID entspricht
        return str(uuid_obj) == session_id
    except (ValueError, AttributeError, TypeError):
        return False

def validate_email(email: str) -> bool:
    """
    Validiert eine E-Mail-Adresse.
    
    Args:
        email: Die zu validierende E-Mail-Adresse
    
    Returns:
        True wenn gültig, False sonst
    """
    if not email or not isinstance(email, str):
        return False
    
    # Einfacher E-Mail-Regex
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_password(password: str, min_length: int = 8) -> Tuple[bool, Optional[str]]:
    """
    Validiert ein Passwort nach Sicherheitskriterien.
    
    Args:
        password: Das zu validierende Passwort
        min_length: Minimale Länge des Passworts
    
    Returns:
        Tuple aus (gültig, Fehlermeldung oder None)
    """
    if not password or not isinstance(password, str):
        return False, "Passwort darf nicht leer sein"
    
    if len(password) < min_length:
        return False, f"Passwort muss mindestens {min_length} Zeichen lang sein"
    
    # Prüfe auf Zahlen
    if not re.search(r'\d', password):
        return False, "Passwort muss mindestens eine Zahl enthalten"
    
    # Prüfe auf Großbuchstaben
    if not re.search(r'[A-Z]', password):
        return False, "Passwort muss mindestens einen Großbuchstaben enthalten"
    
    # Prüfe auf Kleinbuchstaben
    if not re.search(r'[a-z]', password):
        return False, "Passwort muss mindestens einen Kleinbuchstaben enthalten"
    
    # Prüfe auf Sonderzeichen
    if not re.search(r'[^a-zA-Z0-9]', password):
        return False, "Passwort muss mindestens ein Sonderzeichen enthalten"
    
    return True, None

def validate_filename(filename: str, allowed_extensions: set = None) -> Tuple[bool, Optional[str]]:
    """
    Validiert einen Dateinamen.
    
    Args:
        filename: Der zu validierende Dateiname
        allowed_extensions: Set mit erlaubten Dateierweiterungen (z.B. {'.pdf', '.docx'})
    
    Returns:
        Tuple aus (gültig, Fehlermeldung oder None)
    """
    if not filename or not isinstance(filename, str):
        return False, "Dateiname darf nicht leer sein"
    
    # Säubere den Dateinamen (entferne Pfade)
    clean_filename = filename.split('/')[-1].split('\\')[-1]
    
    # Prüfe auf ungültige Zeichen
    if re.search(r'[<>:"/\\|?*]', clean_filename):
        return False, "Dateiname enthält ungültige Zeichen"
    
    # Prüfe die Dateierweiterung, falls angegeben
    if allowed_extensions:
        ext = '.' + clean_filename.split('.')[-1].lower() if '.' in clean_filename else ''
        if ext not in allowed_extensions:
            allowed_ext_list = ', '.join(allowed_extensions)
            return False, f"Ungültige Dateierweiterung. Erlaubt sind: {allowed_ext_list}"
    
    return True, None 