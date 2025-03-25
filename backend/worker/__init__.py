"""
HackTheStudy Worker Microservice
"""
from app import celery_app, initialize_worker

__version__ = '1.0.0'

__all__ = ['celery_app', 'initialize_worker'] 