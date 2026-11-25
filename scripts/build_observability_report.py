"""Fill production report sections from measured CSV/API evidence."""
import csv
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/observability"
PROD = ROOT / "06-lab-complete/benchmark-observability/production"
RESULTS = ROOT / "benchmark-results"
RESULTS.mkdir(exist_ok=True)
for source in (PROD / "benchmark-results").glob("*.csv"):
    shutil.copy2(source, RESULTS / source.name)

load = lambda n: json.loads((OUT / n).read_text(encoding="utf-8"))
traces = load("trace_summary.json")
chaos = load("chaos_alerts.json")
metrics = load("metrics_snapshot.json")


def scalar(name):
    result = metrics[name]["data"]["result"]
    return float(result[0]["value"][1]) if result else float("nan")


lines = ["## 4. Observability stack", "",
    "Stack chạy local: Nginx :8080, Prometheus :9090, Grafana :3000, Jaeger :16686, Locust :8089. Image agent được sửa home của user từ /app sang /home/agent để Python tìm đúng packages đã copy sang /home/agent/.local; không đổi instrumentation, alert rule hay dataset.", "",
    "### 4.1 Golden Signals và Exercise 7.4", "",
    "Snapshot Prometheus dưới đây được thu trong thí nghiệm chaos; không phải số đo baseline Locust.", "",
    f"- Traffic /ask: {scalar('rps'):.3f} req/s; error rate: {scalar('error_rate'):.2%}.",
    f"- Avg latency: {scalar('avg_s') * 1000:.1f} ms; p95: {scalar('p95_s') * 1000:.1f} ms; p99: {scalar('p99_s') * 1000:.1f} ms. Percentile này ước tính từ histogram Prometheus, không phải percentile raw của Locust.",
    "- Tải theo instance:", "",
    "| Instance | /ask req/s |", "| --- | --- |"]
for value in metrics["rps_by_instance"]["data"]["result"]:
    lines.append(f"| {value['metric']['instance']} | {float(value['value'][1]):.3f} |")
lines += ["", "Các instance có lưu lượng là bằng chứng Nginx phân phối request. Chênh lệch ngắn hạn có thể đến từ số user hữu hạn, độ trễ ngẫu nhiên và scrape window; không yêu cầu mỗi giây bằng nhau tuyệt đối.", "",
    "| Token type | tokens/s |", "| --- | --- |"]
for value in metrics["tokens_by_type"]["data"]["result"]:
    lines.append(f"| {value['metric'].get('type')} | {float(value['value'][1]):.3f} |")
lines += ["", "Input tokens gồm system prompt, câu hỏi và context retrieval nên có thể lớn hơn output của câu trả lời ngắn. GET http://localhost:8080/metrics thực tế trả " + str(load("public_metrics_check.json")["status"]) + "; Nginx chặn endpoint vận hành từ bên ngoài, Prometheus scrape trực tiếp các agent trong mạng Docker.", "",
    "### 4.2 Alerts và chaos", "",
    "promtool test rules với alert_rules_test.yml: SUCCESS (xem reports/observability/alert_rules_test.log).", "",
    "Đã thực hiện đồng thời hai fault injection A+B: MOCK_ERROR_RATE=0.2, MOCK_SLOW_RATE=0.3; thực tế 2 agent, Locust 30 users, ramp 5 users/s (compose run đã đưa topology về deploy.replicas=2). Thời gian tính từ trước lệnh Compose áp dụng cấu hình tới lần poll đầu thấy firing; poll mỗi 10 giây nên đây là thời gian quan sát, không phải timestamp chuyển trạng thái chính xác. Hai tác động được bật cùng nhau, không suy diễn là hai phép đo cách ly.", "",
    "| Thí nghiệm | Alert | Thời gian quan sát tới firing | Panel |", "| --- | --- | --- | --- |"]
for kind, alert, panel in [("A: error rate 0.2", "AgentHighErrorRate", "Error rate"), ("B: slow rate 0.3", "AgentHighLatencyP95", "p95/p99 latency")]:
    elapsed = chaos["first_firing_seconds"].get(alert)
    lines.append(f"| {kind} | {alert} | {str(elapsed) + ' s' if elapsed is not None else 'Chưa quan sát firing'} | {panel} |")
lines += ["", "Hai alert cùng firing đã được lưu trong alerts_firing.json. Các thí nghiệm model lớn, pause instance và đổi v1 không được thực hiện trong lượt đo này. Nếu đổi v1 làm chất lượng giảm mà latency/error hạ tầng vẫn tốt, cần golden-dataset eval trước deploy và đánh giá chất lượng định kỳ/sampling trên traffic thực; dashboard xanh không chứng minh câu trả lời đúng.", "",
    "### 4.3 Trace và log correlation", "",
    "Trace được lấy bằng API v3 của Jaeger và giữ nguyên OTLP JSON; tham khảo [tài liệu API chính thức](https://www.jaegertracing.io/docs/2.23/architecture/apis/). Phân tích span chỉ là dữ liệu dẫn xuất từ timestamp/duration gốc.", ""]
