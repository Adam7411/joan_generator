ARG BUILD_FROM
FROM $BUILD_FROM

# Instalacja pakietów systemowych
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-flask \
    py3-requests \
    py3-yaml \
    dos2unix

# Ustawiamy katalog roboczy
WORKDIR /app

# Kopiujemy WSZYSTKIE pliki do katalogu /app
COPY . .

# Naprawiamy plik run.sh (który teraz jest w /app/run.sh)
RUN dos2unix /app/run.sh && chmod a+x /app/run.sh

# Uruchamiamy skrypt z poprawnej ścieżki
CMD [ "/app/run.sh" ]
