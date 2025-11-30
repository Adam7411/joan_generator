ARG BUILD_FROM
FROM $BUILD_FROM

# Dodajemy py3-gunicorn do listy pakietów
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

RUN dos2unix /app/run.sh /app/run.py && chmod a+x /app/run.sh

CMD [ "/app/run.sh" ]
