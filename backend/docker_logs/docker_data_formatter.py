"""
Docker-Data-Formatter
--------------------
Dieses Modul stellt Formatierungsfunktionen für Daten in Docker-Logs bereit.
Es fasst Daten zusammen, anstatt sie detailliert auszugeben.
"""

import json
from typing import Any, Dict, List, Union, Optional
import time
from datetime import datetime
import sys

# ANSI Farbcodes
GREEN = '\033[0;32m'
BLUE = '\033[0;34m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
CYAN = '\033[0;36m'
MAGENTA = '\033[0;35m'
BOLD = '\033[1m'
NC = '\033[0m'  # No Color

# Emojis für Datentypen
DATA_EMOJIS = {
    'dict': '📋',
    'list': '📝',
    'array': '📊',
    'object': '📦',
    'string': '📄',
    'number': '🔢',
    'boolean': '⚖️',
    'null': '⛔',
    'pdf': '📑',
    'image': '🖼️',
    'user': '👤',
    'users': '👥',
    'file': '📄',
    'files': '🗂️',
    'result': '🏆',
    'error': '❌',
    'api': '🌐',
    'database': '🗃️',
    'job': '🔄',
    'task': '📝',
    'question': '❓',
    'answer': '✓',
    'flashcard': '📇',
    'time': '⏱️',
    'memory': '💾',
    'cpu': '⚙️',
}

def get_data_type_emoji(data_type: str) -> str:
    """Gibt das Emoji für einen bestimmten Datentyp zurück"""
    return DATA_EMOJIS.get(data_type.lower(), '📊')

def format_dict_summary(data: Dict[str, Any], max_keys: int = 3) -> str:
    """
    Formatiert ein Dictionary in einer zusammenfassenden Form
    Anstatt alle key-value-Paare anzuzeigen, wird nur die Anzahl der Schlüssel 
    und eine Vorschau der wichtigsten Schlüssel angezeigt
    """
    if not data:
        return f"{BLUE}{get_data_type_emoji('dict')} Leeres Dictionary{NC}"
    
    num_keys = len(data)
    preview_keys = list(data.keys())[:max_keys]
    
    # Bestimme Datentypen der Werte für die Vorschau
    type_info = []
    for key in preview_keys:
        value = data[key]
        if isinstance(value, dict):
            type_str = f"Dict[{len(value)}]"
        elif isinstance(value, list):
            type_str = f"Liste[{len(value)}]"
        elif isinstance(value, str):
            if len(value) > 20:
                type_str = f"String[{len(value)}]"
            else:
                type_str = f"'{value}'"
        else:
            type_str = str(value)
        type_info.append(f"{key}: {type_str}")
    
    # Schlüssel-Vorschau erstellen
    keys_preview = ", ".join(type_info)
    if num_keys > max_keys:
        keys_preview += f", ... ({num_keys - max_keys} weitere)"
    
    return f"{BLUE}{get_data_type_emoji('dict')} Dictionary mit {num_keys} Schlüsseln{NC} [{keys_preview}]"

def format_list_summary(data: List[Any], max_items: int = 3) -> str:
    """
    Formatiert eine Liste in einer zusammenfassenden Form
    Anstatt alle Elemente anzuzeigen, wird nur die Anzahl der Elemente
    und eine Vorschau der ersten Elemente angezeigt
    """
    if not data:
        return f"{BLUE}{get_data_type_emoji('list')} Leere Liste{NC}"
    
    num_items = len(data)
    
    # Bestimme, ob die Liste homogen ist (alle Elemente haben den gleichen Typ)
    element_types = set(type(item).__name__ for item in data)
    is_homogeneous = len(element_types) == 1
    
    # Für homogene Listen zeigen wir einen einfacheren Typ an
    if is_homogeneous:
        type_name = next(iter(element_types))
        
        # Für Listen von Dictionaries, zeige die gemeinsamen Schlüssel an
        if type_name == 'dict' and all(isinstance(item, dict) for item in data):
            common_keys = set.intersection(*[set(item.keys()) for item in data]) if data else set()
            preview = f"mit gemeinsamen Schlüsseln: {', '.join(sorted(common_keys))}" if common_keys else ""
            return f"{BLUE}{get_data_type_emoji('list')} Liste mit {num_items} {type_name}-Objekten{NC} {preview}"
        
        return f"{BLUE}{get_data_type_emoji('list')} Liste mit {num_items} {type_name}-Objekten{NC}"
    
    # Für heterogene Listen zeigen wir eine Verteilung der Typen an
    type_counts = {}
    for item_type in element_types:
        type_counts[item_type] = sum(1 for item in data if type(item).__name__ == item_type)
    
    type_info = [f"{count}x {t}" for t, count in type_counts.items()]
    return f"{BLUE}{get_data_type_emoji('list')} Heterogene Liste mit {num_items} Elementen{NC} [{', '.join(type_info)}]"

