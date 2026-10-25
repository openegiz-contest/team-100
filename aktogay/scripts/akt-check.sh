#!/usr/bin/env bash
#
# Aktogay stand check (make akt-check): one "ok / FAIL + evidence" line per
# claim. Reads only what the interface reads: Ditto (HTTP), InfluxDB (Flux)
# and the web API on the host ports; nothing is written. Always exits 0, so
# a check never stops a run; STRICT=1 returns 1 when a line failed.
#
#   containers      akt-models, akt-sim, akt-modules, akt-web running; akt-setup exit 0
#   Ditto           things of kz.aktogay counted per type; site state, sim_time moves
#   InfluxDB        points younger than 60 s per thing (idSimulationRun of the site)
#   web             /healthz and /api/state answer, thing count
#   modules         mod-losses, mod-ore, mod-priority carry their features for the current run
#   calibration     validation-calib DONE (rows of the table, N of the on/off trial) or RUNNING
#
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/deploy/compose/docker-compose.yml" -f "$ROOT/aktogay/compose.yml")
# shellcheck disable=SC1091
set -a; . "$ROOT/deploy/compose/.env"; set +a

HOST=127.0.0.1
NS=kz.aktogay
DITTO="http://$HOST:${DITTO_PORT:-8080}"
INFLUX="http://$HOST:${INFLUXDB_PORT:-8086}"
WEB="http://$HOST:${AKT_WEB_PORT:-8000}"
MODELS="http://$HOST:${AKT_MODELS_PORT:-8092}"
FAILED=0

pass() { printf '  \033[32mok\033[0m    %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAILED=1; }
note() { printf '        %s\n' "$1"; }

# Ditto answers 503 for a few seconds at a time while its JVMs warm up: retry reads.
ditto_get() {
  local out
  for _ in $(seq 1 10); do
    if out="$(curl -sf -m 15 -u "ditto:$DITTO_PASSWORD" "$DITTO/api/2/$1" 2>/dev/null)"; then
      printf '%s' "$out"; return 0
    fi
    sleep 2
  done
  return 1
}
# Flux query as annotated CSV (InfluxDB ends its CSV lines with CR LF: drop the CR).
flux() {
  curl -sf -m 30 -X POST "$INFLUX/api/v2/query?org=opentwins" \
    -H "Authorization: Token $INFLUXDB_TOKEN" -H 'Content-Type: application/vnd.flux' \
    -H 'Accept: application/csv' --data "$1" 2>/dev/null | tr -d '\r'
}
# value of one feature: GET .../features/<f>/properties/value (JSON scalar)
feat() { ditto_get "things/$NS:$1/features/$2/properties/value" | tr -d '"'; }

echo "Containers"
for svc in akt-models akt-sim akt-modules akt-web; do
  st="$("${COMPOSE[@]}" ps --format '{{.Service}} {{.State}} {{.Health}}' 2>/dev/null | awk -v s="$svc" '$1==s{print $2 ($3!=""?" "$3:"")}')"
  case "$st" in
    running|"running healthy") pass "$svc: $st" ;;
    *) fail "$svc: ${st:-not running}" ;;
  esac
done
setup_exit="$("${COMPOSE[@]}" ps -a --format '{{.Service}} {{.ExitCode}}' 2>/dev/null | awk '$1=="akt-setup"{print $2}')"
if [ "$setup_exit" = "0" ]; then pass "akt-setup finished: $("${COMPOSE[@]}" logs --no-log-prefix --tail 1 akt-setup 2>/dev/null | cut -c1-110)"
else fail "akt-setup exit code: ${setup_exit:-not run}"; fi

