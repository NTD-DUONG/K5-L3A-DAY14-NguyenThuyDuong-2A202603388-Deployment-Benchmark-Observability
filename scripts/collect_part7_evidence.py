"""Collect original API responses and correlate Jaeger traces with agent logs."""
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PROD = ROOT / "06-lab-complete/benchmark-observability/production"
OUT = ROOT / "reports/observability"
OUT.mkdir(parents=True, exist_ok=True)
http = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(url):
    with http.open(url, timeout=30) as res:
        return json.load(res)


queries = {
    "rps": 'sum(rate(http_requests_total{job="agent",route="/ask"}[1m]))',
    "avg_s": 'sum(rate(http_request_duration_seconds_sum{job="agent",route="/ask"}[1m])) / sum(rate(http_request_duration_seconds_count{job="agent",route="/ask"}[1m]))',
    "p95_s": 'histogram_quantile(0.95,sum by(le)(rate(http_request_duration_seconds_bucket{job="agent",route="/ask"}[1m])))',
    "p99_s": 'histogram_quantile(0.99,sum by(le)(rate(http_request_duration_seconds_bucket{job="agent",route="/ask"}[1m])))',
    "error_rate": 'sum(rate(http_requests_total{job="agent",route="/ask",status=~"5.."}[1m]))/sum(rate(http_requests_total{job="agent",route="/ask"}[1m]))',
    "rps_by_instance": 'sum by(instance)(rate(http_requests_total{job="agent",route="/ask"}[1m]))',
    "tokens_by_type": 'sum by(type)(rate(llm_tokens_total[1m]))',
}
if not (OUT / "metrics_snapshot.json").exists():
    metrics = {name: get("http://localhost:9090/api/v1/query?" + urllib.parse.urlencode({"query": query}))
               for name, query in queries.items()}
    (OUT / "metrics_snapshot.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
now = datetime.now(timezone.utc)
params = {"query.service_name": "observable-agent", "query.search_depth": "100",
          "query.start_time_min": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
          "query.start_time_max": now.isoformat().replace("+00:00", "Z")}
traces = get("http://localhost:16686/api/v3/traces?" + urllib.parse.urlencode(params))
(OUT / "jaeger_traces.json").write_text(json.dumps(traces, ensure_ascii=False, indent=2), encoding="utf-8")
slow_traces = get("http://localhost:16686/api/v3/traces?" + urllib.parse.urlencode({**params, "query.duration_min": "1s"}))
(OUT / "jaeger_slow_search.json").write_text(json.dumps(slow_traces, ensure_ascii=False, indent=2), encoding="utf-8")
raw = subprocess.check_output(["docker", "compose", "-p", "k5-day14-observability", "logs", "--no-color", "agent"], cwd=PROD).decode("utf-8", errors="replace")
if (OUT / "agent_logs.log").exists():
    raw = (OUT / "agent_logs.log").read_text(encoding="utf-8") + "\n" + raw
(OUT / "agent_logs.log").write_text(raw, encoding="utf-8")
events = []
for line in raw.splitlines():
    try:
        event = json.loads(line[line.index("{"):])
        if event.get("trace_id"):
            events.append(event)
    except (ValueError, json.JSONDecodeError):
        pass


def duration(trace):
    spans = trace["spans"]
    return max(s["startTime"] + s["duration"] for s in spans) - min(s["startTime"] for s in spans)


grouped = defaultdict(list)
for resource in traces["result"]["resourceSpans"] + slow_traces["result"].get("resourceSpans", []):
    for scope in resource.get("scopeSpans", []):
        for span in scope.get("spans", []):
            grouped[span["traceId"]].append({
                "operationName": span["name"],
                "startTime": int(span["startTimeUnixNano"]) / 1000,
                "duration": (int(span["endTimeUnixNano"]) - int(span["startTimeUnixNano"])) / 1000,
                "tags": [{"key": "error", "value": span.get("status", {}).get("code") in (2, "STATUS_CODE_ERROR")}],
            })
logged_ids = {event["trace_id"] for event in events}
available = [{"traceID": tid, "spans": spans} for tid, spans in grouped.items()
             if tid in logged_ids and any(s["operationName"].startswith("chat ") for s in spans)]
slow = max(available, key=duration)
errors = [t for t in available if any(
    tag.get("key") == "error" and tag.get("value") is True for s in t["spans"] for tag in s.get("tags", []))]
selected = {"slow": slow}
if errors:
    selected["error"] = errors[0]
summary = {}
for kind, trace in selected.items():
    tid = trace["traceID"]
    # Fetch a standalone response, suitable for checking exact IDs and span events.
    detail = get("http://localhost:16686/api/v3/traces/" + tid)
    (OUT / (kind + "_trace.json")).write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
    relevant = [e for e in events if e["trace_id"] == tid]
    if not relevant:
        raise RuntimeError("No matching log for selected " + kind + " trace")
    llm = max((s for s in trace["spans"] if s["operationName"].startswith("chat ")), key=lambda s: s["duration"])
    summary[kind] = {"trace_id": tid, "total_ms": duration(trace) / 1000,
        "llm_span": llm["operationName"], "llm_ms": llm["duration"] / 1000,
        "llm_percent": round(llm["duration"] / duration(trace) * 100, 2),
        "log": next((e for e in relevant if e.get("event") == "llm_error"), relevant[0]),
        "url": "http://localhost:16686/trace/" + tid}
(OUT / "trace_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
req = urllib.request.Request("http://localhost:8080/metrics")
try:
    with http.open(req, timeout=10) as response:
        code = response.status
except urllib.error.HTTPError as exc:
    code = exc.code
(OUT / "public_metrics_check.json").write_text(json.dumps({"path": "http://localhost:8080/metrics", "status": code}), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
