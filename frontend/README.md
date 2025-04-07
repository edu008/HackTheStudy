# Welcome to your Lovable project

## Project info

**URL**: https://lovable.dev/projects/e68c133a-44af-433b-ac82-8c928f5aee27

## How can I edit this code?

There are several ways of editing your application.

**Use Lovable**

Simply visit the [Lovable Project](https://lovable.dev/projects/e68c133a-44af-433b-ac82-8c928f5aee27) and start prompting.

Changes made via Lovable will be committed automatically to this repo.

**Use your preferred IDE**

If you want to work locally using your own IDE, you can clone this repo and push changes. Pushed changes will also be reflected in Lovable.

The only requirement is having Node.js & npm installed - [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating)

Follow these steps:

```sh
# Step 1: Clone the repository using the project's Git URL.
git clone <YOUR_GIT_URL>

# Step 2: Navigate to the project directory.
cd <YOUR_PROJECT_NAME>

# Step 3: Install the necessary dependencies.
npm i

# Step 4: Start the development server with auto-reloading and an instant preview.
npm run dev
```

**Edit a file directly in GitHub**

- Navigate to the desired file(s).
- Click the "Edit" button (pencil icon) at the top right of the file view.
- Make your changes and commit the changes.

**Use GitHub Codespaces**

- Navigate to the main page of your repository.
- Click on the "Code" button (green button) near the top right.
- Select the "Codespaces" tab.
- Click on "New codespace" to launch a new Codespace environment.
- Edit files directly within the Codespace and commit and push your changes once you're done.

## What technologies are used for this project?

This project is built with .

- Vite
- TypeScript
- React
- shadcn-ui
- Tailwind CSS

## How can I deploy this project?

Simply open [Lovable](https://lovable.dev/projects/e68c133a-44af-433b-ac82-8c928f5aee27) and click on Share -> Publish.

## I want to use a custom domain - is that possible?

We don't support custom domains (yet). If you want to deploy your project under your own domain then we recommend using Netlify. Visit our docs for more details: [Custom domains](https://docs.lovable.dev/tips-tricks/custom-domain/)

# HackTheStudy Frontend Docker-Konfiguration

Diese README-Datei beschreibt die Docker-Konfiguration für das HackTheStudy Frontend.

## Integration mit der bestehenden docker-compose.yml

Die folgenden Dateien wurden erstellt/angepasst, um mit der bestehenden docker-compose.yml zu funktionieren:

1. `Dockerfile` - Build-Anweisungen für das Frontend
2. `nginx.conf` - Nginx-Konfiguration für SPA-Routing und API-Proxy
3. `docker-entrypoint.sh` - Script zum Ersetzen von Umgebungsvariablen

## Verwendung

Platziere die drei Dateien im `frontend/`-Verzeichnis und führe dann den folgenden Befehl aus, um die gesamte Anwendung zu starten:

```bash
docker-compose up -d
```

## Umgebungsvariablen

Die folgenden Umgebungsvariablen werden in der docker-compose.yml für das Frontend verwendet:

| Variable | Beschreibung | Verwendet in |
|----------|--------------|--------------|
| `API_URL` | URL des Backend-API für Server-seitige Anfragen | nginx, env-config.js |
| `FRONTEND_URL` | URL des Frontends | env-config.js |
| `VITE_API_URL` | URL des Backend-API für Client-seitige Anfragen | env-config.js |
| `VITE_FRONTEND_URL` | URL des Frontends für Client-seitige Anfragen | env-config.js |
| `NODE_ENV` | Node.js-Umgebung (`development` oder `production`) | Build-Prozess |

## Wie es funktioniert

1. **Build-Prozess**:
   - Build-Stage kompiliert das Frontend mit Node.js
   - Production-Stage richtet Nginx ein, um die kompilierten Dateien zu servieren

2. **Runtime-Konfiguration**:
   - `docker-entrypoint.sh` ersetzt Umgebungsvariablen in der Nginx-Konfiguration
   - Erstellt eine `env-config.js`-Datei mit allen Umgebungsvariablen für das Frontend
   - Fügt diese Datei in die index.html ein

3. **API-Proxy**:
   - Nginx leitet alle Anfragen an `/api/` an das Backend weiter
   - Verwendet die `API_URL` aus der docker-compose.yml

## Fehlersuche

### Frontend kann das Backend nicht erreichen

Wenn das Frontend keine Verbindung zum Backend herstellen kann:

1. Prüfe die Docker-Netzwerkverbindung:
   ```bash
   docker network inspect hackthestudy-network
   ```

2. Stelle sicher, dass die richtigen Umgebungsvariablen gesetzt sind:
   ```bash
   docker-compose exec frontend env | grep API_URL
   ```

3. Prüfe die Nginx-Konfiguration im Container:
   ```bash
   docker-compose exec frontend cat /etc/nginx/conf.d/default.conf
   ```

4. Prüfe die Logs des Frontend-Containers:
   ```bash
   docker-compose logs frontend
   ```

### CORS-Fehler

Wenn CORS-Fehler auftreten:

1. Stelle sicher, dass das Backend die richtigen CORS-Header sendet:
   ```bash
   docker-compose exec main grep -r "CORS" /app
   ```

2. Überprüfe die `CORS_ORIGINS`-Umgebungsvariable im Backend:
   ```bash
   docker-compose exec main env | grep CORS_ORIGINS
   ```
