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

# Worker Konfiguration
worker_prefetch_multiplier = 1  # Präfetch Limit - ein Task pro Worker
worker_max_tasks_per_child = 1  # Neustart nach jedem Task, um Speicherlecks zu vermeiden

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

# Verbesserte Redis-Backend-Konfiguration
redis_socket_connect_timeout = 30
redis_socket_timeout = 30
result_expires = 86400  # 24 Stunden

# Spezielle Einstellungen für FileDescriptor-Probleme
worker_proc_alive_timeout = 120.0  # Erhöhe Timeout für Worker-Prozesse
worker_pool_restarts = True  # Erlaube Pool-Neustarts bei Fehlern 