FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/*.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN ARCH=$(dpkg --print-architecture) \
    && curl -fsSL "https://caddyserver.com/api/download?os=linux&arch=${ARCH}" \
       -o /usr/local/bin/caddy \
    && chmod +x /usr/local/bin/caddy

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

RUN playwright install chromium

RUN for pkg in ttf-unifont ttf-ubuntu-font-family; do \
      mkdir -p /tmp/${pkg}/DEBIAN && \
      printf 'Package: %s\nVersion: 99\nArchitecture: all\nMaintainer: dummy\nDescription: dummy\n' "$pkg" \
        > /tmp/${pkg}/DEBIAN/control && \
      dpkg-deb --build /tmp/${pkg} /tmp/${pkg}.deb && \
      dpkg -i /tmp/${pkg}.deb; \
    done && rm -rf /tmp/ttf-*

RUN playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY Caddyfile /app/Caddyfile
COPY backend /app/backend
COPY frontend /app/frontend

RUN mkdir -p /app/data

EXPOSE 4444

CMD ["sh", "-c", "caddy run --config /app/Caddyfile & cd /app/backend && uvicorn main:app --host 0.0.0.0 --port 4445 --timeout-keep-alive 30"]
