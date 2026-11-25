"""Measure the supplied Docker stack; run from Windows with Docker Desktop."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PROD = ROOT / "06-lab-complete/benchmark-observability/production"
OUT = ROOT / "reports/observability"
OUT.mkdir(parents=True, exist_ok=True)
DOCKER = ["docker", "compose", "-p", "k5-day14-observability"]
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(path):
    with HTTP.open(path, timeout=20) as res:
        return json.load(res)


def run(label, args, env=None):
    print("RUN " + label, flush=True)
    with (OUT / (label + ".log")).open("w", encoding="utf-8") as log:
        result = subprocess.run(args, cwd=PROD, env=env, stdout=log, stderr=subprocess.STDOUT)
    print("DONE " + label + " exit=" + str(result.returncode), flush=True)
    return result.returncode


def wait_healthy():
    for _ in range(60):
        try:
            if get("http://localhost:8080/health")["status"] == "ok":
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("Agent not ready")


wait_healthy()
run("alert_rules_test", ["docker", "run", "--rm", "-v", str(PROD / "prometheus") + ":/p",
    "--entrypoint", "promtool", "prom/prometheus:v3.16.0", "test", "rules", "/p/alert_rules_test.yml"])
for count in (1, 3):
    if run(f"scale_{count}_up", DOCKER + ["up", "-d", "--scale", f"agent={count}"]) != 0:
        raise RuntimeError("Compose failed")
    wait_healthy()
    time.sleep(15)  # DNS refresh required by lab before measuring the new topology.
    actual = subprocess.check_output(DOCKER + ["ps", "-q", "agent"], cwd=PROD, text=True).splitlines()
    if len(actual) != count:
        raise RuntimeError(f"Expected {count} agents, found {len(actual)}")
    run(f"scale_{count}_locust", DOCKER + ["run", "--rm", "--no-deps", "locust", "-f", "/mnt/locust/locustfile.py",
        "--host", "http://nginx", "--headless", "-u", "100", "-r", "10", "-t", "2m",
        "--csv", f"/mnt/results/scale_{count}"])
    run(f"scale_{count}_ps", DOCKER + ["ps"])
    actual_after = subprocess.check_output(DOCKER + ["ps", "-q", "agent"], cwd=PROD, text=True).splitlines()
    if len(actual_after) != count:
        raise RuntimeError("Topology changed during load test")

if "--scaling-only" in sys.argv:
    raise SystemExit(0)

chaos_env = {**os.environ, "MOCK_ERROR_RATE": "0.2", "MOCK_SLOW_RATE": "0.3"}
started = time.time()
if run("chaos_up", DOCKER + ["up", "-d", "--scale", "agent=3"], chaos_env) != 0:
    raise RuntimeError("Chaos compose failed")
wait_healthy()
chaos_log = (OUT / "chaos_locust.log").open("w", encoding="utf-8")
load = subprocess.Popen(DOCKER + ["run", "--rm", "--no-deps", "--name", "day14-chaos-load", "locust",
    "-f", "/mnt/locust/locustfile.py", "--host", "http://nginx", "--headless",
    "-u", "30", "-r", "5", "-t", "10m", "--csv", "/mnt/results/chaos"],
    cwd=PROD, env=chaos_env, stdout=chaos_log, stderr=subprocess.STDOUT)
first = {}
snapshots = []
while time.time() - started < 300:
    elapsed = round(time.time() - started, 1)
    try:
        alerts = get("http://localhost:9090/api/v1/alerts")
        snapshots.append({"elapsed_s": elapsed, "response": alerts})
        firing = {a["labels"]["alertname"] for a in alerts["data"]["alerts"] if a["state"] == "firing"}
        for name in firing:
            first.setdefault(name, elapsed)
        print(f"CHAOS elapsed={elapsed}s firing={sorted(firing)}", flush=True)
        (OUT / "chaos_alerts.json").write_text(json.dumps({
            "started_unix": started, "first_firing_seconds": first,
            "config": {"MOCK_ERROR_RATE": 0.2, "MOCK_SLOW_RATE": 0.3, "users": 30},
            "samples": snapshots}, ensure_ascii=False, indent=2), encoding="utf-8")
        if {"AgentHighErrorRate", "AgentHighLatencyP95"} <= firing:
            (OUT / "alerts_firing.json").write_text(json.dumps(alerts, indent=2), encoding="utf-8")
            break
    except Exception as exc:
        print("MONITOR " + str(exc), flush=True)
    time.sleep(10)

run("agent_logs", DOCKER + ["logs", "--no-color", "agent"])
for name, url in {
    "prometheus_targets": "http://localhost:9090/api/v1/targets",
    "jaeger_services": "http://localhost:16686/api/services",
    "jaeger_traces": "http://localhost:16686/api/traces?service=observable-agent&limit=100&lookback=1h",
}.items():
    try:
        (OUT / (name + ".json")).write_text(json.dumps(get(url), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(name + " " + str(exc), flush=True)
print("READY_FOR_SCREENSHOTS; chaos Locust remains running up to 10 minutes", flush=True)