echo "Ditto: things of $NS"
all=""; cursor=""
for _ in $(seq 1 10); do
  opt="size(200)"; [ -n "$cursor" ] && opt="size(200),cursor($cursor)"
  page="$(ditto_get "search/things?filter=like(thingId,%22$NS:*%22)&fields=thingId,attributes/type&option=$opt")" || break
  all="$all$page"
  cursor="$(printf '%s' "$page" | grep -o '"cursor":"[^"]*"' | cut -d'"' -f4)"
  [ -n "$cursor" ] || break
done
n_things="$(printf '%s' "$all" | grep -o '"thingId":"[^"]*"' | sort -u | wc -l | tr -d ' ')"
by_type="$(printf '%s' "$all" | grep -o '"type":"[^"]*"' | cut -d'"' -f4 | sort | uniq -c | awk '{printf "%s=%s ", $2, $1}')"
if [ "${n_things:-0}" -ge 141 ]; then pass "things: $n_things (design: 141 permanent + batches + issues)"
else fail "things: ${n_things:-0} (expected at least 141)"; fi
note "per type: ${by_type:-none}"
policy="$(ditto_get "policies/$NS:policy" | grep -o '"policyId":"[^"]*"' | cut -d'"' -f4)"
if [ -n "$policy" ]; then pass "policy $policy exists"; else fail "policy $NS:policy not found"; fi
tm_ok="$(feat validation-setup tm_fetch_ok 2>/dev/null)"
[ -n "$tm_ok" ] && note "validation-setup.tm_fetch_ok = $tm_ok"
if curl -sf -m 10 -o /dev/null "$MODELS/tm/site-1.0.0.tm.jsonld"; then pass "Thing Models served at $MODELS/tm/"
else fail "Thing Models not served at $MODELS/tm/"; fi

echo "Stand alive (site thing)"
state="$(feat site state)"; run="$(feat site idSimulationRun)"; t1="$(feat site sim_time)"
degraded="$(feat site degraded)"; speed="$(feat site speed)"
sleep 5
t2="$(feat site sim_time)"
case "$state" in
  RUN) if awk -v a="${t1:-0}" -v b="${t2:-0}" 'BEGIN{exit !(b>a)}'; then pass "site.state RUN, sim_time $t1 -> $t2 in 5 s (x$speed), run $run"
       else fail "site.state RUN but sim_time did not move in 5 s ($t1 -> $t2)"; fi ;;
  PAUSED) pass "site.state PAUSED (speed 0 or 20:00 of a scenario), sim_time $t2, run $run" ;;
  WARMUP) pass "site.state WARMUP (a run is warming up 06:00 -> 08:00), run $run" ;;
  *) fail "site.state is '${state:-?}'" ;;
esac
if [ "${degraded:-1}" = "0.0" ] || [ "${degraded:-1}" = "0" ]; then pass "site.degraded 0 (no barrier timeout in this run)"
else fail "site.degraded = ${degraded:-?}"; fi

echo "InfluxDB: points younger than 60 s"
q='from(bucket:"default") |> range(start:-60s)
 |> filter(fn:(r) => r._measurement == "mqtt_consumer" and r._field == "value_sim_time_properties_value" and r.thingId =~ /^'"$NS"':/)
 |> group(columns:["thingId"]) |> count() |> group() |> keep(columns:["thingId","_value"]) |> sort(columns:["thingId"])'
csv="$(flux "$q")"
if [ -z "$csv" ]; then
  fail "InfluxDB query failed (token or port)"
else
  pairs="$(printf '%s\n' "$csv" | awk -F, 'NR==1{for(i=1;i<=NF;i++){if($i=="thingId")t=i;if($i=="_value")v=i}; next} $0!="" && t && v && $t!="" {n=$t; sub(/^[^:]*:/,"",n); printf "%s=%s ", n, $v}')"
  n_fresh="$(printf '%s' "$pairs" | wc -w | tr -d ' ')"
  n_pts="$(printf '%s' "$pairs" | tr ' ' '\n' | awk -F= '{s+=$2} END{print s+0}')"
  if [ "${n_fresh:-0}" -ge 40 ]; then pass "$n_fresh things with points younger than 60 s, $n_pts points in all"
  elif [ "$state" = "PAUSED" ] && [ "${n_fresh:-0}" -ge 1 ]; then pass "$n_fresh thing(s) with points younger than 60 s (paused: only the site heartbeat), $n_pts points"
  else fail "only ${n_fresh:-0} things with points younger than 60 s ($n_pts points); the simulator or Telegraf is not feeding InfluxDB"; fi
  printf '%s\n' "$pairs" | fold -s -w 96 | sed 's/^/        /'
