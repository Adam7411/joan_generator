
ARG BUILD_FROM
FROM $BUILD_FROM

# Instalacja Pythona i pip
RUN apk add --no-cache python3 py3-pip

# Katalog roboczy
WORKDIR /app

# Kopiowanie plików
COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY . .

# Uruchomienie aplikacji
CMD [ "python3", "run.py" ]
