"""
Task-Definitionen für den API-Container.
Definiert die Schnittstellen zu den Worker-Tasks.
"""

from .task_dispatcher import dispatch_task, get_task_status

__all__ = ['dispatch_task', 'get_task_status'] 