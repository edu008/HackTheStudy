"""
Flask-Extensions und Celery-Konfiguration für den Worker.
"""
import logging
import os

from celery import Celery
from flask_sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)

# Shared SQLAlchemy-Instance
db = SQLAlchemy()


def create_celery_app():
    """
    Erstellt und konfiguriert die Celery-App mit optimierten Einstellungen.
    """
    # Redis-URL aus Umgebungsvariablen oder Standard-Wert
    redis_url = os.environ.get(
        'REDIS_URL',
        os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    )

    # Redis-Passwort für Authentifizierung
    redis_password = os.environ.get('REDIS_PASSWORD', 'hackthestudy_redis_password')

    # Erweiterte Broker-URL mit Passwort
    if 'redis://' in redis_url and '@' not in redis_url and redis_password:
        # Füge Passwort zur URL hinzu, wenn nicht bereits vorhanden
        parts = redis_url.split('://')
        redis_url = f"{parts[0]}://:{redis_password}@{parts[1]}"

    logger.info("Verwende Redis-URL: {redis_url.replace(redis_password, '****")}")

    # Celery-App erstellen
    app = Celery(
        'worker',
        broker=redis_url,
        backend=redis_url,
        include=['tasks']
    )

    # Task-Einstellungen für optimierte Performance
    app.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='Europe/Zurich',
        enable_utc=True,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        worker_max_tasks_per_child=int(os.environ.get('CELERY_MAX_TASKS_PER_CHILD', 10)),
        broker_connection_retry=True,
        broker_connection_max_retries=int(os.environ.get('CELERY_BROKER_CONNECTION_MAX_RETRIES', 10))
    )

    return app


def init_celery(app, celery):
    """
    Initialisiert Celery mit der Flask-App-Konfiguration.
    """
    # TaskBase-Klasse, die Zugriff auf Flask-App-Kontext ermöglicht
    class ContextTask(celery.Task):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    # Task-Klasse mit App-Kontext setzen
    celery.Task = ContextTask

    # Celery-Konfiguration aus Flask-App übernehmen
    celery.conf.update(app.config.get('CELERY', {}))

    return celery
