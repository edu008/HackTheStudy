#!/bin/sh

# Ausgabe von Debug-Informationen
echo "Starting HackTheStudy Frontend..."
echo "API_URL: $API_URL"
echo "FRONTEND_URL: $FRONTEND_URL"
echo "VITE_API_URL: $VITE_API_URL"
echo "VITE_FRONTEND_URL: $VITE_FRONTEND_URL"

# Ersetze Umgebungsvariablen in der nginx-Konfiguration
envsubst '${API_URL}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf

# Ersetze Umgebungsvariablen in der index.html für Frontend-Konfiguration
# Konvertiere Umgebungsvariablen in ein JavaScript-Objekt
echo "window.__env = {" > /usr/share/nginx/html/env-config.js
echo "  API_URL: \"$API_URL\"," >> /usr/share/nginx/html/env-config.js
echo "  FRONTEND_URL: \"$FRONTEND_URL\"," >> /usr/share/nginx/html/env-config.js
echo "  VITE_API_URL: \"$VITE_API_URL\"," >> /usr/share/nginx/html/env-config.js
echo "  VITE_FRONTEND_URL: \"$VITE_FRONTEND_URL\"," >> /usr/share/nginx/html/env-config.js

# Suche alle anderen VITE_ Umgebungsvariablen
env | grep "^VITE_" | grep -v "VITE_API_URL\|VITE_FRONTEND_URL" | while read -r line; do
  key=$(echo "$line" | cut -d '=' -f 1)
  value=$(echo "$line" | cut -d '=' -f 2-)
  echo "  $key: \"$value\"," >> /usr/share/nginx/html/env-config.js
done

# Schließe das JavaScript-Objekt
echo "};" >> /usr/share/nginx/html/env-config.js

# Füge env-config.js in index.html ein
if ! grep -q "env-config.js" /usr/share/nginx/html/index.html; then
  sed -i 's/<head>/<head><script src="\/env-config.js"><\/script>/' /usr/share/nginx/html/index.html
fi

echo "Frontend configuration complete. Starting nginx..."

# Starte nginx
exec "$@" 