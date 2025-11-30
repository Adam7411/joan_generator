ARG BUILD_FROM
FROM $BUILD_FROM

# Pakiety
RUN apk add --no-cache python3 py3-pip py3-flask py3-requests py3-yaml dos2unix

WORKDIR /app
COPY . .

# NAPRAWIAMY OBA PLIKI (run.sh i run.py)
RUN dos2unix /app/run.sh /app/run.py && chmod a+x /app/run.sh

CMD [ "/app/run.sh" ]
