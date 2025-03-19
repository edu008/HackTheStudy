"""
Docker Logs Paket
----------------
Dieses Paket enthält alle Funktionen und Module für verbesserte Docker-Logs.
Es exportiert wichtige Funktionen und Klassen, damit sie einfach importiert werden können.
"""

# Exportiere wichtige Funktionen und Klassen aus den Modulen
try:
    # Banner und visuelle Elemente
    from .docker_banner import print_banner, animate_loading, print_service_status, show_startup_animation

    # Daten-Formatierung
    from .docker_data_formatter import (
        format_dict_summary,
        format_list_summary, 
        summarize_data,
        print_progress,
        print_loading_spinner,
        format_log_message,
        # Farbkonstanten
        BLUE, GREEN, YELLOW, RED, CYAN, MAGENTA, BOLD, NC,
        # Emojis
        DATA_EMOJIS
    )

    # Docker Logging Integration
    from .docker_logging_integration import (
        setup_docker_logging,
        integrate_flask_logging,
        patch_flask_app,
        DockerFormatter,
        # Logger
        api_logger,
        db_logger,
        worker_logger,
        auth_logger,
        app_logger,
        # Hilfsfunktionen
        log_request_start,
        log_request_end,
        log_db_query,
        log_auth_event,
        log_worker_task,
        log_worker_result,
        log_app_event
    )

    # DB-Logging
    from .db_log_patch import (
        patch_sqlalchemy,
        patch_flask_sqlalchemy,
        apply_patches,
        SQL_EMOJIS
    )

    # Zeige Info, dass das Paket erfolgreich geladen wurde
    print("\033[0;32m✅ Docker-Logs-Paket erfolgreich geladen\033[0m")

except ImportError as e:
    # Wenn ein Import fehlschlägt, gib eine Warnung aus
    print(f"\033[0;33m⚠️ Warnung: Einige Docker-Log-Module konnten nicht geladen werden: {e}\033[0m")

# Funktion zum schnellen Setup des gesamten Logging-Systems
def setup_all_logging(app=None):
    """
    Richtet das gesamte Logging-System ein.
    """
    from .docker_logging_integration import setup_docker_logging, integrate_flask_logging
    from .db_log_patch import apply_patches
    
    # Logger einrichten
    loggers = setup_docker_logging()
    
    # DB-Patches anwenden
    apply_patches()
    
    # Falls eine Flask-App übergeben wurde, integriere Logging
    if app:
        integrate_flask_logging(app, loggers)
    
    return loggers 