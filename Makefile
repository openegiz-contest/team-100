.PHONY: up down ps logs smoke clean example-mine example-mine-stop install uninstall status endpoints upgrade upload-build generate-data copy-build unity-demo check-secrets check-public-host akt-check akt-calib

# ---------------------------------------------------------------------------
# Docker Compose deployment (laptops, CI, contest judges): deploy/compose/
# ---------------------------------------------------------------------------
COMPOSE_BASE := docker compose -f deploy/compose/docker-compose.yml
# The Aktogay stand (aktogay/compose.yml: akt-models, akt-setup, akt-calib,
# akt-sim, akt-modules, akt-web) is an overlay on the platform. Every compose command
# loads it, so `up` starts it, `down` stops it and `clean` removes its data.
AKT_COMPOSE  := aktogay/compose.yml
# Once `make example-mine` has run, every compose command also loads the mine
# overlay, so `down` stops its simulator and `up` keeps its Grafana dashboard.
# `make clean` forgets it.
MINE_MARKER  := deploy/compose/.example-mine
MINE_COMPOSE := examples/mine/compose.yml
COMPOSE := $(COMPOSE_BASE) -f $(AKT_COMPOSE)$(if $(wildcard $(MINE_MARKER)), -f $(MINE_COMPOSE))

## Start the whole platform with Docker Compose (first run: generates credentials)
up:
	@bash scripts/compose-env.sh
	@bash scripts/compose-preflight.sh
	@bash aktogay/scripts/akt-preflight.sh
	@# Network fetches during the build (e.g. the extended API sources from GitHub) can drop;
	@# retry only the build, then start once.
	@for i in 1 2 3; do $(COMPOSE) build && break; \
	  if [ $$i = 3 ]; then echo "ERROR: build failed 3 times"; exit 1; fi; \
	  echo "build failed (attempt $$i of 3), retrying in 15 s"; sleep 15; done
	$(COMPOSE) up -d --wait --wait-timeout 900
	@# `--wait` does not wait for one-shot jobs to finish: a running init counts
	@# as up. Wait for it to exit, then check how.
	@test "$$(docker wait $$($(COMPOSE) ps -a -q init))" = 0 || { \
	  echo "ERROR: the init job (policy + Ditto connections) failed:"; $(COMPOSE) logs init; exit 1; }
	@# Same for akt-setup (Aktogay policy, Thing Models, 136 things): without
	@# this check the stand would be "up" with no things in it.
	@test "$$(docker wait $$($(COMPOSE) ps -a -q akt-setup))" = 0 || { \
	  echo "ERROR: the akt-setup job (Aktogay policy + things) failed:"; $(COMPOSE) logs akt-setup; exit 1; }
	@bash scripts/compose-wait-ready.sh
	@bash scripts/compose-urls.sh
	@bash aktogay/scripts/akt-urls.sh

## Stop the platform, keep data
down:
	$(COMPOSE) down

## Show compose service status
ps:
	@$(COMPOSE) ps -a

## Follow logs (one service: make logs S=gateway)
logs:
	$(COMPOSE) logs -f --tail=100 $(S)

## End-to-end check of the running compose stack
smoke:
	@bash scripts/compose-smoke.sh

## Run the Example Mine (twins + haul-cycle simulator + Grafana dashboard) on the compose stack
example-mine: up
	$(COMPOSE_BASE) -f $(MINE_COMPOSE) up -d --build --wait --wait-timeout 300
	@touch $(MINE_MARKER)
	@echo "Example Mine running: Grafana -> Dashboards -> OpenEgiz Examples -> Example Mine"

## Stop the Example Mine simulator (twins and data stay)
example-mine-stop:
	$(COMPOSE_BASE) -f $(MINE_COMPOSE) stop mine-simulator

## Stop the platform and DELETE all its data and credentials
clean:
	$(COMPOSE) down -v --remove-orphans
	rm -f deploy/compose/.env $(MINE_MARKER)

# ---------------------------------------------------------------------------
# Aktogay stand (aktogay/): checks on the running stack
# ---------------------------------------------------------------------------

## Aktogay stand: one "ok / FAIL + evidence" line per claim (containers, things per type in Ditto,
## InfluxDB points younger than 60 s per thing, web /api/state, module features, validation-calib).
## Exit 0; STRICT=1: 1 on a failure
akt-check:
	@bash aktogay/scripts/akt-check.sh

## Aktogay model calibration (2025 fit, 2024 and 2023 checks without refit, balances) in the
## simulator image (service akt-calib): prints the table, writes it with the on/off trial
## summary to the thing validation-calib (?view=calib); exit 0
akt-calib:
	$(COMPOSE) run --rm --no-deps -T akt-calib \
	  || echo "akt-calib: the calibration container did not run (see above)"