fi

echo "Web interface"
if curl -sf -m 10 -o /dev/null "$WEB/healthz"; then pass "$WEB/healthz answers"; else fail "$WEB/healthz does not answer"; fi
st="$(curl -sf -m 20 "$WEB/api/state" 2>/dev/null)"
# server.py writes JSON with ": " between key and value
cnt="$(printf '%s' "$st" | grep -o '"count": *[0-9]*' | head -1 | tr -dc '0-9')"
if [ -n "$cnt" ] && [ "$cnt" -ge 49 ]; then pass "$WEB/api/state ok: $cnt things (Ditto through the interface)"
else fail "$WEB/api/state: ${cnt:-no answer} things"; fi
if curl -sf -m 10 "$WEB/?view=plan" | grep -q '<html'; then pass "$WEB/?view=plan serves the page"; else fail "$WEB/?view=plan does not serve the page"; fi

echo "Modules (mod-* things, written by akt-modules only)"
check_mod() {   # thing, feature with text, label
  local thing="$1" f="$2" txt mrun pst
  # first 14 words: cutting by bytes would split a Cyrillic letter
  txt="$(feat "$thing" "$f" | cut -d' ' -f1-14)"; mrun="$(feat "$thing" idSimulationRun)"; pst="$(feat "$thing" processed_sim_time)"
  if [ -z "$txt" ] || [ -z "$pst" ]; then fail "$thing: no $f / processed_sim_time"; return; fi
  if [ "$mrun" = "$run" ]; then pass "$thing: processed_sim_time $pst (run of the site), $f = $txt"
  else fail "$thing: run '$mrun' differs from the site run '$run' (processed_sim_time $pst); the module is behind or stopped"; fi
}
check_mod mod-losses top_text
check_mod mod-ore fc_text
check_mod mod-priority queue_text
n_issues="$(printf '%s' "$by_type" | grep -o 'issue=[0-9]*' | cut -d= -f2)"
note "issue-* things: ${n_issues:-0} (queue of the priority module)"

echo "Calibration (validation-calib, written by the one-shot akt-calib)"
cal_state="$(feat validation-calib state)"
cal_exit="$("${COMPOSE[@]}" ps -a --format '{{.Service}} {{.State}} {{.ExitCode}}' 2>/dev/null | awk '$1=="akt-calib"{print $2" "$3}')"
case "$cal_state" in
  DONE)
    rep="$(ditto_get "things/$NS:validation-calib/features/report_json/properties/value")"
    n_rows="$(printf '%s' "$rep" | grep -o '\\"group\\"' | wc -l | tr -d ' ')"
    n_trial="$(feat validation-calib shifts_total)"; n_trial="${n_trial%.*}"
    pass "validation-calib DONE: $n_rows calibration rows, on/off trial N ${n_trial:-?} (?view=calib)" ;;
  RUNNING) pass "validation-calib RUNNING: akt-calib is computing (about 2 min after start)" ;;
  *) fail "validation-calib state '${cal_state:-?}' (akt-calib: ${cal_exit:-not run}); run make akt-calib" ;;
esac

echo
if [ "$FAILED" = 0 ]; then echo "akt-check: every line ok."; else echo "akt-check: some lines FAILED (see above)."; fi
if [ "${STRICT:-0}" = "1" ] && [ "$FAILED" != 0 ]; then exit 1; fi
exit 0
