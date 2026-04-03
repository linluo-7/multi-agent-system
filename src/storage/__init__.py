"""
Storage Layer
存储层 - PostgreSQL和Redis的统一接口
"""

from .postgres import PostgresStorage, get_storage
from .redis_manager import RedisManager, get_redis

__all__ = ['PostgresStorage', 'RedisManager', 'get_storage', 'get_redis']