# ---------------------------------------------------------------------------
# Helm deployment (servers): the chart at the repository root
# ---------------------------------------------------------------------------
# Several values reference names derived from the release name (e.g. the
# telegraf configmap), so the release MUST be called "opentwins" until those
# references are made release-agnostic.
RELEASE_NAME := opentwins
NAMESPACE    := opentwins
CHART_PATH   := .

# Credentials live OUTSIDE this repo (rotated 2026-08-07). values.yaml carries
# only invalid placeholders, so install/upgrade must always be given this
# override file. Deliberately a hard failure rather than a silent fallback:
# deploying the placeholders would break Ditto auth and telemetry ingest.
SECRETS_FILE ?= $(HOME)/openegiz-deploy/secrets.values.yaml

# Address browsers use to reach this host; the Grafana app plugin calls Ditto
# and the extended API from the browser. Defaults to the first node's
# InternalIP; override with `make install PUBLIC_HOST=my-host.example`.
PUBLIC_HOST ?= $(shell kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null)

check-public-host:
	@test -n "$(PUBLIC_HOST)" || { \
	  echo "ERROR: could not determine PUBLIC_HOST from kubectl."; \
	  echo "       Pass it explicitly: make install PUBLIC_HOST=<ip-or-hostname>"; \
	  exit 1; }

check-secrets:
	@test -f "$(SECRETS_FILE)" || { \
	  echo "ERROR: secrets override not found: $(SECRETS_FILE)"; \
	  echo "       It holds the Ditto/Grafana/InfluxDB credentials that are"; \
	  echo "       intentionally absent from values.yaml. Create it from"; \
	  echo "       secrets.values.yaml.example, or point to another file with:"; \
	  echo "       make install SECRETS_FILE=/path/to/file"; \
	  exit 1; }

## Install the OpenEgiz Helm chart
install: check-secrets check-public-host
	helm install $(RELEASE_NAME) $(CHART_PATH) -n $(NAMESPACE) --create-namespace -f "$(SECRETS_FILE)" --set grafanaPlugin.publicHost=$(PUBLIC_HOST) --wait --timeout=15m --debug

## Upgrade the OpenEgiz Helm chart
upgrade: check-secrets check-public-host
	helm upgrade $(RELEASE_NAME) $(CHART_PATH) -n $(NAMESPACE) -f "$(SECRETS_FILE)" --set grafanaPlugin.publicHost=$(PUBLIC_HOST) --wait --timeout=15m --debug

## Uninstall the OpenEgiz Helm chart
uninstall:
	helm uninstall $(RELEASE_NAME) -n $(NAMESPACE) --wait

## Show pod statuses
status:
	@kubectl get pods -n $(NAMESPACE) -o wide

## Show all service endpoints (IP + port)
endpoints:
	@bash scripts/show-endpoints.sh

## Upload Unity WebGL build files to the nginx pod
upload-build:
	@bash scripts/upload-build.sh $(RELEASE_NAME)

## Oven demo: create the oven twins, then stream telemetry (Ctrl+C to stop).
## Compose by default; Helm: make generate-data MQTT_PORT=30511 DITTO_URL=http://localhost:30525 DITTO_PASSWORD=...
generate-data:
	@bash scripts/demo-oven.sh

## Download the demo Unity WebGL scene (88 MB, kept out of git) into ./build/
unity-demo:
	@bash scripts/unity-demo.sh

## Copy 4 Unity WebGL build files from SRC into ./build/
## Usage: make copy-build SRC=/path/to/source
copy-build:
	@bash scripts/copy-build.sh $(SRC)

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

## Static checks, same as the CI lint job: run before pushing
.PHONY: lint
lint:
	helm lint . -f secrets.values.yaml.example --set grafanaPlugin.publicHost=127.0.0.1
	helm template opentwins . -n opentwins -f secrets.values.yaml.example \
	  --set grafanaPlugin.publicHost=127.0.0.1 > /dev/null
	git ls-files -z '*.sh' | xargs -0 -n1 bash -n
	git ls-files -z 'scripts/*.sh' 'deploy/*.sh' | xargs -0 shellcheck --severity=warning
	git ls-files -z '*.py' | xargs -0 python3 -c 'import ast, sys; [ast.parse(open(f, encoding="utf-8").read(), f) for f in sys.argv[1:]]'
	@bash scripts/compose-env.sh
	docker compose -f deploy/compose/docker-compose.yml config -q
	@echo "lint: ok"
