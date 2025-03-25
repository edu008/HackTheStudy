import os
import multiprocessing

# Server Socket
bind = "0.0.0.0:" + os.getenv("PORT", "8080")
backlog = 2048

# Worker Processes
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "gevent"
threads = int(os.getenv("GUNICORN_THREADS", "4"))
worker_connections = 1000
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
keepalive = 2
max_requests = 1000
max_requests_jitter = 100

# Process Naming
proc_name = "hackthestudy-api"
default_proc_name = "hackthestudy-api"

# Logging
errorlog = "-"
accesslog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s'
loglevel = os.getenv("LOG_LEVEL", "info").lower()

# Server Mechanics
preload_app = True
daemon = False
raw_env = []
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL
keyfile = None
certfile = None

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