for kind, label in [("slow", "Trace chậm"), ("error", "Trace lỗi")]:
    t = traces[kind]
    lines += [f"**{label}:** [{t['trace_id']}]({t['url']})", "",
        f"Tổng {t['total_ms']:.3f} ms; span `{t['llm_span']}` {t['llm_ms']:.3f} ms, chiếm {t['llm_percent']:.2f}%. " +
        ("Đây là trace chậm nhất trong tập kết quả truy vấn có log đối chiếu, gồm truy vấn lọc duration >=1s; không khẳng định chậm nhất toàn bộ lịch sử." if kind == "slow" else "Span lỗi có exception được ghi bởi OpenTelemetry; kiểm tra dữ liệu gốc ở error_trace.json."),
        "", "Dòng log JSON có cùng trace_id:", "", "```json", json.dumps(t["log"], ensure_ascii=False), "```", ""]
lines += ["### 4.4 Ảnh minh chứng", "",
    "Người học đã chụp và lưu bốn ảnh từ giao diện thật trong phiên tải capture bổ sung, cùng cấu hình chaos 2 agent. Ảnh Alerts thấy error-rate, latency và cost alert cùng firing. Capture bổ sung phục vụ ảnh minh chứng; thời gian tới firing ở mục 4.2 vẫn lấy từ lượt đo chaos ban đầu.", "",
    "- [x] [Grafana dashboard](screenshots/grafana-dashboard.png) — dashboard khi Locust đang có tải.",
    "- [x] [Jaeger slow trace](screenshots/jaeger-slow-trace.png) — trace chậm ở link trên.",
    "- [x] [Jaeger error trace](screenshots/jaeger-error-trace.png) — trace lỗi, mở event exception.",
    "- [x] [Prometheus Alerts](screenshots/prometheus-alert-firing.png) — cùng lúc ít nhất hai alert firing.", "",
    "## 5. Benchmark scaling", "",
    "Locust headless: 100 users, ramp 10 users/s, 2 phút mỗi topology. Chờ DNS 15 giây sau thay đổi instance. Dùng compose run --no-deps và kiểm tra số agent trước/sau để giữ đúng 1 hoặc 3 instance. Hai lượt ban đầu bị Compose tự đưa về 2 instance đã được loại khỏi bảng, giữ ở reports/observability/discarded_two_instances. Mock mặc định error 0.01, slow 0.03, model small, KB đã sửa. Mỗi agent giới hạn 0.5 CPU/256 MB theo Compose. Bảng lấy riêng dòng POST /ask trong CSV cuối, gồm cả response lỗi; JSON load_test.py ở mục 2 chỉ thống kê latency thành công nên không so sánh trực tiếp như cùng một phép đo.", "",
    "| Instances | RPS /ask | p50 ms | p95 ms | p99 ms | Failures / Requests | Error rate |",
    "| --- | --- | --- | --- | --- | --- | --- |"]
rows = []
for count in (1, 3):
    with (RESULTS / f"scale_{count}_stats.csv").open(encoding="utf-8") as file:
        row = next(r for r in csv.DictReader(file) if r["Name"] == "/ask")
    rows.append(row)
    fails, requests = int(row["Failure Count"]), int(row["Request Count"])
    lines.append(f"| {count} | {float(row['Requests/s']):.3f} | {row['50%']} | {row['95%']} | {row['99%']} | {fails}/{requests} | {fails/requests:.2%} |")
ratio = float(rows[1]["Requests/s"]) / float(rows[0]["Requests/s"])
lines += ["", f"RPS /ask với 3 instance bằng {ratio:.3f} lần 1 instance. Không kỳ vọng gấp ba: Locust cố định 100 users và mỗi user nghỉ 0.5–2 giây; mock LLM còn latency/tail được cấu hình riêng cho từng request, scale không làm mỗi lần gọi LLM nhanh hơn. Vì đây là mock async trên một máy, kết quả không chứng minh khả năng scale của provider LLM thật. Phân biệt tăng thông lượng xử lý với giảm tail latency cho mỗi request.", ""]
section = "\n".join(lines)
(OUT / "production_report.md").write_text(section, encoding="utf-8")
report_path = ROOT / "BENCHMARK_REPORT.md"
report = report_path.read_text(encoding="utf-8")
report = report[:report.index("## 4. Observability stack")] + section + "\n" + report[report.index("## 6. Nhận xét"):]
report_path.write_text(report, encoding="utf-8")
print("Updated production report from CSV and API evidence")
