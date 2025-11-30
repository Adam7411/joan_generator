#!/bin/bash
# Production Version (Gunicorn)

echo " "
echo "🚀 STARTING JOAN 6 DASHBOARD GENERATOR (PRODUCTION)..."
echo "---------------------------------------------------"

# Naprawa formatowania
echo "🔧 Fixing file formatting..."
dos2unix /app/run.py

# Uruchomienie serwera produkcyjnego Gunicorn
# -w 2: Dwa procesy robocze (szybsze działanie)
# -b: Port 5000
# --chdir /app: Katalog aplikacji
# --access-logfile -: Logi dostępu na ekran
# --error-logfile -: Logi błędów na ekran
# run:app: Plik 'run.py' i obiekt 'app' wewnątrz niego

echo "🦄 Starting Gunicorn WSGI Server..."
echo "---------------------------------------------------"
gunicorn -w 2 -b 0.0.0.0:5000 --chdir /app --access-logfile - --error-logfile - run:app
