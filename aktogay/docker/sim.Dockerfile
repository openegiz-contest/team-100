# Simulator image: Python with paho-mqtt and the aktogay model core.
# Build context is aktogay/:
#   docker build -f aktogay/docker/sim.Dockerfile -t aktogay/sim:local aktogay
# Default command: the simulator service (sim/service.py, compose service akt-sim).
# Other entry points of the same image:
#   python -I /akt/run.py service --dry-run --duration 30     no MQTT, counts messages
#   python -I /akt/sim/publish.py demo --duration 120         synthetic telemetry
#   python -I /akt/run.py trial --n 100 --out /tmp/trial.json  on/off trial (offline)
#   python -I /akt/run.py calib --quick                       calibration table
FROM docker.io/library/python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

# Same pin as the template's examples/mine (known to work with its Mosquitto).
RUN pip install paho-mqtt==2.1.0

WORKDIR /akt
COPY run.py ./
COPY setup/things.json setup/twins.py setup/
COPY sim/ sim/

USER nobody
CMD ["python", "-I", "/akt/run.py", "service"]
