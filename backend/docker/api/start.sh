#!/bin/bash
set -e

# Stelle sicher, dass keine alten Socket-Dateien existieren
rm -f /var/run/supervisor.sock

# Warte kurz, um sicherzustellen, dass Redis Zeit hat, zu starten
sleep 2

# Stelle sicher, dass die Berechtigungen korrekt sind
chmod 700 /etc/supervisor/conf.d/supervisord.conf

# Starte Supervisor mit explizitem Konfigurationspfad
exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf 