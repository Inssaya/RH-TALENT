# One image for api, worker and beat (same code, different command).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

# Optional extra CA certificates (corporate proxy): drop *.crt files in ./ca at the repository root.
COPY ca/ /usr/local/share/ca-certificates/extra/
# WITH_OCR=1 installs Tesseract (local OCR fallback for scans). WITH_OCR=0 gives a smaller image;
# scans are then read by Mistral OCR only (or flagged "to check" if no key is configured).
# APT_HTTPS=1 makes apt use https mirrors (for proxies that only allow HTTPS CONNECT).
ARG WITH_OCR=1
ARG APT_HTTPS=0
RUN update-ca-certificates \
 && if [ "$WITH_OCR" = "1" ]; then \
      if [ "$APT_HTTPS" = "1" ]; then sed -i 's#http://#https://#g' /etc/apt/sources.list.d/*.sources 2>/dev/null || true; fi; \
      apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra tesseract-ocr-ara libmagic1 \
      && rm -rf /var/lib/apt/lists/*; \
    fi
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt PIP_CERT=/etc/ssl/certs/ca-certificates.crt

WORKDIR /srv
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install -e ".[ocr,s3]"
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN useradd -r -u 1000 -m app \
 && mkdir -p /data/storage && chown -R app:app /data /srv/app/data \
 && chmod +x /usr/local/bin/docker-entrypoint.sh
USER app
ENV STORAGE_DIR=/data/storage
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health',timeout=4)" || exit 1
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--proxy-headers"]
