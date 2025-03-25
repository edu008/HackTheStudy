"""
Gunicorn-Konfiguration für den API-Container
"""

import os
import multiprocessing

# Umgebungsvariablen lesen oder Standardwerte verwenden
workers_per_core_str = os.getenv("WORKERS_PER_CORE", "2")
max_workers_str = os.getenv("MAX_WORKERS", "4")
use_max_workers = os.getenv("USE_MAX_WORKERS", "false").lower() == "true"
web_concurrency_str = os.getenv("WEB_CONCURRENCY", None)
host = os.getenv("HOST", "0.0.0.0")
port = os.getenv("PORT", "8000")
bind_env = os.getenv("BIND", None)
log_level = os.getenv("LOG_LEVEL", "info")
worker_class = os.getenv("WORKER_CLASS", "gevent")
timeout = int(os.getenv("TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GRACEFUL_TIMEOUT", "120"))
keep_alive = int(os.getenv("KEEP_ALIVE", "5"))
threads = int(os.getenv("THREADS", "1"))

# Anzahl der Kerne bestimmen
cores = multiprocessing.cpu_count()

# Workers pro Kern berechnen
workers_per_core = float(workers_per_core_str)
max_workers = int(max_workers_str)

# Wenn WEB_CONCURRENCY gesetzt ist, verwende diesen Wert
if web_concurrency_str:
    web_concurrency = int(web_concurrency_str)
    assert web_concurrency > 0
else:
    # Sonst berechne basierend auf Kernen und Settings
    web_concurrency = int(cores * workers_per_core)
    if use_max_workers:
        web_concurrency = min(web_concurrency, max_workers)

# Bind definieren
if bind_env:
    bind = bind_env
else:
    bind = f"{host}:{port}"

# Gunicorn-Konfiguration
# https://docs.gunicorn.org/en/stable/settings.html
workers = max(int(multiprocessing.cpu_count() * 0.75), 2)
worker_class = worker_class
threads = threads
bind = bind
keepalive = keep_alive
timeout = timeout
graceful_timeout = graceful_timeout

# Logging
loglevel = log_level
accesslog = "-"  # stdout
errorlog = "-"   # stderr
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s'
capture_output = True
enable_stdio_inheritance = True

# Worker-Optionen
worker_tmp_dir = "/dev/shm"
worker_connections = 1000
preload_app = True
reuse_port = True

# Maximale Anzahl gleichzeitiger Requests pro Worker
max_requests = 2000
max_requests_jitter = 400

# Performance-Einstellungen
backlog = 2048

# Debug-Modus (nur für Entwicklung)
reload = os.environ.get("GUNICORN_RELOAD", "false").lower() == "true"
reload_extra_files = []

# Sicherheitseinstellungen
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Header-Verarbeitung
forwarded_allow_ips = '*'

# Process Naming
proc_name = "hackthestudy-api"
default_proc_name = "hackthestudy-api"

# Server Mechanics
daemon = False
raw_env = []
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Aktiviere Statsd-Metriken, falls konfiguriert
if os.getenv("ENABLE_METRICS", "").lower() in ("1", "true", "yes"):
    # Optional: StatD-Metriken aktivieren, wenn STATSD_HOST gesetzt ist
    statsd_host = os.getenv("STATSD_HOST", None)
    if statsd_host:
        statsd_port = int(os.getenv("STATSD_PORT", "8125"))
        statsd_prefix = os.getenv("STATSD_PREFIX", "gunicorn")
        
        # Aktiviere StatD
        statsd_host = f"{statsd_host}:{statsd_port}"

# Server Hooks
def on_starting(server):
    pass

def on_reload(server):
    pass

def when_ready(server):
    pass

def post_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def pre_fork(server, worker):
    pass

def pre_exec(server):
    server.log.info("Forked child, re-executing.")

def pre_request(worker, req):
    worker.log.debug("%s %s", req.method, req.path)

def post_request(worker, req, environ, resp):
    pass

def child_exit(server, worker):
    pass

def worker_exit(server, worker):
    pass

def worker_abort(worker):
    pass

def on_exit(server):
    server.log.info("Shutting down") 