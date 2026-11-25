# Benchmark & Observability Report — Day 14

**Họ tên:** NguyenThuyDuong (theo tên repo)
**Ngày chạy:** 25/11/2026 (GMT+7)
**Môi trường:** Windows + Ubuntu WSL2, Python 3.11.18; WSL báo 8 CPU logic, MemTotal 7.997.660 kB (~7,63 GiB). Docker Desktop. Agent local chạy trong WSL; benchmark production chạy qua Docker.

## 1. SLO của agent

| SLI | SLO | Lý do |
| --- | --- | --- |
| p95 /ask | ≤500 ms | Ngưỡng mặc định load_test.py, theo dõi phần lớn trải nghiệm thay vì chỉ average. |
| Error rate /ask | ≤2% | Ngưỡng mặc định; mock có xác suất lỗi 1%, vẫn giữ khoảng dung sai. |
| Accuracy | ≥85% cho CI; 100% sau sửa KB | CI chặn chất lượng thấp; bài yêu cầu v2 cuối đạt 23/23, không regression. |

## 2. Benchmark hiệu năng local

Mỗi lần chạy 300 request; mock mặc định latency 120 ms, jitter 60 ms, retrieval 20 ms, slow thêm 1500 ms, error rate 0.01. Các load test chạy trên KB ban đầu. Không lặp lại để chọn kết quả đẹp. Image Docker đang được tải trong nền trong quá trình benchmark local, nên có thể gây nhiễu tài nguyên; đây là số đo trên laptop, không phải công suất cloud. Latency JSON chỉ tính các request HTTP 200; error rate tính toàn bộ request.

### 2.1 Concurrency vs latency

| Concurrency | RPS | p50 ms | p95 ms | p99 ms | Error rate | SLO |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 4.08 | 190.9 | 225.8 | 1701.5 | 1.33% | PASS |
| 10 | 36.38 | 193.3 | 229.5 | 1706.3 | 0.33% | PASS |
| 50 | 103.19 | 214.8 | 303.4 | 444.8 | 2.33% | FAIL |
| 100 | 80.65 | 316.5 | 1880.4 | 2020.8 | 1.33% | FAIL |

RPS không tăng tuyến tính: client/server cùng chia sẻ CPU, event loop, kết nối và chi phí xử lý/log; request slow giữ slot lâu hơn. 300 request là mẫu nhỏ, số lỗi ngẫu nhiên có thể vượt ngưỡng dù cấu hình lỗi chỉ 1%. Các lần FAIL được giữ nguyên.

### 2.2 Tail latency

Cùng concurrency 20 và 300 request, restart agent cho mỗi slow rate.

| MOCK_SLOW_RATE | avg ms | p95 ms | p99 ms |
| --- | --- | --- | --- |
| 0 | 215.8 | 333.0 | 424.7 |
| 0.03 | 261.8 | 296.8 | 1702.2 |
| 0.1 | 357.7 | 1704.8 | 1730.9 |

p99 nhạy với số ít request chậm; khi slow rate lên 10%, p95 cũng rơi vào nhóm chậm. Average trộn phần lớn request nhanh với phần nhỏ request slow, nên có thể che giấu trải nghiệm tệ của nhóm cuối. Với mẫu 300 và ngẫu nhiên, percentile không nhất thiết đơn điệu giữa mọi lần chạy.

## 3. Benchmark chất lượng

Eval tắt lỗi upstream (`MOCK_ERROR_RATE=0`) để tách chất lượng khỏi lỗi ngẫu nhiên; slow rate vẫn 0.03. Golden dataset và script eval giữ nguyên.

| Chỉ số | v1 | v2 ban đầu | v2 sau sửa |
| --- | --- | --- | --- |
| Accuracy | 1/23 (4.35%) | 21/23 (91.30%) | 23/23 (100.00%) |
| Avg tokens/câu | 57.4 | 108.8 | 113.7 |
| Tổng cost USD | 0.000409 | 0.000757 | 0.00079 |
| Cost/câu đúng USD | 0.00040875 | 3.607e-05 | 3.436e-05 |
| Latency p95 ms | 193.6 | 214.5 | 218.2 |
| Quality gate | FAIL | PASS | PASS |

| Câu sai ban đầu | Keyword thiếu | Sửa KB |
| --- | --- | --- |
| security-02 | token, hết hạn, chữ ký | Bổ sung tài liệu phân biệt API key cố định và JWT có chữ ký, expiration. |
| scaling-03 | cpu, memory, custom metrics | Bổ sung tài liệu Kubernetes HPA dùng CPU, memory và custom metrics. |