def format_value(value: Any) -> str:
    """
    Formatiert einen einzelnen Wert in einer zusammenfassenden Form
    basierend auf seinem Typ
    """
    if value is None:
        return f"{BLUE}{get_data_type_emoji('null')} None{NC}"
    
    if isinstance(value, dict):
        return format_dict_summary(value)
    
    if isinstance(value, list):
        return format_list_summary(value)
    
    if isinstance(value, str):
        if len(value) > 100:
            return f"{BLUE}{get_data_type_emoji('string')} String mit {len(value)} Zeichen{NC}"
        return f"{BLUE}'{value}'{NC}"
    
    if isinstance(value, (int, float)):
        return f"{BLUE}{get_data_type_emoji('number')} {value}{NC}"
    
    if isinstance(value, bool):
        return f"{BLUE}{get_data_type_emoji('boolean')} {value}{NC}"
    
    return f"{BLUE}{type(value).__name__}: {str(value)}{NC}"

def summarize_data(data: Any, context: str = None) -> str:
    """
    Fasst beliebige Daten zusammen und gibt eine für Docker-Logs geeignete
    Darstellung zurück
    """
    # Wenn Kontext angegeben wurde, prefix hinzufügen
    prefix = f"{MAGENTA}{context}{NC}: " if context else ""
    
    # Je nach Typ unterschiedlich formatieren
    if isinstance(data, dict):
        return f"{prefix}{format_dict_summary(data)}"
    
    if isinstance(data, list):
        return f"{prefix}{format_list_summary(data)}"
    
    # Für primitive Typen oder unbekannte Objekte
    return f"{prefix}{format_value(data)}"

def print_data_summary(data: Any, context: str = None, emoji: str = None) -> None:
    """
    Druckt die Zusammenfassung der Daten auf die Konsole
    """
    emoji_str = f"{DATA_EMOJIS.get(emoji, '📊')} " if emoji else ""
    
    if context:
        print(f"{emoji_str}{CYAN}{context}{NC}:")
    
    print(summarize_data(data))

def print_progress(message: str, progress: float, emoji: str = "⏱️") -> None:
    """
    Zeigt einen Fortschrittsbalken an
    
    Args:
        message: Die Nachricht, die angezeigt werden soll
        progress: Ein Wert zwischen 0 und 1, der den Fortschritt angibt
        emoji: Ein Emoji, das vor der Nachricht angezeigt wird
    """
    progress = min(1.0, max(0.0, progress))
    bar_length = 30
    
    # Anzahl der Balken basierend auf dem Fortschritt
    filled_length = int(bar_length * progress)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    
    # Formatiere den Prozentsatz
    percent = int(progress * 100)
    
    # Ausgabe mit ANSI-Farben
    sys.stdout.write(f"\r{emoji} {CYAN}{message}{NC} [{GREEN}{bar}{NC}] {YELLOW}{percent}%{NC}")
    sys.stdout.flush()
    
    # Neue Zeile bei 100%
    if progress >= 1.0:
        print()

