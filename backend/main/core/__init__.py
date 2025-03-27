"""
Kernkomponenten des API-Containers.
Enthält die Basismodelle und Datenbankoperationen.
"""

# Version der Kern-Komponenten
__version__ = '1.0.0'

# Exportiere wichtige Komponenten für einfachen Import
from .redis_client import (
    redis_client, RedisClient, 
    get_redis_client, get_from_redis, set_in_redis
)

__all__ = [
    'redis_client', 'RedisClient',
    'get_redis_client', 'get_from_redis', 'set_in_redis'
] 