Đã sửa cùng hai entry trong mock_llm.py bản develop và production. Eval cuối so với baseline v2: 2 câu được sửa, 0 regression, quality gate 100% PASS. v2 dùng retrieval nên prompt/token và chi phí mỗi câu tăng, nhưng chi phí mỗi câu đúng giảm rõ rệt so với v1. Chi phí là số mô phỏng từ mock, không phải hóa đơn LLM thật.

Workflow `.github/workflows/eval.yml` chạy agent v2 rồi eval với --min-accuracy 0.85; exit code 1 làm job fail. Để thực sự chặn merge cần bật required status check trong branch protection trên GitHub; chưa thay đổi cài đặt này và chưa khẳng định workflow đã chạy trên GitHub.

## 4. Observability stack

Stack chạy local: Nginx :8080, Prometheus :9090, Grafana :3000, Jaeger :16686, Locust :8089. Image agent được sửa home của user từ /app sang /home/agent để Python tìm đúng packages đã copy sang /home/agent/.local; không đổi instrumentation, alert rule hay dataset.

### 4.1 Golden Signals và Exercise 7.4

Snapshot Prometheus dưới đây được thu trong thí nghiệm chaos; không phải số đo baseline Locust.

- Traffic /ask: 13.891 req/s; error rate: 12.57%.
- Avg latency: 408.7 ms; p95: 1816.3 ms; p99: 1963.3 ms. Percentile này ước tính từ histogram Prometheus, không phải percentile raw của Locust.
- Tải theo instance:

| Instance | /ask req/s |
| --- | --- |
| 172.18.0.6:8000 | 7.018 |
| 172.18.0.8:8000 | 6.873 |

Các instance có lưu lượng là bằng chứng Nginx phân phối request. Chênh lệch ngắn hạn có thể đến từ số user hữu hạn, độ trễ ngẫu nhiên và scrape window; không yêu cầu mỗi giây bằng nhau tuyệt đối.

| Token type | tokens/s |
| --- | --- |
| input | 938.309 |
| output | 488.927 |

Input tokens gồm system prompt, câu hỏi và context retrieval nên có thể lớn hơn output của câu trả lời ngắn. GET http://localhost:8080/metrics thực tế trả 404; Nginx chặn endpoint vận hành từ bên ngoài, Prometheus scrape trực tiếp các agent trong mạng Docker.

### 4.2 Alerts và chaos

promtool test rules với alert_rules_test.yml: SUCCESS (xem reports/observability/alert_rules_test.log).

Đã thực hiện đồng thời hai fault injection A+B: MOCK_ERROR_RATE=0.2, MOCK_SLOW_RATE=0.3; thực tế 2 agent, Locust 30 users, ramp 5 users/s (compose run đã đưa topology về deploy.replicas=2). Thời gian tính từ trước lệnh Compose áp dụng cấu hình tới lần poll đầu thấy firing; poll mỗi 10 giây nên đây là thời gian quan sát, không phải timestamp chuyển trạng thái chính xác. Hai tác động được bật cùng nhau, không suy diễn là hai phép đo cách ly.

| Thí nghiệm | Alert | Thời gian quan sát tới firing | Panel |
| --- | --- | --- | --- |
| A: error rate 0.2 | AgentHighErrorRate | 103.9 s | Error rate |
| B: slow rate 0.3 | AgentHighLatencyP95 | 164.0 s | p95/p99 latency |

Hai alert cùng firing đã được lưu trong alerts_firing.json. Các thí nghiệm model lớn, pause instance và đổi v1 không được thực hiện trong lượt đo này. Nếu đổi v1 làm chất lượng giảm mà latency/error hạ tầng vẫn tốt, cần golden-dataset eval trước deploy và đánh giá chất lượng định kỳ/sampling trên traffic thực; dashboard xanh không chứng minh câu trả lời đúng.

### 4.3 Trace và log correlation

