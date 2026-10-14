# Local-only container image. This is NOT a public, multi-user service.
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CAREERPILOT_DATA_DIR=/data

WORKDIR /workspace
COPY pyproject.toml README.md ./
COPY app ./app
RUN python -m pip install --no-cache-dir . && \
    groupadd --system --gid 10001 careerpilot && \
    useradd --system --uid 10001 --gid 10001 --home-dir /workspace careerpilot && \
    mkdir -p /data && chown -R 10001:10001 /workspace /data

USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
