# Docker-Konfiguration für HackTheStudy Frontend

Diese Datei enthält Informationen zur Docker-Konfiguration des HackTheStudy Frontend.

## Dateien

- `Dockerfile`: Hauptkonfiguration für das Frontend-Docker-Image
- `nginx.conf`: Nginx-Konfiguration für das SPA-Routing
- `docker-entrypoint.sh`: Script zum Ersetzen von Umgebungsvariablen
- `docker-compose.frontend.yml`: Docker-Compose-Konfiguration für Frontend und Backend

## Verwendung

### Standalone-Frontend-Build

Um nur das Frontend-Image zu bauen und zu starten:

```bash
# Image bauen
docker build -t hackthestudy-frontend .

# Container starten
docker run -p 80:80 -e API_URL=http://deine-backend-url hackthestudy-frontend
```

### Komplette Anwendung mit Docker Compose

Um Frontend und Backend zusammen zu starten:

```bash
# Anwendung starten
docker-compose -f docker-compose.frontend.yml up -d

# Logs anzeigen
docker-compose -f docker-compose.frontend.yml logs -f

# Anwendung stoppen
docker-compose -f docker-compose.frontend.yml down
```

## Umgebungsvariablen

Die folgenden Umgebungsvariablen können gesetzt werden:

| Variable | Beschreibung | Standard |
|----------|--------------|----------|
| `API_URL` | URL des Backend-API (für Nginx Proxy) | `http://backend:5000` |
| `VITE_API_URL` | URL des Backend-API (für Frontend) | `http://localhost:5000` |
| `VITE_APP_NAME` | Name der Anwendung | `HackTheStudy` |
| `VITE_ENV` | Umgebung (`development` oder `production`) | `production` |
| `VITE_ENABLE_MOCK_AUTH` | Mock-Authentifizierung aktivieren | `false` |

## Integration mit bestehendem Backend

Das Frontend ist so konfiguriert, dass es mit dem bestehenden Backend in `/backend/main` kommuniziert. 
Die Docker-Compose-Konfiguration verwendet das Backend-Dockerfile im Backend-Verzeichnis.

## Produktionsdeployment

Für ein Produktionsdeployment:

1. Passe die Umgebungsvariablen für die Produktion an
2. Stelle sicher, dass das Backend korrekt konfiguriert ist
3. Verwende einen Reverse-Proxy wie Nginx oder Traefik für HTTPS

```bash
# Beispiel für Produktionsstart
docker-compose -f docker-compose.frontend.yml -f docker-compose.prod.yml up -d
```

## Fehlerbehebung

### Backend nicht erreichbar

Wenn das Frontend das Backend nicht erreichen kann:

1. Prüfe, ob die `API_URL` korrekt gesetzt ist
2. Stelle sicher, dass das Backend läuft und auf dem richtigen Port hört
3. Prüfe die Netzwerkkonfiguration (insbesondere bei benutzerdefinierten Docker-Netzwerken)

### CORS-Fehler

Bei CORS-Fehlern:

1. Stelle sicher, dass das Backend CORS für den Frontend-Host erlaubt
2. Prüfe die CORS-Header im Backend 