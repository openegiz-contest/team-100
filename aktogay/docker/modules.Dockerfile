# Analysis modules image (akt-modules): standard library only, no pip packages.
# Build context is aktogay/:
#   docker build -f aktogay/docker/modules.Dockerfile -t aktogay/modules:local aktogay
FROM docker.io/library/python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /akt
COPY setup/things.json setup/
COPY modules/ modules/

USER nobody
CMD ["python", "-I", "/akt/modules/main.py", "run"]
