"""
Redis-Komponente für Worker-Microservice
"""
from redis.client import get_redis_client, initialize_redis_connection
from redis.utils import (
    safe_redis_get, 
    safe_redis_set, 
    log_debug_info,
    REDIS_TTL_DEFAULT,
    REDIS_TTL_SHORT
)

# Exportiere globale Redis-Client-Instanz
from redis.client import redis_client

__all__ = [
    'get_redis_client', 
    'initialize_redis_connection',
    'safe_redis_get', 
    'safe_redis_set',
    'log_debug_info',
    'REDIS_TTL_DEFAULT',
    'REDIS_TTL_SHORT',
    'redis_client'
] 