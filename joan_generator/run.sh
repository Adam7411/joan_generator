#!/bin/bash
# Wersja produkcyjna z Emojis

echo " "
echo "🚀 URUCHAMIANIE GENERATORA JOAN 6..."
echo "---------------------------------------------------"

# Naprawa formatowania (na wypadek edycji w Windows)
echo "🔧 Naprawiam formatowanie plików (dos2unix)..."
dos2unix /app/run.py

# Uruchamiamy aplikację
echo "🐍 Startuje Python..."
echo "---------------------------------------------------"
python3 -u /app/run.py
