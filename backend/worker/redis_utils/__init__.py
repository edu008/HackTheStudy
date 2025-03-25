"""
Redis-Komponente für Worker-Microservice
"""
from redis_utils.client import get_redis_client, initialize_redis_connection
from redis_utils.utils import (
    safe_redis_get, 
    safe_redis_set, 
    log_debug_info,
    REDIS_TTL_DEFAULT,
    REDIS_TTL_SHORT
)

# Exportiere globale Redis-Client-Instanz
from redis_utils.client import redis_client

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