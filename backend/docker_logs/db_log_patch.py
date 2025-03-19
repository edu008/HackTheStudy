"""
DB-Logging-Patch
--------------
Dieses Modul patcht SQLAlchemy, um alle Datenbank-Abfragen mit Emojis 
und schönem Datenformat zu loggen.
"""

import time
import logging
import functools
import json
from datetime import datetime

try:
    # Farbige Ausgaben und Datenformatierer importieren wenn verfügbar
    from .docker_data_formatter import (
        format_dict_summary, 
        format_list_summary,
        BLUE, GREEN, YELLOW, RED, CYAN, MAGENTA, BOLD, NC
    )
except ImportError:
    # Fallback-Definitionen wenn docker_data_formatter nicht verfügbar ist
    BLUE = GREEN = YELLOW = RED = CYAN = MAGENTA = BOLD = NC = ''
    def format_dict_summary(data, max_keys=3):
        return f"Dict mit {len(data)} Schlüsseln"
    def format_list_summary(data, max_items=3):
        return f"Liste mit {len(data)} Elementen"

# Emojis für verschiedene SQL-Operationen
SQL_EMOJIS = {
    'SELECT': '🔍',
    'INSERT': '➕',
    'UPDATE': '📝',
    'DELETE': '🗑️',
    'CREATE': '🏗️',
    'DROP': '💣',
    'ALTER': '🔧',
    'COMMIT': '✅',
    'ROLLBACK': '↩️',
    'BEGIN': '🔄',
    'JOIN': '🔗',
    'TRANSACTION': '📊',
    'EXECUTE': '⚡',
    'QUERY': '❓',
    'CONNECT': '🔌',
    'DISCONNECT': '🔌',
    'ERROR': '❌'
}

def get_query_type(query):
    """Bestimmt den Typ der SQL-Abfrage, um das passende Emoji zu wählen"""
    if not query:
        return 'QUERY'
    
    # Erstes Wort der Abfrage extrahieren
    first_word = query.strip().split(' ')[0].upper()
    
    if first_word in SQL_EMOJIS:
        return first_word
    
    # Versuche, eine teilweise Übereinstimmung zu finden
    for key in SQL_EMOJIS:
        if query.upper().startswith(key):
            return key
    
    return 'QUERY'

def get_query_emoji(query):
    """Gibt das Emoji für einen bestimmten SQL-Abfragetyp zurück"""
    query_type = get_query_type(query)
    return SQL_EMOJIS.get(query_type, SQL_EMOJIS['QUERY'])

# Logger für Datenbank-Operationen
db_logger = logging.getLogger('docker.db')

