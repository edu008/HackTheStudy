#!/usr/bin/env python

import os
import platform
import sys
import time
from datetime import datetime

# ANSI Farbcodes
GREEN = '\033[0;32m'
BLUE = '\033[0;34m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
CYAN = '\033[0;36m'
MAGENTA = '\033[0;35m'
BOLD = '\033[1m'
NC = '\033[0m'  # No Color

LOGO = f"""
{MAGENTA}
    ██╗  ██╗ █████╗  ██████╗██╗  ██╗████████╗██╗  ██╗███████╗███████╗████████╗██╗   ██╗██████╗ ██╗   ██╗
    ██║  ██║██╔══██╗██╔════╝██║ ██╔╝╚══██╔══╝██║  ██║██╔════╝██╔════╝╚══██╔══╝██║   ██║██╔══██╗╚██╗ ██╔╝
    ███████║███████║██║     █████╔╝    ██║   ███████║█████╗  ███████╗   ██║   ██║   ██║██║  ██║ ╚████╔╝ 
    ██╔══██║██╔══██║██║     ██╔═██╗    ██║   ██╔══██║██╔══╝  ╚════██║   ██║   ██║   ██║██║  ██║  ╚██╔╝  
    ██║  ██║██║  ██║╚██████╗██║  ██╗   ██║   ██║  ██║███████╗███████║   ██║   ╚██████╔╝██████╔╝   ██║   
    ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚══════╝   ╚═╝    ╚═════╝ ╚═════╝    ╚═╝   
{NC}"""

def horizontal_line(color=BLUE, char="━", length=80):
    """Erzeugt eine horizontale Linie"""
    return f"{color}{char * length}{NC}"

def centered_text(text, color=CYAN, width=80):
    """Zentriert Text in der gegebenen Breite"""
    return f"{color}{text.center(width)}{NC}"

def two_column(left, right, width=80, left_color=YELLOW, right_color=GREEN):
    """Erstellt eine zweispaltige Zeile"""
    padding = width - len(left) - len(right)
    if padding < 1:
        padding = 1
    return f"{left_color}{left}{' ' * padding}{right_color}{right}{NC}"

def print_banner(container_type="API"):
    """Zeigt den Haupt-Banner an"""
    os.system('cls' if os.name == 'nt' else 'clear')
    print(LOGO)
    print(horizontal_line())
    
    # Containertyp in Grossbuchstaben
    container_type = container_type.upper()
    
    # Zeige Emoji basierend auf Container-Typ
    emoji = "🚀"
    if container_type == "WORKER":
        emoji = "⚙️"
    elif container_type == "API":
        emoji = "🌐"
    elif container_type == "WEB":
        emoji = "🖥️"
    
    print(centered_text(f"{emoji}  {BOLD}HackTheStudy {container_type} Container  {emoji}", MAGENTA))
    print(centered_text(f"Startzeit: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}", BLUE))
    print(horizontal_line())
    
    # System-Info
    print(f"\n{BOLD}{YELLOW}🖥️  System-Informationen:{NC}")
    print(f"{CYAN}  • Python-Version:{NC} {sys.version.split()[0]}")
    print(f"{CYAN}  • Plattform:{NC} {platform.platform()}")
    
    # Umgebungsvariablen (nur ausgewählte anzeigen)
    safe_envs = ["FLASK_ENV", "FLASK_DEBUG", "PYTHONPATH", "FLASK_APP"]
    env_info = {k: v for k, v in os.environ.items() if k in safe_envs}
    
    print(f"\n{BOLD}{YELLOW}🔧  Umgebungskonfiguration:{NC}")
    for k, v in env_info.items():
        print(f"{CYAN}  • {k}:{NC} {v}")
    
    # Netzwerk-Info (vereinfacht)
    print(f"\n{BOLD}{YELLOW}🌐  Netzwerkkonfiguration:{NC}")
    print(f"{CYAN}  • Host:{NC} 0.0.0.0")
    print(f"{CYAN}  • Port:{NC} 5000")
    
    # Datenbank-Info
    db_url = os.environ.get("DATABASE_URL", "Nicht konfiguriert")
    # Für die Sicherheit nur den DB-Typ anzeigen
    if "://" in db_url:
        db_type = db_url.split("://")[0]
        db_info = f"{db_type}://******"
    else:
        db_info = db_url
    
    print(f"\n{BOLD}{YELLOW}📊  Datenbankverbindung:{NC}")
    print(f"{CYAN}  • Typ:{NC} {db_info}")
    
    # Redis-Info
    redis_url = os.environ.get("REDIS_URL", "Nicht konfiguriert")
    if "://" in redis_url:
        redis_type = redis_url.split("://")[0]
        redis_info = f"{redis_type}://******"
    else:
        redis_info = redis_url
    
    print(f"{CYAN}  • Redis:{NC} {redis_info}")
    
    print(horizontal_line())
    print(centered_text("🚀 Container wird gestartet...", GREEN))
    print(horizontal_line())
    print()

