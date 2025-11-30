ARG BUILD_FROM
FROM $BUILD_FROM

# Instalacja pakietów systemowych + GUNICORN
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-flask \
    py3-requests \
    py3-yaml \
    py3-gunicorn \
    dos2unix

WORKDIR /app
COPY . .

# Naprawa formatowania
RUN dos2unix /app/run.sh /app/run.py && chmod a+x /app/run.sh

CMD [ "/app/run.sh" ]
