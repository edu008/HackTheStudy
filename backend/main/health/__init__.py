"""
Health-Monitoring-Komponenten für den API-Container.
Enthält Module für verschiedene Aspekte des Gesundheitsmonitorings.
"""

# Exportiere öffentliche API aus den Modulen
from .base import (
    get_health_status,
    track_api_request,
    track_api_error,
    set_health_status
)

from .monitor_thread import (
    start_health_monitoring,
    stop_health_monitoring,
    update_health_data,
    run_standalone
)

from .connections import (
    check_db_connection,
    check_redis_connection,
    check_celery_connection,
    store_health_in_redis
)

from .resources import (
    get_memory_usage,
    get_cpu_usage,
    get_open_file_descriptors,
    get_system_info
)

# Für Abwärtskompatibilität
start_health_monitor = start_health_monitoring

__all__ = [
    # Basis-Funktionalität
    'get_health_status',
    'track_api_request',
    'track_api_error',
    'set_health_status',
    
    # Thread-Management
    'start_health_monitoring',
    'stop_health_monitoring',
    'update_health_data',
    'run_standalone',
    
    # Verbindungsprüfungen
    'check_db_connection',
    'check_redis_connection',
    'check_celery_connection',
    'store_health_in_redis',
    
    # Ressourcenüberwachung
    'get_memory_usage',
    'get_cpu_usage',
    'get_open_file_descriptors',
    'get_system_info',
    
    # Abwärtskompatibilität
    'start_health_monitor'
]

# Falls dieses Modul direkt ausgeführt wird, starte das Monitoring im Standalone-Modus
if __name__ == "__main__":
    run_standalone() 