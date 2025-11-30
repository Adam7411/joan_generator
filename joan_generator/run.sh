#!/bin/bash
echo "--> Startuje Joan Generator..."

# Uruchamiamy pythona i przekierowujemy wszystkie błędy na ekran
# Jeśli python padnie (||), wypisujemy komunikat i czekamy 10 minut
python3 -u /app/run.py || { echo "!!! APLIKACJA PADŁA Z BŁĘDEM !!!"; sleep 600; }
