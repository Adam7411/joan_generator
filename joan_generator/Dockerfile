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

# Instalacja dodatkowych pakietów Python z requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

# Naprawa formatowania
RUN dos2unix /app/run.sh /app/run.py && chmod a+x /app/run.sh

CMD [ "/app/run.sh" ]
