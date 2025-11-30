ARG BUILD_FROM
FROM $BUILD_FROM

# Instalujemy gotowe pakiety systemowe (Flask, Requests, YAML, dos2unix)
# To jest znacznie stabilniejsze niz pip w Home Assistant
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-flask \
    py3-requests \
    py3-yaml \
    dos2unix

WORKDIR /app

# Kopiujemy pliki
COPY . .

# Naprawiamy format pliku run.sh i nadajemy uprawnienia
RUN dos2unix /run.sh && chmod a+x /run.sh

# Uruchamiamy
CMD [ "/run.sh" ]
