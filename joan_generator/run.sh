#!/bin/bash
# Wersja produkcyjna

# Dla pewności naprawiamy formatowanie przy każdym starcie
dos2unix /app/run.py

# Uruchamiamy aplikację
echo "Startuje Joan Generator..."
python3 -u /app/run.py
