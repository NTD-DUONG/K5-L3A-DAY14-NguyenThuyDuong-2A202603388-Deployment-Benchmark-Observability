"""Keep a local chaos scenario running briefly for genuine UI screenshots."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

root = Path(__file__).resolve().parents[1]
prod = root / "06-lab-complete/benchmark-observability/production"
out = root / "reports/observability"
cmd = ["docker", "compose", "-p", "k5-day14-observability"]
env = {**os.environ, "MOCK_ERROR_RATE": "0.2", "MOCK_SLOW_RATE": "0.3"}
http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
started = time.time()
subprocess.run(cmd + ["up", "-d", "--scale", "agent=2"], cwd=prod, env=env, check=True)
existing = subprocess.check_output(["docker", "ps", "-q", "--filter", "name=^day14-capture-load$"], text=True).strip()
if not existing:
    subprocess.run(cmd + ["run", "--rm", "--no-deps", "-d", "--name", "day14-capture-load", "locust",
        "-f", "/mnt/locust/locustfile.py", "--host", "http://nginx", "--headless", "-u", "30", "-r", "5",
        "-t", "15m", "--csv", "/mnt/results/capture"], cwd=prod, env=env, check=True)
for attempt in range(30):
    with http.open("http://localhost:9090/api/v1/alerts", timeout=10) as res:
        data = json.load(res)
    firing = {a["labels"]["alertname"] for a in data["data"]["alerts"] if a["state"] == "firing"}
    print(f"Capture elapsed {time.time()-started:.1f}s, firing={sorted(firing)}", flush=True)
    if {"AgentHighErrorRate", "AgentHighLatencyP95"} <= firing:
        (out / "capture_alerts_firing.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        print("READY: http://localhost:9090/alerts and http://localhost:3000/d/day14-agent-overview", flush=True)
        break
    time.sleep(10)
else:
    raise SystemExit("Two alerts not yet observed; inspect Prometheus before taking screenshot")
