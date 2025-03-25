"""
Ressourcen-Management-Funktionen für den Worker-Microservice
"""
from resource_manager.fd_monitor import (
    check_and_set_fd_limits,
    monitor_file_descriptors
)

from resource_manager.signals import (
    register_signal_handlers,
    handle_worker_timeout
)

__all__ = [
    'check_and_set_fd_limits',
    'monitor_file_descriptors',
    'register_signal_handlers',
    'handle_worker_timeout'
] 