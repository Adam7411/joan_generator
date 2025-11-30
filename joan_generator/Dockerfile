ARG BUILD_FROM
FROM $BUILD_FROM

# Instalacja Pythona i pip
RUN apk add --no-cache python3 py3-pip

# Katalog roboczy
WORKDIR /app

# Kopiowanie plików requirements
COPY requirements.txt .

# TU JEST ZMIANA: Dodano flagę --break-system-packages
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

# Kopiowanie reszty plików
COPY . .

# Uruchomienie aplikacji
CMD [ "python3", "run.py" ]
