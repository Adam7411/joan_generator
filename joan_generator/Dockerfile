ARG BUILD_FROM
FROM $BUILD_FROM

# Instalacja Pythona i pip
RUN apk add --no-cache python3 py3-pip

# Katalog roboczy
WORKDIR /app

# Kopiowanie requirements
COPY requirements.txt .

# Instalacja zależności (z fixem dla Alpine)
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

# Kopiowanie skryptu startowego i nadanie uprawnień (TO JEST NOWE)
COPY run.sh /
RUN chmod a+x /run.sh

# Kopiowanie reszty plików aplikacji
COPY . .

# Uruchomienie przez skrypt run.sh zamiast bezpośrednio pythona
CMD [ "/run.sh" ]
