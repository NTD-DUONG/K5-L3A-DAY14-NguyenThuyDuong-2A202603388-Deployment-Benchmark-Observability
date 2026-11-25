"""Run the original lab tools in WSL; preserve JSON and console evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "06-lab-complete/benchmark-observability/develop"
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)


def run_tool(label, args):
    print("RUN " + label, flush=True)
    result = subprocess.run([sys.executable, *args], cwd=DEV, capture_output=True, text=True)
    (REPORTS / (label + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr)
    print("DONE " + label + " exit=" + str(result.returncode), flush=True)


def agent(version, port, slow="0.03", errors="0.01"):
    env = {**os.environ, "AGENT_VERSION": version, "PORT": str(port),
           "MOCK_SLOW_RATE": slow, "MOCK_ERROR_RATE": errors}
    env.pop("AGENT_API_KEY", None)
    log = (REPORTS / f"agent_{version}_{port}.log").open("a", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "app.py"], cwd=DEV, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    for _ in range(100):
        if proc.poll() is not None:
            raise RuntimeError("Agent failed; inspect agent log")
        try:
            with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=1):
                return proc, log
        except Exception:
            time.sleep(0.1)
    proc.terminate()
    raise RuntimeError("Startup timeout")


def stop(pair):
    proc, log = pair
    proc.terminate()
    try:
        proc.wait(timeout=15)
    finally:
        if proc.poll() is None:
            proc.kill()
        log.close()


mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
if mode == "baseline":
    pair = agent("v2", 8002)
    try:
        for c in (1, 10, 50, 100):
            label = f"load_v2_c{c}"
            run_tool(label, ["load_test.py", "--url", "http://localhost:8002",
                            "--requests", "300", "--concurrency", str(c),
                            "--out", str(REPORTS / (label + ".json"))])
    finally:
        stop(pair)
    for slow in ("0", "0.03", "0.1"):
        pair = agent("v2", 8002, slow)
        try:
            label = f"load_v2_slow_{slow}"
            run_tool(label, ["load_test.py", "--url", "http://localhost:8002",
                            "--requests", "300", "--concurrency", "20",
                            "--out", str(REPORTS / (label + ".json"))])
        finally:
            stop(pair)
    for version, port in (("v1", 8001), ("v2", 8002)):
        pair = agent(version, port, errors="0")
        try:
            label = "eval_" + version
            args = ["eval/run_eval.py", "--url", f"http://localhost:{port}",
                    "--min-accuracy", "0.85", "--out", str(REPORTS / (label + ".json"))]
            if version == "v2":
                args += ["--baseline", str(REPORTS / "eval_v1.json")]
            run_tool(label, args)
        finally:
            stop(pair)
elif mode == "fixed":
    pair = agent("v2", 8002, errors="0")
    try:
        run_tool("eval_v2_fixed", ["eval/run_eval.py", "--url", "http://localhost:8002",
                 "--min-accuracy", "1.0", "--baseline", str(REPORTS / "eval_v2.json"),
                 "--out", str(REPORTS / "eval_v2_fixed.json")])
    finally:
        stop(pair)
else:
    raise SystemExit("Use baseline or fixed")
