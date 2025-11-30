#!/bin/bash
echo "Startuje Joan Generator (Production Mode)..."

# Naprawa formatowania
dos2unix /app/run.py

# Uruchomienie przez GUNICORN (Serwer produkcyjny)
# -w 2: Dwa procesy (szybciej)
# -b: Port 5000
# --chdir /app: Katalog pracy
# run:app : Plik run.py, aplikacja o nazwie 'app'
gunicorn -w 2 -b 0.0.0.0:5000 --chdir /app run:app
