ARG BUILD_FROM
FROM $BUILD_FROM

# Instalacja Python, pip oraz dos2unix (do naprawy plikow z Windows)
RUN apk add --no-cache python3 py3-pip dos2unix

# Katalog roboczy
WORKDIR /app

# Kopiowanie requirements
COPY requirements.txt .

# Instalacja zależności
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

# Kopiowanie skryptu startowego
COPY run.sh /

# NAPRAWA PLIKU Z WINDOWS (usuwa znaki CRLF) i nadanie uprawnień
RUN dos2unix /run.sh && chmod a+x /run.sh

# Kopiowanie reszty plików
COPY . .

# Uruchomienie
CMD [ "/run.sh" ]