Trace được lấy bằng API v3 của Jaeger và giữ nguyên OTLP JSON; tham khảo [tài liệu API chính thức](https://www.jaegertracing.io/docs/2.23/architecture/apis/). Phân tích span chỉ là dữ liệu dẫn xuất từ timestamp/duration gốc.

**Trace chậm:** [e84484847ee7873e3e2b603bafeb549b](http://localhost:16686/trace/e84484847ee7873e3e2b603bafeb549b)

Tổng 1876.519 ms; span `chat mock-llm-small` 1660.421 ms, chiếm 88.48%. Đây là trace chậm nhất trong tập kết quả truy vấn có log đối chiếu, gồm truy vấn lọc duration >=1s; không khẳng định chậm nhất toàn bộ lịch sử.

Dòng log JSON có cùng trace_id:

```json
{"ts": "2026-11-25T14:42:10.903041+00:00", "level": "INFO", "service": "observable-agent", "instance": "c3b7603d97f6", "event": "llm_call", "trace_id": "e84484847ee7873e3e2b603bafeb549b", "span_id": "e4259350e14a4ac6", "request_id": "84c1c32610cb", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1660.1}
```

**Trace lỗi:** [2c3a1355ee01aba6fa11800cd6eb10c4](http://localhost:16686/trace/2c3a1355ee01aba6fa11800cd6eb10c4)

Tổng 117.318 ms; span `chat mock-llm-small` 92.968 ms, chiếm 79.24%. Span lỗi có exception được ghi bởi OpenTelemetry; kiểm tra dữ liệu gốc ở error_trace.json.

Dòng log JSON có cùng trace_id:

```json
{"ts": "2026-11-25T14:42:17.206763+00:00", "level": "INFO", "service": "observable-agent", "instance": "c3b7603d97f6", "event": "llm_error", "trace_id": "2c3a1355ee01aba6fa11800cd6eb10c4", "span_id": "870ea65e60c4cc07", "request_id": "7ad1f7e90645", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

### 4.4 Ảnh minh chứng

Cần chụp từ giao diện thật. Công cụ trình duyệt báo host unavailable nên AI chưa lưu được bốn ảnh dưới đây; không thay thế bằng ảnh dựng lại từ số liệu.

- [ ] screenshots/grafana-dashboard.png — dashboard khi Locust đang có tải.
- [ ] screenshots/jaeger-slow-trace.png — trace chậm ở link trên.
- [ ] screenshots/jaeger-error-trace.png — trace lỗi, mở event exception.
- [ ] screenshots/prometheus-alert-firing.png — cùng lúc hai alert firing.

## 5. Benchmark scaling

Locust headless: 100 users, ramp 10 users/s, 2 phút mỗi topology. Chờ DNS 15 giây sau thay đổi instance. Dùng compose run --no-deps và kiểm tra số agent trước/sau để giữ đúng 1 hoặc 3 instance. Hai lượt ban đầu bị Compose tự đưa về 2 instance đã được loại khỏi bảng, giữ ở reports/observability/discarded_two_instances. Mock mặc định error 0.01, slow 0.03, model small, KB đã sửa. Mỗi agent giới hạn 0.5 CPU/256 MB theo Compose. Bảng lấy riêng dòng POST /ask trong CSV cuối, gồm cả response lỗi; JSON load_test.py ở mục 2 chỉ thống kê latency thành công nên không so sánh trực tiếp như cùng một phép đo.

| Instances | RPS /ask | p50 ms | p95 ms | p99 ms | Failures / Requests | Error rate |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 59.342 | 200 | 270 | 1700 | 78/7100 | 1.10% |
| 3 | 60.001 | 190 | 230 | 1700 | 75/7175 | 1.05% |

RPS /ask với 3 instance bằng 1.011 lần 1 instance. Không kỳ vọng gấp ba: Locust cố định 100 users và mỗi user nghỉ 0.5–2 giây; mock LLM còn latency/tail được cấu hình riêng cho từng request, scale không làm mỗi lần gọi LLM nhanh hơn. Vì đây là mock async trên một máy, kết quả không chứng minh khả năng scale của provider LLM thật. Phân biệt tăng thông lượng xử lý với giảm tail latency cho mỗi request.

## 6. Nhận xét

1. Latency tốt chưa chứng minh câu trả lời đúng: v1 cần eval để phát hiện chất lượng thấp.
2. Percentile và error rate phải đọc cùng nhau; mock lỗi và tail latency là hai yếu tố khác nhau.
3. CI cần dùng dataset cố định, baseline và exit code để ngăn regression; không sửa đáp án để nâng điểm.

Nếu vận hành thật, cần thêm metric/error ở Nginx hoặc synthetic check vì lỗi 504 có thể không xuất hiện ở metric của agent; thêm quality eval định kỳ, token/cost theo model và kiểm soát cardinality.

## Bằng chứng và tái lập

JSON và console log trong `reports/`. Script `scripts/run_part7_local.py baseline` chạy bộ baseline; chỉ chạy trước khi sửa KB. `fixed` chạy eval sau sửa. Chạy lại baseline sau sửa sẽ không tái tạo trạng thái KB cũ; cần dùng commit trước thay đổi KB hoặc đọc diff để khôi phục riêng hai entry trong bản checkout riêng. Không ghi đè số đo cũ để chọn mẫu đẹp.
