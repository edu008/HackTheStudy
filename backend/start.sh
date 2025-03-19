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

# Spinner-Funktion für Ladeanimationen
spinner() {
  local pid=$1
  local delay=0.1
  local spinstr='⣾⣽⣻⢿⡿⣟⣯⣷'
  while [ "$(ps a | awk '{print $1}' | grep $pid)" ]; do
    local temp=${spinstr#?}
    printf " [%c]  " "$spinstr"
    local spinstr=$temp${spinstr%"$temp"}
    sleep $delay
    printf "\b\b\b\b\b\b"
  done
  printf "    \b\b\b\b"
}

# Funktion für horizontale Trennlinien
divider() {
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Zeige den Banner
python -c "from docker_logs.docker_banner import print_banner; print_banner('API')"

echo -e "\n${BOLD}${YELLOW}🔄 Initialisierung der Dienste...${NC}\n"

# Warten auf PostgreSQL
echo -e "${MAGENTA}📊 Warte auf PostgreSQL...${NC}"
while ! nc -z db 5432; do
  echo -ne "${YELLOW}⏳ Verbindung zu PostgreSQL wird hergestellt...\r${NC}"
  sleep 0.5
  echo -ne "${YELLOW}⌛ Verbindung zu PostgreSQL wird hergestellt...\r${NC}"
  sleep 0.5
done
echo -e "${GREEN}✅ PostgreSQL ist bereit!${NC}"

# Datenbank-Tabellen löschen
echo -e "\n${YELLOW}🗑️  Entferne alte Datenbank-Tabellen...${NC}"
python -c "from app import create_app; app = create_app(); from models import db; app.app_context().push(); db.drop_all()" > /dev/null 2>&1 &
PID=$!
spinner $PID
wait $PID
if [ $? -eq 0 ]; then
  echo -e "${GREEN}✅ Alte Tabellen erfolgreich entfernt${NC}"
else
  echo -e "${RED}❌ Fehler beim Entfernen alter Tabellen${NC}"
fi

# Neue Datenbank-Tabellen erstellen
echo -e "\n${YELLOW}📝 Erstelle neue Datenbank-Struktur...${NC}"
python -c "from app import create_app; app = create_app(); from models import db; app.app_context().push(); db.create_all()" > /dev/null 2>&1 &
PID=$!
spinner $PID
wait $PID
if [ $? -eq 0 ]; then
  echo -e "${GREEN}✅ Datenbank-Struktur erfolgreich erstellt${NC}"
  # Zählen der Tabellen ohne sie aufzulisten
  TABLE_COUNT=$(python -c "from app import create_app; app = create_app(); from models import db; app.app_context().push(); import inspect; print(len([t for t in db.metadata.tables.keys()]))")
  echo -e "${CYAN}   ℹ️ ${TABLE_COUNT} Tabellen wurden initialisiert${NC}"
else
  echo -e "${RED}❌ Fehler beim Erstellen der Datenbank-Struktur${NC}"
fi

# Setze Umgebungsvariablen für verbessertes Logging
export PYTHONPATH=$PYTHONPATH:/app
export USE_COLORED_LOGS=true
export LOG_LEVEL=INFO
export PYTHONUNBUFFERED=1

# Flask-Anwendung starten mit unserem verbesserten Log-Wrapper
divider
echo -e "\n${BOLD}${GREEN}🌟 Starte Flask-Anwendung mit verbesserten Logs...${NC}\n"
divider
echo -e "\n${CYAN}🔗 API-Endpunkte werden unter http://localhost:5000 verfügbar sein${NC}\n"

# Starte die App mit dem Wrapper statt direkt mit Flask
exec python app_wrapper.py