def animate_loading(message="Starte Dienste", duration=3):
    """Zeigt eine Ladeanimation für die angegebene Dauer"""
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    end_time = time.time() + duration
    
    i = 0
    while time.time() < end_time:
        frame = frames[i % len(frames)]
        sys.stdout.write(f"\r{BLUE}{frame} {message}...{NC}")
        sys.stdout.flush()
        time.sleep(0.1)
        i += 1
    
    sys.stdout.write(f"\r{GREEN}✓ {message} abgeschlossen!{NC}\n")
    sys.stdout.flush()

def print_service_status(services):
    """Zeigt den Status von verschiedenen Services an"""
    print(f"\n{BOLD}{YELLOW}📊 Service-Status:{NC}")
    
    max_name_len = max(len(name) for name, _ in services)
    
    for name, status in services:
        padded_name = name.ljust(max_name_len)
        if status:
            status_text = f"{GREEN}✓ Aktiv{NC}"
        else:
            status_text = f"{RED}✗ Inaktiv{NC}"
        
        print(f"  • {CYAN}{padded_name}:{NC} {status_text}")

def show_startup_animation(container_type="API", services=None, init_steps=None):
    """
    Zeigt eine komplette Startanimation mit Banner, Ladeanimationen und Service-Status
    
    Args:
        container_type (str): Typ des Containers (API, WORKER, WEB, etc.)
        services (list): Liste von (Name, Status) Tupeln für Services
        init_steps (list): Liste von (Nachricht, Dauer) Tupeln für Initialisierungs-Schritte
    """
    # Standard-Initialisierungsschritte
    if init_steps is None:
        if container_type.upper() == "API":
            init_steps = [
                ("Initialisierung des API-Dienstes", 1.5),
                ("Verbindung zu PostgreSQL herstellen", 1.0),
                ("API-Endpunkte registrieren", 0.8)
            ]
        elif container_type.upper() == "WORKER":
            init_steps = [
                ("Initialisierung der Worker-Dienste", 1.5),
                ("Verbindung zu PostgreSQL herstellen", 1.0),
                ("Aufgabenwarteschlange vorbereiten", 0.8)
            ]
        elif container_type.upper() == "WEB":
            init_steps = [
                ("Initialisierung des Web-Dienstes", 1.5),
                ("Statische Dateien laden", 1.0),
                ("Templates kompilieren", 0.8)
            ]
        else:
            init_steps = [
                (f"Initialisierung des {container_type}-Dienstes", 1.5),
                ("Dienste vorbereiten", 1.0)
            ]
    
    # Standard-Services falls keine angegeben
    if services is None:
        if container_type.upper() == "API":
            services = [
                ("API-Server", True),
                ("PostgreSQL", True),
                ("Redis", True)
            ]
        elif container_type.upper() == "WORKER":
            services = [
                ("Worker-Prozess", True),
                ("PostgreSQL", True),
                ("Redis", True)
            ]
        elif container_type.upper() == "WEB":
            services = [
                ("Web-Server", True),
                ("API-Verbindung", True)
            ]
    
    # Banner anzeigen
    print_banner(container_type)
    
    # Zeige Initialisierungsschritte
    print()
    for message, duration in init_steps:
        animate_loading(message, duration)
    
    # Zeige Service-Status falls vorhanden
    if services:
        print_service_status(services)
    
    print(f"\n{GREEN}✓ {container_type.capitalize()} Container ist bereit!{NC}")
    print()

def demo():
    """Demo-Funktion, um die Banner-Funktionalität zu zeigen"""
    print_banner("API")
    
    time.sleep(1)
    animate_loading("Initialisiere Datenbank", 2)
    animate_loading("Starte API-Server", 1.5)
    
    services = [
        ("PostgreSQL", True),
        ("Redis", True),
        ("Celery Worker", False),
        ("API Server", True)
    ]
    
    print_service_status(services)
    
    print(f"\n{GREEN}✓ System ist bereit!{NC}")

if __name__ == "__main__":
    # Parameter für verschiedene Container-Typen
    if len(sys.argv) > 1:
        container_type = sys.argv[1]
    else:
        container_type = "API"
    
    demo() 