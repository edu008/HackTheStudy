"""
Redis-Client für den Worker.
Bietet Verbindung zu Redis mit Fallback-Optionen und Fehlerbehandlung.
"""
import logging
# System-Imports
import os

# Redis-Imports
import redis

# Optional für Dummy-Client
try:
    import fakeredis
    FAKEREDIS_AVAILABLE = True
except ImportError:
    FAKEREDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class RedisClientManager:
    """
    Verwaltet Redis-Client-Verbindungen für den Worker.
    Implementiert als Singleton mit Klassenattribut statt globaler Variable.
    """
    # Klassenattribute
    _redis_instance = None
    _default_redis_url = 'redis://localhost:6379/0'
    _default_redis_host = 'localhost'
    _default_redis_port = 6379
    _default_redis_db = 0
    _default_redis_password = 'hackthestudy_redis_password'
    
    @classmethod
    def initialize_redis_connection(cls):
        """
        Initialisiert die Redis-Verbindung für den Worker.
        Versucht verschiedene Verbindungsoptionen, falls Standardverbindung fehlschlägt.

        Returns:
            redis.Redis: Redis-Client-Instanz oder None bei Fehler.
        """
        # Bereits initialisiert
        if cls._redis_instance is not None:
            return cls._redis_instance

        # Haupt-Redis-URL
        redis_url = os.environ.get('REDIS_URL', cls._default_redis_url)
        redis_host = os.environ.get('REDIS_HOST', cls._default_redis_host)
        redis_port = int(os.environ.get('REDIS_PORT', cls._default_redis_port))
        redis_db = int(os.environ.get('REDIS_DB', cls._default_redis_db))
        redis_password = os.environ.get('REDIS_PASSWORD', cls._default_redis_password)

        # Fallback-URLs
        fallback_urls = os.environ.get('REDIS_FALLBACK_URLS', 'api,redis,localhost')
        fallback_hosts = fallback_urls.split(',')

        # Verbindungsparameter
        connection_params = {
            'decode_responses': True,
            'socket_timeout': 5,
            'socket_connect_timeout': 5,
            'retry_on_timeout': True,
            'health_check_interval': 30
        }

        # Zuerst die Haupt-URL versuchen
        try:
            logger.info("Versuche Redis-Verbindung zu %s", redis_url)
            cls._redis_instance = redis.from_url(
                redis_url,
                password=redis_password,
                **connection_params
            )
            cls._redis_instance.ping()  # Testet die Verbindung
            logger.info("Redis-Verbindung erfolgreich hergestellt zu %s", redis_url)
            return cls._redis_instance
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            logger.warning("Konnte keine Verbindung zu Redis über URL herstellen: %s", e)

        # Fallback: Haupt-Host direkt versuchen
        try:
            logger.info("Versuche Redis-Verbindung zu %s:%s", redis_host, redis_port)
            cls._redis_instance = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                **connection_params
            )
            cls._redis_instance.ping()
            logger.info("Redis-Verbindung erfolgreich hergestellt zu %s:%s", redis_host, redis_port)
            return cls._redis_instance
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            logger.warning("Konnte keine Verbindung zu Redis-Host herstellen: %s", e)

        # Alle Fallback-Hosts durchgehen
        for host in fallback_hosts:
            if not host or host == redis_host:
                continue

            # Host-Port-Trennung, falls angegeben
            if ':' in host:
                host, port = host.split(':')
                port = int(port)
            else:
                port = redis_port

            try:
                logger.info("Versuche Fallback-Redis-Verbindung zu %s:%s", host, port)
                cls._redis_instance = redis.Redis(
                    host=host,
                    port=port,
                    db=redis_db,
                    password=redis_password,
                    **connection_params
                )
                cls._redis_instance.ping()
                logger.info("Redis-Fallback-Verbindung erfolgreich hergestellt zu %s:%s", host, port)
                return cls._redis_instance
            except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
                logger.warning("Konnte keine Verbindung zu Redis-Fallback-Host %s herstellen: %s", host, e)

        # Dummy-Redis-Client erstellen, wenn keine Verbindung möglich
        if FAKEREDIS_AVAILABLE:
            logger.warning("Erstelle Dummy-Redis-Client mit fakeredis")
            cls._redis_instance = fakeredis.FakeStrictRedis(decode_responses=True)
            return cls._redis_instance
            
        logger.error("Fakeredis nicht verfügbar, kann keinen Dummy-Client erstellen")
        return None

    @classmethod
    def get_redis_client(cls):
        """
        Gibt den inititalisierten Redis-Client zurück oder initialisiert ihn bei Bedarf.

        Returns:
            redis.Redis: Redis-Client-Instanz oder None bei Fehler.
        """
        if cls._redis_instance is None:
            cls._redis_instance = cls.initialize_redis_connection()

        return cls._redis_instance

    @classmethod
    def clear_keys(cls, pattern):
        """
        Löscht alle Redis-Schlüssel, die dem angegebenen Muster entsprechen.

        Args:
            pattern (str): Glob-Muster für zu löschende Schlüssel.

        Returns:
            int: Anzahl der gelöschten Schlüssel.
        """
        client = cls.get_redis_client()
        if not client:
            logger.warning("Redis-Client nicht verfügbar, Schlüssel können nicht gelöscht werden")
            return 0

        try:
            keys = client.keys(pattern)
            if not keys:
                return 0

            deleted = client.delete(*keys)
            logger.info("%s Redis-Schlüssel mit Muster '%s' gelöscht", deleted, pattern)
            return deleted
        except Exception as e:
            logger.error("Fehler beim Löschen von Redis-Schlüsseln: %s", e)
            return 0


# Singleton-Instanz für einfachen Zugriff
redis_client_manager = RedisClientManager()

# Funktionen für Abwärtskompatibilität
def initialize_redis_connection():
    """Leitet an die Klassenmethode weiter."""
    return RedisClientManager.initialize_redis_connection()

def get_redis_client():
    """Leitet an die Klassenmethode weiter."""
    return RedisClientManager.get_redis_client()

def clear_keys(pattern):
    """Leitet an die Klassenmethode weiter."""
    return RedisClientManager.clear_keys(pattern)

# Export für Import aus anderen Modulen
__all__ = [
    'redis_client_manager', 'RedisClientManager',
    'initialize_redis_connection', 'get_redis_client', 'clear_keys'
]
