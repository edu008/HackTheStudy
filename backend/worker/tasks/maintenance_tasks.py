"""
Wartungs-Tasks für den Worker.
"""
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def register_tasks(celery_app):
    """
    Registriert alle Wartungs-Tasks mit der Celery-App.

    Args:
        celery_app: Die Celery-App-Instanz.

    Returns:
        dict: Dictionary mit den registrierten Tasks.
    """
    tasks = {}

    @celery_app.task(name='maintenance.clean_temp_files')
    def clean_temp_files(older_than_days=1, directory=None):
        """
        Bereinigt temporäre Dateien, die älter als die angegebene Zeit sind.

        Args:
            older_than_days (int): Dateien älter als diese Anzahl von Tagen werden gelöscht.
            directory (str, optional): Zu bereinigendes Verzeichnis. Standardmäßig wird
                                       das temporäre Upload-Verzeichnis verwendet.

        Returns:
            dict: Ergebnis der Bereinigung.
        """
        import glob
        import os
        import tempfile
        import time

        # Standardverzeichnis festlegen, falls nicht angegeben
        if not directory:
            directory = os.environ.get('UPLOAD_TEMP_DIR', os.path.join(tempfile.gettempdir(), 'hackthestudy_uploads'))

        if not os.path.exists(directory):
            return {'status': 'skipped', 'reason': f'Verzeichnis existiert nicht: {directory}'}

        logger.info("Bereinige temporäre Dateien in %s (älter als %s Tage)", directory, older_than_days)

        # Zeitpunkt berechnen, vor dem Dateien gelöscht werden sollen
        cutoff = time.time() - (older_than_days * 86400)

        deleted_files = []
        errors = []

        # Alle Dateien im Verzeichnis durchgehen
        for root, dirs, files in os.walk(directory, topdown=False):
            for file in files:
                file_path = os.path.join(root, file)

                try:
                    # Dateiattribute abrufen
                    file_stats = os.stat(file_path)

                    # Prüfen, ob die Datei älter als der Cutoff ist
                    if file_stats.st_mtime < cutoff:
                        os.remove(file_path)
                        deleted_files.append(file_path)
                except Exception as e:
                    errors.append(f"{file_path}: {str(e)}")

            # Leere Verzeichnisse löschen
            for dir in dirs:
                dir_path = os.path.join(root, dir)
                try:
                    if not os.listdir(dir_path):
                        os.rmdir(dir_path)
                        logger.info("Leeres Verzeichnis gelöscht: %s", dir_path)
                except Exception as e:
                    errors.append(f"{dir_path}: {str(e)}")

        result = {
            'status': 'completed',
            'deleted_count': len(deleted_files),
            'deleted_files': deleted_files[:50],  # Begrenzen, um die Antwortgröße zu reduzieren
            'errors_count': len(errors),
            'errors': errors[:10]
        }

        logger.info("Temporäre Dateien bereinigt: %s gelöscht, %s Fehler", result['deleted_count'], result['errors_count'])

        return result

    tasks['maintenance.clean_temp_files'] = clean_temp_files

    @celery_app.task(name='maintenance.clean_cache')
    def clean_cache(pattern=None, older_than_days=7):
        """
        Bereinigt Redis-Cache-Einträge.

        Args:
            pattern (str, optional): Muster für zu löschende Schlüssel.
                                      Standardmäßig werden alle Cache-Einträge gelöscht.
            older_than_days (int): Cache-Einträge älter als diese Anzahl von Tagen werden gelöscht.

        Returns:
            dict: Ergebnis der Cache-Bereinigung.
        """
        from redis_utils.client import get_redis_client

        # Muster für zu löschende Schlüssel
        if not pattern:
            pattern = "*"

        logger.info("Bereinige Cache-Einträge: %s (älter als %s Tage)", pattern, older_than_days)

        # Redis-Client verwenden
        redis_client = get_redis_client()
        if not redis_client:
            return {'status': 'error', 'error': 'Redis-Client nicht verfügbar'}

        try:
            # Aktuelle Zeit minus die Anzahl der Tage in Sekunden
            cutoff_time = datetime.now() - timedelta(days=older_than_days)
            cutoff_timestamp = cutoff_time.timestamp()

            keys = redis_client.keys(pattern)
            deleted_count = 0

            for key in keys:
                # Erstellungszeitpunkt des Schlüssels prüfen
                ttl = redis_client.ttl(key)
                if ttl == -1:  # Kein TTL gesetzt
                    # Prüfe zusätzliche Metadaten, falls vorhanden
                    try:
                        # Versuche 'created_at' oder 'timestamp' zu finden
                        if redis_client.type(key) == 'hash':
                            created_at = redis_client.hget(key, 'created_at') or redis_client.hget(key, 'timestamp')
                            if created_at and float(created_at) < cutoff_timestamp:
                                redis_client.delete(key)
                                deleted_count += 1
                    except Exception as e:
                        logger.error(f"Fehler beim Prüfen des Schlüssels {key}: {e}")
                else:
                    # Wenn TTL gesetzt ist und abgelaufen, löschen
                    if ttl <= 0:
                        redis_client.delete(key)
                        deleted_count += 1

            return {
                'status': 'completed',
                'pattern': pattern,
                'deleted_count': deleted_count
            }

        except Exception as e:
            logger.error(f"Fehler beim Bereinigen des Caches: {e}")
            return {'status': 'error', 'error': str(e)}

    tasks['maintenance.clean_cache'] = clean_cache

    @celery_app.task(name='maintenance.health_check')
    def health_check():
        """
        Führt einen Health-Check des Systems durch.

        Returns:
            dict: Ergebnis des Health-Checks.
        """
        import psutil
        from redis_utils.client import get_redis_client

        logger.info("Führe System-Health-Check durch")

        result = {
            'status': 'ok',
            'timestamp': datetime.now().isoformat(),
            'system': {},
            'redis': {},
            'errors': []
        }

        # System-Informationen sammeln
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            result['system'] = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_mb': memory.available / (1024 * 1024),
                'disk_percent': disk.percent,
                'disk_free_gb': disk.free / (1024 * 1024 * 1024)
            }
        except Exception as e:
            result['errors'].append(f"Fehler beim Sammeln von Systeminformationen: {e}")

        # Redis-Status prüfen
        try:
            redis_client = get_redis_client()
            if redis_client:
                # Ping-Test
                redis_response = redis_client.ping()
                result['redis']['ping'] = redis_response

                # Info abrufen
                info = redis_client.info()
                result['redis']['used_memory_mb'] = info.get('used_memory', 0) / (1024 * 1024)
                result['redis']['connected_clients'] = info.get('connected_clients', 0)
                result['redis']['uptime_days'] = info.get('uptime_in_days', 0)
            else:
                result['redis']['status'] = 'unavailable'
                result['errors'].append("Redis-Client nicht verfügbar")
        except Exception as e:
            result['redis']['status'] = 'error'
            result['errors'].append(f"Fehler bei der Redis-Verbindung: {e}")

        # Gesamtstatus basierend auf Fehlern
        if result['errors']:
            result['status'] = 'warning' if len(result['errors']) < 2 else 'error'

        return result

    tasks['maintenance.health_check'] = health_check

    return tasks
