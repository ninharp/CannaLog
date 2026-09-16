ARG BUILD_FROM=ghcr.io/home-assistant/base:3.23
FROM $BUILD_FROM

# Python plus the native libraries WeasyPrint needs for PDF export
RUN apk add --no-cache \
        python3 \
        pango \
        fontconfig \
        font-dejavu \
        libffi

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python3 -m venv /venv \
    && /venv/bin/pip install --no-cache-dir -r /app/requirements.txt

COPY app/ /app/app/
COPY init_db.py run.py /app/
COPY homeassistant/run.sh /
RUN chmod a+x /run.sh

ENV PATH="/venv/bin:$PATH"

EXPOSE 5000

CMD [ "/run.sh" ]

LABEL \
    io.hass.type="addon" \
    io.hass.name="CannaLog" \
    org.opencontainers.image.source="https://github.com/ninharp/CannaLog"
