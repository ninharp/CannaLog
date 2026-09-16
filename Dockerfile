FROM python:3.13-alpine

ARG VERSION=dev
ENV CANNALOG_VERSION=$VERSION

RUN apk add --no-cache pango fontconfig font-dejavu

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY init_db.py run.py ./

ENV CANNALOG_DATA_DIR=/data
VOLUME /data
EXPOSE 5000

CMD ["sh", "-c", "python init_db.py && exec gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 --timeout 120 --access-logfile - app:app"]

LABEL org.opencontainers.image.source="https://github.com/ninharp/CannaLog"
