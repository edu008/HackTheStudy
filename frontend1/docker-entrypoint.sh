#!/bin/sh

# Ersetze API_URL in der nginx.conf
sed -i "s|https://api.hackthestudy.ch|$API_URL|g" /etc/nginx/conf.d/default.conf

# Starte Nginx
exec nginx -g "daemon off;" 