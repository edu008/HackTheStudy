#!/bin/bash

# Farbdefinitionen
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Funktion für Ladeanimationen
loading_animation() {
  local message=$1
  local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
  local delay=0.1
  local i=0
  
  while [ "$2" = "true" ]; do
    i=$(( (i+1) % ${#frames[@]} ))
    printf "\r${YELLOW}${frames[$i]} %s${NC}" "$message"
    sleep $delay
  done
}

# Funktion für horizontale Trennlinien
divider() {
  echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Zeige den Banner mit Worker-Typspecifikation
python -c "from docker_logs.docker_banner import print_banner; print_banner('WORKER')"

echo -e "\n${BOLD}${YELLOW}🔄 Initialisierung der Worker-Dienste...${NC}\n"

# Warten auf PostgreSQL mit Animation
echo -e "${CYAN}📊 Verbindung zu PostgreSQL herstellen...${NC}"
connection_status=true
loading_animation "Verbinde mit PostgreSQL..." "$connection_status" &
LOADING_PID=$!

while ! nc -z db 5432; do
  sleep 0.5
done

connection_status=false
wait $LOADING_PID 2>/dev/null
echo -e "\r${GREEN}✅ PostgreSQL ist verbunden!     ${NC}"

# Warten auf Redis mit Animation
echo -e "\n${CYAN}🔄 Verbindung zu Redis herstellen...${NC}"
connection_status=true
loading_animation "Verbinde mit Redis..." "$connection_status" &
LOADING_PID=$!

while ! nc -z redis 6379; do
  sleep 0.5
done

connection_status=false
wait $LOADING_PID 2>/dev/null
echo -e "\r${GREEN}✅ Redis ist verbunden!     ${NC}"

# Setze Umgebungsvariablen für verbessertes Logging
export PYTHONPATH=$PYTHONPATH:/app
export USE_COLORED_LOGS=true
export LOG_LEVEL=INFO
export PYTHONUNBUFFERED=1

# Starten des Celery Workers
divider
echo -e "\n${BOLD}${GREEN}🚀 Starte Celery Worker mit verbessertem Logging...${NC}\n"

# Informationen über Worker
echo -e "${CYAN}ℹ️  Worker-Informationen:${NC}"
echo -e "${YELLOW}  • Aufgaben werden in der Redis-Warteschlange verwaltet${NC}"
echo -e "${YELLOW}  • Verarbeitet Hintergrund-Jobs (PDF-Analyse, KI-Generierung, etc.)${NC}"
echo -e "${YELLOW}  • Log-Level: INFO${NC}"
divider

echo -e "\n${MAGENTA}🔍 Worker-Logs:${NC}\n"

# Initialisiere das verbesserte Logging vor dem Start des Workers
python -c "
import sys
sys.path.append('/app')
try:
    from docker_logs import worker_logger
    worker_logger.info('Celery Worker wird initialisiert', extra={'emoji': 'STARTUP'})
except ImportError:
    print('Warnung: Verbessertes Logging konnte nicht initialisiert werden')
"

# Starten des Celery Workers mit angepasstem Log-Format
# Anstatt alle Task-Details auszugeben, zeigen wir nur die Anzahl der Tasks
PYTHONUNBUFFERED=1 exec celery -A tasks.celery worker --loglevel=info | sed \
  -e "s/\[.*\]/${BLUE}[WORKER]${NC}/" \
  -e "s/Task .* received/🔔 Task erhalten/" \
  -e "s/Task .* succeeded/✅ Task erfolgreich abgeschlossen/" \
  -e "s/Task .* failed/❌ Task fehlgeschlagen/" \
  -e "s/^Received task:.*/📥 Neue Aufgabe erhalten.../" \
  -e "s/^Task .* raised .*/⚠️ Fehler in Aufgabe aufgetreten.../" \
  -e "s/\(.*\) tasks of \(.*\) tasks.*/🔢 \1 Aufgaben von \2 Tasks in der Warteschlange/" \
  -e "s/Started.*/🚀 Worker gestartet und bereit für Aufgaben/" \
  -e "s/Ready for.*/✅ Worker ist bereit und wartet auf Aufgaben/" \
  -e "s/Connected.*/🔗 Verbindung hergestellt/" \
  -e "s/Detailed results for.*/{Detaillierte Ergebnisse werden nicht angezeigt}/" \
  -e "/arguments/d" \
  -e "/result=/d" \
  -e "/run time:/d"
