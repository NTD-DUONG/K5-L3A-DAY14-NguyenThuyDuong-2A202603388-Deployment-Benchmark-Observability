"""Generate local benchmark tables from measured JSON, never invented values."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
reports = root / "reports"
read = lambda name: json.loads((reports / name).read_text(encoding="utf-8"))
lines = [
    "# Benchmark & Observability Report — Day 14", "",
    "**Họ tên:** NguyenThuyDuong (theo tên repo)", "**Ngày chạy:** 25/11/2026 (GMT+7)",
    "**Môi trường:** Windows + Ubuntu WSL2, Python 3.11.18; WSL báo 8 CPU logic, MemTotal 7.997.660 kB (~7,63 GiB). Docker Desktop. Agent local chạy trong WSL; benchmark production chạy qua Docker.", "",
    "## 1. SLO của agent", "",
    "| SLI | SLO | Lý do |", "| --- | --- | --- |",
    "| p95 /ask | ≤500 ms | Ngưỡng mặc định load_test.py, theo dõi phần lớn trải nghiệm thay vì chỉ average. |",
    "| Error rate /ask | ≤2% | Ngưỡng mặc định; mock có xác suất lỗi 1%, vẫn giữ khoảng dung sai. |",
    "| Accuracy | ≥85% cho CI; 100% sau sửa KB | CI chặn chất lượng thấp; bài yêu cầu v2 cuối đạt 23/23, không regression. |", "",
    "## 2. Benchmark hiệu năng local", "",
    "Mỗi lần chạy 300 request; mock mặc định latency 120 ms, jitter 60 ms, retrieval 20 ms, slow thêm 1500 ms, error rate 0.01. Các load test chạy trên KB ban đầu. Không lặp lại để chọn kết quả đẹp. Image Docker đang được tải trong nền trong quá trình benchmark local, nên có thể gây nhiễu tài nguyên; đây là số đo trên laptop, không phải công suất cloud. Latency JSON chỉ tính các request HTTP 200; error rate tính toàn bộ request.", "",
    "### 2.1 Concurrency vs latency", "",
    "| Concurrency | RPS | p50 ms | p95 ms | p99 ms | Error rate | SLO |",
    "| --- | --- | --- | --- | --- | --- | --- |",
]
for c in (1, 10, 50, 100):
    d = read(f"load_v2_c{c}.json")
    lat = d["latency_ms"]
    lines.append(f"| {c} | {d['rps']} | {lat['p50']} | {lat['p95']} | {lat['p99']} | {d['error_rate']:.2%} | {'PASS' if d['slo']['passed'] else 'FAIL'} |")
lines += ["", "RPS không tăng tuyến tính: client/server cùng chia sẻ CPU, event loop, kết nối và chi phí xử lý/log; request slow giữ slot lâu hơn. 300 request là mẫu nhỏ, số lỗi ngẫu nhiên có thể vượt ngưỡng dù cấu hình lỗi chỉ 1%. Các lần FAIL được giữ nguyên.", "",
    "### 2.2 Tail latency", "",
    "Cùng concurrency 20 và 300 request, restart agent cho mỗi slow rate.", "",
    "| MOCK_SLOW_RATE | avg ms | p95 ms | p99 ms |", "| --- | --- | --- | --- |"]
for rate in ("0", "0.03", "0.1"):
    lat = read(f"load_v2_slow_{rate}.json")["latency_ms"]
    lines.append(f"| {rate} | {lat['avg']} | {lat['p95']} | {lat['p99']} |")
lines += ["", "p99 nhạy với số ít request chậm; khi slow rate lên 10%, p95 cũng rơi vào nhóm chậm. Average trộn phần lớn request nhanh với phần nhỏ request slow, nên có thể che giấu trải nghiệm tệ của nhóm cuối. Với mẫu 300 và ngẫu nhiên, percentile không nhất thiết đơn điệu giữa mọi lần chạy.", "",
    "## 3. Benchmark chất lượng", "",
    "Eval tắt lỗi upstream (`MOCK_ERROR_RATE=0`) để tách chất lượng khỏi lỗi ngẫu nhiên; slow rate vẫn 0.03. Golden dataset và script eval giữ nguyên.", "",
    "| Chỉ số | v1 | v2 ban đầu | v2 sau sửa |", "| --- | --- | --- | --- |"]
evals = [read(n) for n in ("eval_v1.json", "eval_v2.json", "eval_v2_fixed.json")]
for label, vals in [
    ("Accuracy", [f"{d['passed']}/{d['total']} ({d['accuracy']:.2%})" for d in evals]),
    ("Avg tokens/câu", [d["avg_tokens"] for d in evals]),
    ("Tổng cost USD", [d["total_cost_usd"] for d in evals]),
    ("Cost/câu đúng USD", [d["cost_per_correct_usd"] for d in evals]),
    ("Latency p95 ms", [d["latency_ms"]["p95"] for d in evals]),
    ("Quality gate", ["PASS" if d["quality_gate"]["passed"] else "FAIL" for d in evals]),
]:
    lines.append("| " + " | ".join(map(str, [label, *vals])) + " |")
lines += ["", "| Câu sai ban đầu | Keyword thiếu | Sửa KB |", "| --- | --- | --- |",
    "| security-02 | token, hết hạn, chữ ký | Bổ sung tài liệu phân biệt API key cố định và JWT có chữ ký, expiration. |",
    "| scaling-03 | cpu, memory, custom metrics | Bổ sung tài liệu Kubernetes HPA dùng CPU, memory và custom metrics. |", "",
    "Đã sửa cùng hai entry trong mock_llm.py bản develop và production. Eval cuối so với baseline v2: 2 câu được sửa, 0 regression, quality gate 100% PASS. v2 dùng retrieval nên prompt/token và chi phí mỗi câu tăng, nhưng chi phí mỗi câu đúng giảm rõ rệt so với v1. Chi phí là số mô phỏng từ mock, không phải hóa đơn LLM thật.", "",
    "Workflow `.github/workflows/eval.yml` chạy agent v2 rồi eval với --min-accuracy 0.85; exit code 1 làm job fail. Để thực sự chặn merge cần bật required status check trong branch protection trên GitHub; chưa thay đổi cài đặt này và chưa khẳng định workflow đã chạy trên GitHub.", "",
    "## 4. Observability stack", "",
    "Đang thực hiện; chưa có kết quả dashboard, trace và chaos để kết luận. Không dùng số mẫu trong README làm số đo.", "",
    "## 5. Benchmark scaling", "",
    "Đang thực hiện Locust headless 100 users, ramp 10 users/s, 2 phút, 1 và 3 instance. CSV và bảng sẽ được bổ sung khi có kết quả thật.", "",
    "## 6. Nhận xét", "",
    "1. Latency tốt chưa chứng minh câu trả lời đúng: v1 cần eval để phát hiện chất lượng thấp.",
    "2. Percentile và error rate phải đọc cùng nhau; mock lỗi và tail latency là hai yếu tố khác nhau.",
    "3. CI cần dùng dataset cố định, baseline và exit code để ngăn regression; không sửa đáp án để nâng điểm.", "",
    "Nếu vận hành thật, cần thêm metric/error ở Nginx hoặc synthetic check vì lỗi 504 có thể không xuất hiện ở metric của agent; thêm quality eval định kỳ, token/cost theo model và kiểm soát cardinality.", "",
    "## Bằng chứng và tái lập", "",
    "JSON và console log trong `reports/`. Script `scripts/run_part7_local.py baseline` chạy bộ baseline; chỉ chạy trước khi sửa KB. `fixed` chạy eval sau sửa. Chạy lại baseline sau sửa sẽ không tái tạo trạng thái KB cũ; cần dùng commit trước thay đổi KB hoặc đọc diff để khôi phục riêng hai entry trong bản checkout riêng. Không ghi đè số đo cũ để chọn mẫu đẹp.", "",
]
content = "\n".join(lines)
production = reports / "observability/production_report.md"
if production.exists():
    content = (content[:content.index("## 4. Observability stack")]
               + production.read_text(encoding="utf-8") + "\n"
               + content[content.index("## 6. Nhận xét"):])
(root / "BENCHMARK_REPORT.md").write_text(content, encoding="utf-8")
print("Wrote BENCHMARK_REPORT.md from measured JSON")