def patch_sqlalchemy():
    """
    Patcht SQLAlchemy's Engine, um alle Abfragen mit schönen Logs zu versehen
    """
    try:
        from sqlalchemy.engine import Engine
        from sqlalchemy import event
        
        @event.listens_for(Engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            conn.info.setdefault('query_start_time', []).append(time.time())
            
            # Log-Formatter für Debug-Logs
            emoji = get_query_emoji(statement)
            
            # Versuche, den Tabellennamen aus der Abfrage zu extrahieren
            table_name = "DB"
            try:
                # Einfache Heuristik - sucht nach FROM oder JOIN und nimmt das nächste Wort
                words = statement.upper().split()
                for i, word in enumerate(words):
                    if word in ("FROM", "JOIN", "INTO", "UPDATE") and i+1 < len(words):
                        table_name = words[i+1].strip(',;()')
                        break
            except:
                pass
            
            # Limitiere die Abfrage auf max. 80 Zeichen
            short_statement = ' '.join(statement.split())
            if len(short_statement) > 80:
                short_statement = short_statement[:77] + "..."
            
            # Bei Parameter-Ausgabe berücksichtigen, ob es sich um executemany handelt
            param_text = ""
            if parameters:
                if executemany:
                    param_count = len(parameters)
                    param_text = f" | {CYAN}Batch mit {param_count} Parameter-Sets{NC}"
                else:
                    # Begrenze die Anzeige auf wenige Parameter
                    param_preview = str(parameters)
                    if len(param_preview) > 50:
                        param_preview = param_preview[:47] + "..."
                    param_text = f" | {CYAN}Params: {param_preview}{NC}"
            
            db_logger.debug(f"{emoji} {short_statement}{param_text}",
                            extra={'data': {'query': statement, 'params': parameters}})
        
        @event.listens_for(Engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            start_time = conn.info['query_start_time'].pop(-1)
            total_time = time.time() - start_time
            
            # Log nur, wenn die Abfrage länger als 100ms gedauert hat (reduziert Log-Volumen)
            if total_time > 0.1:
                emoji = get_query_emoji(statement)
                
                # Versuche, die Anzahl der betroffenen Zeilen zu bekommen
                rows_affected = -1
                try:
                    if hasattr(cursor, 'rowcount'):
                        rows_affected = cursor.rowcount
                except:
                    pass
                
                # Formatiere die Zeit
                time_str = f"{total_time:.3f}s"
                if total_time < 0.01:
                    time_color = GREEN
                elif total_time < 0.1:
                    time_color = CYAN
                elif total_time < 0.5:
                    time_color = YELLOW
                else:
                    time_color = RED
                
                # Ergebnisse zusammenfassen
                if rows_affected >= 0:
                    rows_text = f"{rows_affected} Zeilen"
                    db_logger.info(f"{emoji} Abfrage abgeschlossen | {rows_text} in {time_color}{time_str}{NC}",
                                   extra={'data': {'duration': total_time, 'rows_affected': rows_affected}})
        
        # Log erfolgreiche Patching
        db_logger.info("SQLAlchemy erfolgreich gepatcht für verbesserte DB-Logs", 
                      extra={'emoji': '🔧'})
        return True
    
    except ImportError:
        db_logger.warning("SQLAlchemy nicht gefunden, DB-Logging-Patch wird übersprungen", 
                         extra={'emoji': '⚠️'})
        return False
    except Exception as e:
        db_logger.error(f"Fehler beim Patchen von SQLAlchemy: {e}", 
                       extra={'emoji': '❌'})
        return False

def patch_flask_sqlalchemy():
    """
    Patcht Flask-SQLAlchemy, um schöne Logs zu zeigen
    """
    try:
        import flask_sqlalchemy
        
        # Original-Methode speichern
        original_execute = flask_sqlalchemy.SQLAlchemy.execute
        
        @functools.wraps(original_execute)
        def patched_execute(self, *args, **kwargs):
            start_time = time.time()
            
            # Falls das erste Argument eine Abfrage ist, loggen wir sie
            query = None
            if args and isinstance(args[0], str):
                query = args[0]
                emoji = get_query_emoji(query)
                
                # Limitiere die Abfrage auf max. 80 Zeichen
                short_query = ' '.join(query.split())
                if len(short_query) > 80:
                    short_query = short_query[:77] + "..."
                
                # Parameter formatieren
                params = kwargs.get('params', None)
                if not params and len(args) > 1:
                    params = args[1]
                
                param_text = ""
                if params:
                    param_preview = str(params)
                    if len(param_preview) > 50:
                        param_preview = param_preview[:47] + "..."
                    param_text = f" | {CYAN}Params: {param_preview}{NC}"
                
                db_logger.debug(f"{emoji} {short_query}{param_text}",
                               extra={'data': {'query': query, 'params': params}})
            
            # Original-Methode aufrufen
            try:
                result = original_execute(self, *args, **kwargs)
                
                # Zeit messen und formatieren
                total_time = time.time() - start_time
                
                # Nur wichtige Abfragen loggen (länger als 100ms)
                if query and total_time > 0.1:
                    emoji = get_query_emoji(query)
                    time_str = f"{total_time:.3f}s"
                    
                    # Farbe basierend auf der Zeit auswählen
                    if total_time < 0.01:
                        time_color = GREEN
                    elif total_time < 0.1:
                        time_color = CYAN
                    elif total_time < 0.5:
                        time_color = YELLOW
                    else:
                        time_color = RED
                    
                    # Ergebnisse zusammenfassen
                    rows_text = "Abfrage erfolgreich"
                    if hasattr(result, 'rowcount'):
                        rows_text = f"{result.rowcount} Zeilen"
                    
                    db_logger.info(f"{emoji} Abfrage abgeschlossen | {rows_text} in {time_color}{time_str}{NC}",
                                  extra={'data': {'duration': total_time}})
                
                return result
            
            except Exception as e:
                # Fehler loggen
                if query:
                    db_logger.error(f"❌ SQL-Fehler: {str(e)}", 
                                   extra={'data': {'query': query}, 'emoji': '❌'})
                raise
        
        # Methode ersetzen
        flask_sqlalchemy.SQLAlchemy.execute = patched_execute
        
        # Log erfolgreiche Patching
        db_logger.info("Flask-SQLAlchemy erfolgreich gepatcht für verbesserte DB-Logs", 
                      extra={'emoji': '🔧'})
        return True
    
    except ImportError:
        db_logger.warning("Flask-SQLAlchemy nicht gefunden, DB-Logging-Patch wird übersprungen", 
                         extra={'emoji': '⚠️'})
        return False
    except Exception as e:
        db_logger.error(f"Fehler beim Patchen von Flask-SQLAlchemy: {e}", 
                       extra={'emoji': '❌'})
        return False

# Patch anwenden, wenn dieses Modul importiert wird
def apply_patches():
    """
    Wendet alle Patches an
    """
    sqlalchemy_patched = patch_sqlalchemy()
    flask_sqlalchemy_patched = patch_flask_sqlalchemy()
    
    return sqlalchemy_patched or flask_sqlalchemy_patched

# Automatisch Patches anwenden
success = apply_patches()

if __name__ == "__main__":
    # Demo, wenn Skript direkt ausgeführt wird
    if success:
        print(f"{GREEN}✅ DB-Logging-Patches erfolgreich angewendet{NC}")
        
        # Beispiel-Logs
        db_logger.info("🔄 DB-Verbindung hergestellt", extra={
            'data': {'db_type': 'postgresql', 'host': 'localhost', 'name': 'hackthestudy'},
            'emoji': '🔌'
        })
        
        db_logger.debug("🔍 SELECT * FROM users WHERE email = ?", extra={
            'data': {'params': ['test@example.com']},
            'emoji': '🔍'
        })
        
        db_logger.info("✅ Query abgeschlossen | 1 Zeilen in 0.015s", extra={
            'data': {'duration': 0.015, 'rows_affected': 1},
            'emoji': '✅'
        })
    else:
        print(f"{RED}❌ DB-Logging-Patches konnten nicht angewendet werden{NC}") 