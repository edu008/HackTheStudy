import os
from celery import Celery

# Ermittle den optimalen Pool-Typ basierend auf Umgebung
# 'prefork' ist besser für CPU-gebundene Aufgaben
# 'gevent' ist besser für I/O-gebundene Aufgaben (API-Aufrufe)
# 'solo' ist für die einfachste Konfiguration
CELERY_POOL_TYPE = os.environ.get('CELERY_POOL', 'gevent')

# Basis-Anzahl der Worker - Kann über Umgebungsvariable angepasst werden
BASE_CONCURRENCY = 2 if CELERY_POOL_TYPE == 'gevent' else 1

# Worker-Parallelität basierend auf verfügbaren CPU-Kernen
# Bei 'solo' bleibt es bei 1, ansonsten skalieren wir
if CELERY_POOL_TYPE == 'solo':
    CONCURRENCY = 1
else:
    import multiprocessing
    # Verwende die Hälfte der verfügbaren CPU-Kerne (mindestens BASE_CONCURRENCY)
    CONCURRENCY = max(BASE_CONCURRENCY, multiprocessing.cpu_count() // 2)
    # Begrenze auf maximal 8 Worker, um Ressourcenübernutzung zu vermeiden
    CONCURRENCY = min(CONCURRENCY, int(os.environ.get('MAX_CONCURRENCY', '8')))

# Erweiterte Konfigurationswerte aus Umgebungsvariablen
TASK_TIME_LIMIT = int(os.environ.get('CELERY_TASK_TIME_LIMIT', '3600'))  # 1 Stunde Standard
TASK_SOFT_TIME_LIMIT = TASK_TIME_LIMIT - 60  # 1 Minute früher als Hard-Limit

# Verbesserte Konfiguration für bessere Skalierbarkeit und Stabilität
celery_config = {
    # Worker-Konfiguration
    'worker_pool': CELERY_POOL_TYPE,
    'worker_concurrency': CONCURRENCY,
    'worker_prefetch_multiplier': 1,  # Reduzieren für gleichmäßigere Verteilung
    'worker_max_tasks_per_child': 200,  # Verhindert Speicherlecks
    'worker_max_memory_per_child': 350000,  # 350MB - Worker neustarten
    
    # Task-Ausführungskonfiguration
    'task_acks_late': True,  # Bestätige Tasks erst nach erfolgreicher Ausführung
    'task_reject_on_worker_lost': True,  # Zurück in die Warteschlange bei Worker-Ausfall
    'task_time_limit': TASK_TIME_LIMIT,  # Maximale Laufzeit für Tasks
    'task_soft_time_limit': TASK_SOFT_TIME_LIMIT,  # Soft-Limit für Tasks
    
    # Retry-Konfiguration
    'task_default_rate_limit': '10/m',  # Begrenze Rate auf 10 pro Minute
    'broker_connection_retry': True,  # Automatische Wiederverbindung
    'broker_connection_retry_on_startup': True,  # Wiederverbindung beim Start
    'broker_connection_max_retries': 10,  # Maximale Anzahl an Wiederverbindungen
    
    # Logging und Überwachung
    'worker_hijack_root_logger': False,  # Eigene Logger-Konfiguration
    'worker_log_color': False,  # Keine Farben für DigitalOcean Logs
    
    # Optimierungen
    'worker_proc_alive_timeout': 60.0,  # 60s warten auf Worker-Start
    'result_expires': 3600,  # Ergebnisse nach 1 Stunde löschen
    'broker_heartbeat': 10,  # 10s Heartbeat für bessere Verbindungsstabilität
    'broker_transport_options': {
        'visibility_timeout': 18000,  # 5 Stunden Sichtbarkeits-Timeout
        'socket_timeout': 60,  # 60s Socket-Timeout
        'socket_connect_timeout': 60,  # 60s Verbindungs-Timeout
    },
    
    # Task-Serialisierung
    'task_serializer': 'json',
    'result_serializer': 'json',
    'accept_content': ['json'],
}

def configure_celery(app):
    """
    Konfiguriert eine Celery-Instanz mit optimierten Einstellungen.
    
    Args:
        app: Die Celery-Anwendung, die konfiguriert werden soll
        
    Returns:
        Die konfigurierte Celery-Anwendung
    """
    # Wende die Konfiguration an
    app.conf.update(**celery_config)
    
    # Logging zur Konfiguration
    print(f"Celery konfiguriert mit Pool: {CELERY_POOL_TYPE}, Concurrency: {CONCURRENCY}")
    
    return app

broker_url = 'redis://redis:6379/0'
result_backend = 'redis://redis:6379/0'

# Liste der Module, die Celery-Tasks enthalten
imports = ('tasks',)

# Aufgabenzeitlimits
task_time_limit = 14400  # 4 Stunden Maximalzeit für Tasks (erhöht von 2 Stunden)
task_soft_time_limit = 12600  # 3.5 Stunden Soft-Limit für Tasks (erhöht von 1 Stunde)

# Konfiguration von Task-Serialisierung
task_serializer = 'json'
accept_content = ['json']  # Akzeptiere nur JSON-Tasks
result_serializer = 'json'

# Pool-Konfiguration - Verwende solo statt threads oder Prozesse
worker_pool = 'solo'  # Vermeidet Probleme mit Multiprocessing & Dateidescriptoren
worker_concurrency = 1  # Immer 1 für Solo-Pool
worker_prefetch_multiplier = 1  # Präfetch Limit - ein Task pro Worker
# worker_max_tasks_per_child = 1  # Neustart nach jedem Task - nicht relevant für solo-Pool

# Verbesserte Stabilität für Worker
worker_send_task_events = False
worker_disable_rate_limits = True
worker_without_heartbeat = True
worker_without_gossip = True
worker_without_mingle = True

# Erlaube Task-Abbruch und Wiederaufnahme
task_acks_late = True
task_reject_on_worker_lost = True

# Erlaube deregistrieren/registrieren von Tasks
worker_enable_remote_control = False

# Task-Tracking und Logging
task_track_started = True
task_send_sent_event = False

# Verbesserte Fehlerbehandlung
task_default_retry_delay = 300  # 5 Minuten Wartezeit vor Retry
task_max_retries = 3

# Verbesserte Verbindungshandhabung
broker_connection_timeout = 30
broker_connection_retry = True
broker_connection_max_retries = 10
broker_pool_limit = None  # Keine Begrenzung für Verbindungen
broker_heartbeat = 0      # Deaktiviere Broker-Heartbeat

# Verbesserte Redis-Backend-Konfiguration
redis_socket_connect_timeout = 30
redis_socket_timeout = 30
result_expires = 86400  # 24 Stunden

# Spezielle Einstellungen für FileDescriptor-Probleme
worker_proc_alive_timeout = 120.0  # Erhöhe Timeout für Worker-Prozesse
worker_pool_restarts = True  # Erlaube Pool-Neustarts bei Fehlern

# Ergebnishandhabung verbessern
result_persistent = False  # Keine dauerhafte Speicherung für Ergebnisse
task_ignore_result = False  # Ergebnisse nicht ignorieren

# Sichere Serialisierung - verhindert einige Fehlerquellen
accept_content = ['json']  # Nur JSON für Serialisierung akzeptieren 