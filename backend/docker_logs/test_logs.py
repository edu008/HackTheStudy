#!/usr/bin/env python
"""
Docker-Logs Test-Script
----------------------
Demonstriert die Funktionen des Docker-Logging-Systems.
"""

import os
import sys
import time
from datetime import datetime

# Importiere das docker_logs-Paket
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import docker_logs

def test_banner():
    """Testet die Banner-Funktionen"""
    print("\n🚀 Banner-Test:")
    docker_logs.print_banner("TEST")
    
    services = [
        ("API-Server", True),
        ("PostgreSQL", True),
        ("Redis", True),
        ("Celery Worker", False)
    ]
    docker_logs.print_service_status(services)

def test_progress():
    """Testet Fortschrittsbalken und Animationen"""
    print("\n⏱️ Fortschrittsbalken-Test:")
    for i in range(11):
        docker_logs.print_progress("Verarbeite Datei", i/10, "📄")
        time.sleep(0.1)
    
    print("\n🔄 Lade-Animation-Test:")
    docker_logs.print_loading_spinner("Lade Daten", 2)

def test_data_formatting():
    """Testet die Datenformatierung"""
    print("\n📊 Datenformatierung-Test:")
    
    # Beispiel-Daten
    user_data = {
        "id": 12345,
        "name": "Max Mustermann",
        "email": "max@example.com",
        "roles": ["admin", "user"],
        "preferences": {"theme": "dark", "language": "de"},
        "last_login": "2023-08-15T14:30:00Z"
    }
    
    tasks = [
        {"id": 1, "title": "Aufgabe 1", "status": "completed"},
        {"id": 2, "title": "Aufgabe 2", "status": "pending"},
        {"id": 3, "title": "Aufgabe 3", "status": "in_progress"}
    ]
    
    print("\nWörterbuch-Formatierung:")
    print(docker_logs.format_dict_summary(user_data))
    
    print("\nListen-Formatierung:")
    print(docker_logs.format_list_summary(tasks))
    
    print("\nLog-Nachricht mit Daten:")
    print(docker_logs.format_log_message(
        "Benutzer angemeldet", 
        user_data, 
        "INFO"
    ))

def test_loggers():
    """Testet die verschiedenen Logger"""
    print("\n📝 Logger-Test:")
    
    # App-Logger
    docker_logs.app_logger.info("Anwendung gestartet", extra={'emoji': '🚀'})
    
    # API-Logger
    docker_logs.api_logger.info("GET /api/v1/users/123", extra={
        'data': {'params': {'id': 123}},
        'emoji': '🔍'
    })
    
    # DB-Logger
    docker_logs.db_logger.info("SELECT * FROM users WHERE id = ?", extra={
        'data': {'params': [123], 'rows_affected': 1},
        'emoji': '🗃️'
    })
    
    # Worker-Logger
    docker_logs.worker_logger.info("PDF-Verarbeitung gestartet", extra={
        'data': {'job_id': 'abc123', 'file': 'dokument.pdf'},
        'emoji': '📝'
    })
    
    # Auth-Logger
    docker_logs.auth_logger.info("Benutzer eingeloggt", extra={
        'data': {'user_id': 123, 'method': 'password'},
        'emoji': '🔐'
    })
    
    # Fehler-Logger
    docker_logs.api_logger.error("Fehler beim Verarbeiten der Anfrage", extra={
        'data': {'error_code': 500, 'path': '/api/v1/users'},
        'emoji': '❌'
    })

def main():
    """Hauptfunktion zum Testen des Docker-Logging-Systems"""
    print("\n" + "="*50)
    print("🐳 Docker-Logging-System Test")
    print("="*50 + "\n")
    
    test_banner()
    test_progress()
    test_data_formatting()
    test_loggers()
    
    print("\n" + "="*50)
    print("✅ Test abgeschlossen")
    print("="*50 + "\n")

if __name__ == "__main__":
    main() 