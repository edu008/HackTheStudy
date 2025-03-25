"""
Ressourcenmanagement für den API-Container.
"""

from .fd_monitor import check_and_set_fd_limits, monitor_file_descriptors
from .limits import set_memory_limit, set_cpu_limit

__all__ = [
    'check_and_set_fd_limits', 'monitor_file_descriptors',
    'set_memory_limit', 'set_cpu_limit'
] 