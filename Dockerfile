FROM python:3.12-slim

ARG ZETATECH_IMAGE_VERSION=unknown
ARG ZETATECH_IMAGE_TAG=unknown
ARG ZETATECH_IMAGE_BUILD=

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ZETATECH_HOST=0.0.0.0 \
    ZETATECH_PORT=8080 \
    ZETATECH_IMAGE_VERSION=${ZETATECH_IMAGE_VERSION} \
    ZETATECH_IMAGE_TAG=${ZETATECH_IMAGE_TAG} \
    ZETATECH_IMAGE_BUILD=${ZETATECH_IMAGE_BUILD}

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    git \
    gosu \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt

COPY . .
RUN npm --prefix /app/agents/nodejs ci && npm --prefix /app/agents/nodejs run build

RUN useradd -m -u 10001 appuser && \
    mkdir -p /app/Plugins /app/semgrep_results /app/sessions /home/appuser/.zetatech && \
    chown -R appuser:appuser /app /home/appuser

RUN sed -i 's/\r$//' /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "zetatech.py"]