def print_loading_spinner(message: str, duration: int = 3) -> None:
    """
    Zeigt eine Ladeanimation für die angegebene Dauer
    
    Args:
        message: Die Nachricht, die angezeigt werden soll
        duration: Die Dauer in Sekunden
    """
    spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    end_time = time.time() + duration
    
    i = 0
    try:
        while time.time() < end_time:
            i = (i + 1) % len(spinner_chars)
            sys.stdout.write(f"\r{spinner_chars[i]} {CYAN}{message}{NC}...")
            sys.stdout.flush()
            time.sleep(0.1)
        
        sys.stdout.write(f"\r{GREEN}✅ {message} abgeschlossen{NC}     \n")
        sys.stdout.flush()
    except KeyboardInterrupt:
        sys.stdout.write("\r")
        sys.stdout.flush()

def format_log_message(message: str, data: Any = None, level: str = "INFO") -> str:
    """
    Formatiert eine Log-Nachricht mit optionalen Daten
    
    Args:
        message: Die Log-Nachricht
        data: Optionale Daten, die zusammengefasst werden sollen
        level: Das Log-Level (INFO, WARNING, ERROR, DEBUG)
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    # Log-Level formatieren
    if level == "INFO":
        level_color = GREEN
        emoji = "ℹ️"
    elif level == "WARNING":
        level_color = YELLOW
        emoji = "⚠️"
    elif level == "ERROR":
        level_color = RED
        emoji = "❌"
    elif level == "DEBUG":
        level_color = BLUE
        emoji = "🔍"
    else:
        level_color = CYAN
        emoji = "📝"
    
    # Grundnachricht formatieren
    formatted_message = f"{BLUE}[{timestamp}]{NC} {emoji} {level_color}{message}{NC}"
    
    # Daten hinzufügen, falls vorhanden
    if data is not None:
        if isinstance(data, dict):
            data_summary = format_dict_summary(data)
        elif isinstance(data, list):
            data_summary = format_list_summary(data)
        else:
            data_summary = format_value(data)
        
        formatted_message += f"\n    {data_summary}"
    
    return formatted_message

# Einfache Beispielfunktion zur Demonstration
def demo():
    """Demonstriert die Formatierungsfunktionen"""
    
    # Beispiel: Dictionary zusammenfassen
    user_data = {
        "id": 12345,
        "name": "Max Mustermann",
        "email": "max@example.com",
        "roles": ["admin", "user"],
        "preferences": {"theme": "dark", "language": "de", "notifications": True},
        "last_login": "2023-08-15T14:30:00Z",
        "sessions": [{"id": "abc123", "ip": "192.168.1.1"}, {"id": "def456", "ip": "192.168.1.2"}]
    }
    print(format_log_message("Benutzer angemeldet", user_data))
    
    # Beispiel: Liste zusammenfassen
    tasks = [
        {"id": 1, "title": "Aufgabe 1", "status": "completed", "priority": "high"},
        {"id": 2, "title": "Aufgabe 2", "status": "pending", "priority": "medium"},
        {"id": 3, "title": "Aufgabe 3", "status": "in_progress", "priority": "low"},
        {"id": 4, "title": "Aufgabe 4", "status": "pending", "priority": "high"},
        {"id": 5, "title": "Aufgabe 5", "status": "completed", "priority": "medium"}
    ]
    print(format_log_message("Aufgaben geladen", tasks))
    
    # Beispiel: Fortschrittsbalken
    print("\nFortschrittsbalken-Demo:")
    for i in range(11):
        print_progress("Verarbeite Datei", i/10, "📄")
        time.sleep(0.2)
    
    # Beispiel: Ladeanimation
    print("\nLadeanimation-Demo:")
    print_loading_spinner("Lade Daten", 3)
    
    # Beispiel: Fehlernachricht
    error_data = {"code": 404, "message": "Ressource nicht gefunden", "details": {"path": "/api/v1/users/999"}}
    print(format_log_message("Fehler bei API-Anfrage", error_data, "ERROR"))

if __name__ == "__main__":
    # Führt die Demo aus, wenn diese Datei direkt ausgeführt wird
    demo() 