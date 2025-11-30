#!/bin/bash
echo "----------------------------------------"
echo "STARTUJE JOAN GENERATOR (TRYB DEBUGOWANIA)"
echo "----------------------------------------"

# 1. Naprawiamy formatowanie pliku Python (częsty problem przy kopiowaniu z Windows)
echo "Naprawiam formatowanie plików..."
dos2unix /app/run.py

# 2. Uruchamiamy Pythona z flagą -u (unbuffered) i łapiemy błąd
echo "Uruchamiam aplikację Python..."
python3 -u /app/run.py

# 3. Zapisujemy kod wyjścia (0 = sukces, inne = błąd)
EXIT_CODE=$?

echo "----------------------------------------"
echo "!!! APLIKACJA ZAKOŃCZYŁA DZIAŁANIE (KOD: $EXIT_CODE) !!!"
echo "Jeśli KOD != 0, powyżej powinieneś widzieć błąd (SyntaxError, ImportError itp.)"
echo "System zasypia na 1 godzinę, abyś mógł sprawdzić logi bez restartu..."
echo "----------------------------------------"

# 4. Blokujemy restart kontenera
sleep 3600
