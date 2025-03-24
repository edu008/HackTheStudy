# Verwende offizielles Node.js-Image als Basis
FROM node:18 AS builder

# Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# Abhängigkeiten kopieren und installieren
COPY package*.json ./
RUN npm ci

# Projekt-Dateien kopieren
COPY . .

# Build-Argumente für Umgebungsvariablen
ARG API_URL
ARG NODE_ENV=production

# Setzte Umgebungsvariablen für den Build
ENV API_URL=${API_URL:-https://api.hackthestudy.ch}
ENV NODE_ENV=${NODE_ENV}

# Build erstellen
RUN npm run build

# Prüfe, ob der Build erfolgreich war und Dateien in dist/ sind
RUN ls -la dist/ && echo "Build erfolgreich!"

# Nginx-Stage
FROM nginx:alpine

# Kopiere die gebaute App
COPY --from=builder /app/dist /usr/share/nginx/html
# Prüfe, ob die Dateien korrekt kopiert wurden
RUN ls -la /usr/share/nginx/html && echo "Statische Dateien erfolgreich kopiert!"

# Kopiere die angepasste Nginx-Konfiguration
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Prüfe, ob die Konfiguration korrekt kopiert wurde
RUN cat /etc/nginx/conf.d/default.conf && echo "Nginx-Konfiguration kopiert!"

# Überprüfe die Nginx-Konfiguration
RUN nginx -t

# Healthcheck für Docker
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1

# Ports
EXPOSE 80 8080

# Start Nginx
CMD ["nginx", "-g", "daemon off;"] 