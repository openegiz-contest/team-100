# akt-web image: Python standard library only, no pip, no network at build time.
# Build context is aktogay/:
#   docker build -f aktogay/web/docker/web.Dockerfile -t aktogay/web:local aktogay
FROM docker.io/library/python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /akt
COPY web/server.py web/
COPY web/static/ web/static/

USER nobody
EXPOSE 8000
CMD ["python", "-I", "/akt/web/server.py"]
