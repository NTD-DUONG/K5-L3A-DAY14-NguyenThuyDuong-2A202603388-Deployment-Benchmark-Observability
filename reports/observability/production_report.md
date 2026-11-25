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

Người học đã chụp và lưu bốn ảnh từ giao diện thật trong phiên tải capture bổ sung, cùng cấu hình chaos 2 agent. Ảnh Alerts thấy error-rate, latency và cost alert cùng firing. Capture bổ sung phục vụ ảnh minh chứng; thời gian tới firing ở mục 4.2 vẫn lấy từ lượt đo chaos ban đầu.

- [x] [Grafana dashboard](screenshots/grafana-dashboard.png) — dashboard khi Locust đang có tải.
- [x] [Jaeger slow trace](screenshots/jaeger-slow-trace.png) — trace chậm ở link trên.
- [x] [Jaeger error trace](screenshots/jaeger-error-trace.png) — trace lỗi, mở event exception.
- [x] [Prometheus Alerts](screenshots/prometheus-alert-firing.png) — cùng lúc ít nhất hai alert firing.

## 5. Benchmark scaling

Locust headless: 100 users, ramp 10 users/s, 2 phút mỗi topology. Chờ DNS 15 giây sau thay đổi instance. Dùng compose run --no-deps và kiểm tra số agent trước/sau để giữ đúng 1 hoặc 3 instance. Hai lượt ban đầu bị Compose tự đưa về 2 instance đã được loại khỏi bảng, giữ ở reports/observability/discarded_two_instances. Mock mặc định error 0.01, slow 0.03, model small, KB đã sửa. Mỗi agent giới hạn 0.5 CPU/256 MB theo Compose. Bảng lấy riêng dòng POST /ask trong CSV cuối, gồm cả response lỗi; JSON load_test.py ở mục 2 chỉ thống kê latency thành công nên không so sánh trực tiếp như cùng một phép đo.

| Instances | RPS /ask | p50 ms | p95 ms | p99 ms | Failures / Requests | Error rate |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 59.342 | 200 | 270 | 1700 | 78/7100 | 1.10% |
| 3 | 60.001 | 190 | 230 | 1700 | 75/7175 | 1.05% |

RPS /ask với 3 instance bằng 1.011 lần 1 instance. Không kỳ vọng gấp ba: Locust cố định 100 users và mỗi user nghỉ 0.5–2 giây; mock LLM còn latency/tail được cấu hình riêng cho từng request, scale không làm mỗi lần gọi LLM nhanh hơn. Vì đây là mock async trên một máy, kết quả không chứng minh khả năng scale của provider LLM thật. Phân biệt tăng thông lượng xử lý với giảm tail latency cho mỗi request.
