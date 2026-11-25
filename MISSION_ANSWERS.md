# Mission Answers — Day 14

## Part 1 — Localhost vs Production

### Exercise 1.1 — Anti-patterns

Trong `develop/app.py`: (1) API key và database URL hardcode; (2) DEBUG/MAX_TOKENS cố định; (3) print thay logging có mức độ; (4) in secret ra log; (5) không có route /health; (6) bind localhost và cố định cổng 8000; (7) reload luôn bật. Các điểm này làm lộ thông tin, khó cấu hình cloud và thiếu tín hiệu giám sát. Uvicorn vẫn có xử lý shutdown mặc định, nhưng app chưa có cleanup tài nguyên riêng.

### Exercise 1.2 — Chạy develop

Người học cài dependencies trong venv Ubuntu WSL và chạy `python app.py`, sau đó:

```bash
curl -i -X POST "http://localhost:8000/ask?question=Hello"
```

Log thực tế xác nhận `POST /ask?question=Hello HTTP/1.1` trả `200 OK`; response mock: “Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.” Đồng thời log in API key giả, minh họa nguy cơ ghi secret. Bản production cũng đã được chạy và kiểm tra health/ask trả 200.

### Exercise 1.3 — So sánh develop và production

Đối chiếu `01-localhost-vs-production/develop/app.py`, `production/app.py` và `production/config.py`:

| Tiêu chí | Develop | Production | Tại sao quan trọng? |
| --- | --- | --- | --- |
| Cấu hình | Hardcode trong `app.py`. | Tập trung trong `config.py`, đọc bằng `os.getenv()`. | Đổi cấu hình giữa các môi trường mà không cần sửa code. |
| Secret | API key và thông tin database nằm trong code; key còn bị in ra log. | Key đọc từ biến môi trường; không in key trong phần xử lý request. | Giảm nguy cơ lộ thông tin bí mật qua GitHub và log. |
| Health check | Không có endpoint riêng. | Có `GET /health`, trả trạng thái, uptime, version và môi trường. | Giúp nền tảng kiểm tra ứng dụng còn hoạt động. |
| Readiness | Không có. | Có `GET /ready`, trả 200 khi `is_ready=True`, ngược lại trả 503. | Giúp xác định ứng dụng đã sẵn sàng nhận request chưa. |
| Logging | Dùng `print()`, thiếu mức độ log và có ghi secret. | Dùng `logging`, có mức độ log và các event request/response. | Dễ theo dõi và phân tích hoạt động. Cách lồng `json.dumps()` vào format hiện tại chưa đảm bảo JSON hợp lệ ở mọi dòng. |
| Shutdown | Không có logic cleanup riêng của ứng dụng. | Có phần cleanup trong `lifespan`; Uvicorn quản lý quá trình shutdown. | Cho phép bổ sung việc đóng kết nối và giải phóng tài nguyên khi tắt. |
| Host và port | Cố định `localhost:8000`. | Đọc `HOST`, `PORT` từ môi trường; mặc định `0.0.0.0:8000`. | Hỗ trợ chạy trong container và nhận cổng do nền tảng cloud cung cấp. |
| Reload | Luôn bật `reload=True`. | Bật/tắt theo `settings.debug`, mặc định tắt. | Tránh chạy cơ chế tự tải lại code trong production. |
| Kiểm tra cấu hình | Không có bước validation. | `validate()` báo lỗi nếu môi trường production thiếu `AGENT_API_KEY`. | Phát hiện cấu hình thiếu ngay khi khởi động. |

Lưu ý: việc yêu cầu `AGENT_API_KEY` trong cấu hình chưa phải là xác thực request. Endpoint `/ask` của bản production Part 1 chưa kiểm tra API key.

## Part 2 — Docker Containerization

### Exercise 2.1 — Đọc Dockerfile develop

Đối chiếu `02-docker/develop/Dockerfile`:

| Câu hỏi | Trả lời |
| --- | --- |
| Base image là gì? | `python:3.11`, cung cấp Python 3.11 và môi trường hệ điều hành để chạy ứng dụng. Đây là bản đầy đủ, không phải bản `slim`. |
| Working directory là gì? | `WORKDIR /app` đặt thư mục làm việc bên trong container là `/app`. Các lệnh `RUN`, `COPY` có đích tương đối và lệnh chạy ứng dụng phía sau sử dụng thư mục này. |
| Tại sao COPY requirements.txt trước? | Để tận dụng Docker layer cache. Khi chỉ thay đổi code nhưng không thay đổi `requirements.txt`, Docker có thể dùng lại layer cài dependencies thay vì chạy lại `pip install`, giúp build nhanh hơn. |
| CMD và ENTRYPOINT khác nhau thế nào? | `CMD` khai báo lệnh hoặc đối số mặc định; đối số truyền sau tên image có thể thay thế `CMD`. `ENTRYPOINT` khai báo chương trình chính; với dạng exec, đối số truyền khi chạy thường được nối vào chương trình này, và có thể thay chương trình bằng `--entrypoint`. Dockerfile này dùng `CMD ["python", "app.py"]` để mặc định chạy ứng dụng. |

Dockerfile dùng một stage. Các đường dẫn nguồn của `COPY` được tính từ build context ở gốc repo, vì vậy lệnh build cần chạy từ gốc repo:

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
```

### Exercise 2.2–2.3 — Build, chạy và so sánh image

Đã build hai image từ gốc repo:

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
docker images --filter "reference=my-agent:*"
```

Kết quả do người học chạy và cung cấp:

| Image | ID | DISK USAGE |
| --- | --- | --- |
| `my-agent:develop` | `2054e76fe90d` | 1.67 GB |
| `my-agent:advanced` | `74bf5ed488c4` | 240 MB |

Theo số hiển thị đã làm tròn, quy đổi 1.67 GB ≈ 1670 MB: mức giảm `(1670 - 240) / 1670 × 100 ≈ 85.6%`. Đây là so sánh chỉ số **DISK USAGE** từ cùng lệnh Docker, không phải dung lượng tải nén.

- Container develop: `POST /ask?question=What%20is%20Docker` trả `HTTP/1.1 200 OK`.
- Container production chạy với `ENVIRONMENT=production`: `GET /health` trả 200 theo log Uvicorn. Có hai worker khởi động, phù hợp với `--workers 2` trong Dockerfile.
- Stage `builder` cài công cụ build và dependencies. Stage `runtime` dùng base slim mới, copy thư viện đã cài và code cần chạy; không mang các công cụ build như gcc sang image cuối. Runtime chạy bằng user `appuser`.
- `HEALTHCHECK` đánh dấu trạng thái sức khỏe; tự nó không restart container khi unhealthy.

### Exercise 2.4 — Docker Compose

```text
Client → Nginx :80 → Agent :8000
                       ├→ Redis :6379 (dịch vụ được cấu hình cho cache/state)
                       └→ Qdrant :6333 (dịch vụ vector database)
```

Các service cùng tham gia mạng bridge `internal`, truy cập nhau bằng tên service. Agent nhận `REDIS_URL=redis://redis:6379/0` và `QDRANT_URL=http://qdrant:6333`; cấu hình này chưa chứng minh app mẫu thực sự sử dụng hai dịch vụ cho từng request. Redis và Qdrant có volume lưu dữ liệu. Agent đợi health check của Redis và Qdrant đạt trước khi khởi động. Chỉ Nginx publish cổng ra máy host. Cổng 443 được publish nhưng cần cấu hình chứng chỉ/listener để phục vụ HTTPS.

Đã tạo `.env.local` và chạy:

```bash
docker compose -p k5-day14-docker up -d --build
docker compose -p k5-day14-docker ps
```

Kết quả: 4 service `agent`, `nginx`, `qdrant`, `redis` đều Up; agent, Qdrant và Redis healthy. Thực tế có một container agent, không phải hai replica như comment đầu file. `target: runtime` vẫn build stage builder vì runtime phụ thuộc vào kết quả của nó.

Kiểm tra qua Nginx ngày 25/11/2026:

```bash
curl -i http://localhost/health
curl -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'
```

Cả hai trả `HTTP/1.1 200 OK`, header `Server: nginx`. Health trả `status: ok`, version `2.0.0`. Endpoint ask trả:

```json
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

## Part 3 — Cloud Deployment

Đã deploy agent Part 6 lên Railway cùng service Redis. URL public:

https://k5-l3a-day14-nguyenthuyduong-2a202603388-deploym-production.up.railway.app

Kiểm tra ngày 25/11/2026: health 200, ready 200, POST /ask thiếu key 401, đúng key 200. Chi tiết cấu hình và lệnh kiểm tra ở `DEPLOYMENT.md`. Đã lưu `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`. Còn cần bổ sung so sánh Railway/Render và mô tả pipeline Cloud Run để hoàn thiện hồ sơ Part 3.

### So sánh railway.toml và render.yaml — Exercise 3.2

Đối chiếu các file mẫu ở `03-cloud-deployment/`: Railway dùng TOML với các section `[build]`, `[deploy]`, khai báo builder NIXPACKS, startCommand dùng `$PORT`, healthcheck và chính sách restart cho service. Render dùng YAML với danh sách `services`, khai báo web service cùng Redis, region, plan, runtime Python, buildCommand/startCommand và envVars. Render minh họa `sync: false` để nhập secret qua dashboard và `generateValue: true` để tạo secret. Vì vậy hai file có cùng mục tiêu tự động hóa deploy nhưng khác schema, phạm vi khai báo tài nguyên và cách quản lý biến/secret. Bài làm Part 6 dùng Railway Dockerfile builder thay NIXPACKS của mẫu, Redis được tạo riêng trên dashboard rồi nối bằng variable reference. Không deploy thêm Render.

### Pipeline Cloud Run — Exercise 3.3

`cloudbuild.yaml` khai báo bước cài dependencies và chạy pytest, sau đó build Docker image gắn tag COMMIT_SHA/latest.
Bước push đẩy image lên Container Registry; bước deploy dùng gcloud run deploy tại asia-southeast1, đặt giới hạn instance, CPU/RAM và secret từ Secret Manager.
Các bước phụ thuộc tuần tự qua waitFor; trigger khi push cần được cấu hình bên ngoài file YAML.
`service.yaml` mô tả cấu hình service, concurrency 80, timeout 60 giây, scale 1–10 instance, env/secret và các probe.
Đây là phân tích code mẫu, không phải pipeline đã chạy thực tế. Bước test mẫu chưa có `set -e` và kết thúc bằng echo, nên khi áp dụng thật cần bảo đảm lỗi pytest làm bước build thất bại.

## Part 4 — API Security

### Exercise 4.1 — API key authentication

`APIKeyHeader` đọc header `X-API-Key`; dependency `verify_api_key()` được gắn vào `/ask` bằng `Depends`. Thiếu key trả 401; sai key trả 403 trong bản mẫu Part 4; đúng key mới xử lý câu hỏi. Muốn rotate key, thay biến môi trường `AGENT_API_KEY`, khởi động lại app và cập nhật client. Bản develop in key ra terminal khi khởi động, cần bỏ cách ghi log này khi dùng secret thật.

Đã chạy bản develop với key demo theo hướng dẫn lab. Log người học cung cấp:

```text
POST /ask HTTP/1.1 401 Unauthorized
POST /ask HTTP/1.1 200 OK
```

### Exercise 4.2–4.3 — JWT và rate limiting

Đã chạy bản production; gọi `POST /auth/token` với tài khoản demo `student` và nhận 200. Token được lưu trong biến shell `TOKEN`, không đưa vào bài. Request dùng header `Authorization: Bearer <token đã che>`.

Tài khoản student giới hạn 10 request/phút. Kết quả vòng lặp 12 request do người học chạy:

```text
Request 1: 200
Request 2: 200
Request 3: 200
Request 4: 200
Request 5: 200
Request 6: 200
Request 7: 200
Request 8: 200
Request 9: 200
Request 10: 200
Request 11: 429
Request 12: 429
```

### Exercise 4.4 — Cost guard

Theo `04-api-gateway/production/cost_guard.py`, mỗi user có `UsageRecord` cộng dồn input/output tokens và số request. Chi phí được tính bằng số token chia 1000 rồi nhân đơn giá input/output khai báo trong code. Đây là đơn giá của bài mẫu, không phải xác nhận giá dịch vụ hiện hành.

- Trước khi gọi LLM, `check_budget()` kiểm tra tổng chi phí toàn hệ thống và của user.
- Ngân sách mặc định: 1 USD/ngày/user và 10 USD tổng hệ thống; dùng từ 80% ngân sách user thì ghi cảnh báo.
- User đã dùng hết ngân sách bị chặn bằng HTTP 402; toàn hệ thống hết ngân sách bị chặn bằng HTTP 503 trong bản mẫu này.
- Sau khi LLM trả lời, `record_usage()` cộng token và chi phí vào state. Vì kiểm tra trước nhưng ghi chi phí sau, một request có thể làm chi phí vượt ngưỡng; code chưa đặt trước ngân sách cho các request đồng thời.
- State đang nằm trong RAM (`_records`, `_global_cost`), mất khi restart và không chia sẻ giữa worker/instance. Production cần state chung trong Redis/DB với cập nhật nguyên tử.
- Record user được tạo lại khi ngày thay đổi theo `time.strftime()` của process. `_global_today` được khai báo nhưng không dùng để reset `_global_cost`, nên code hiện tại chưa thực hiện reset ngân sách global mỗi ngày. Chuỗi thông báo “midnight UTC” cũng chưa được đảm bảo vì code dùng giờ hệ thống.

Rate limit giới hạn tốc độ request để giảm quá tải/lạm dụng; cost guard giới hạn tổng tiền sử dụng. Cần cả hai vì ít request nhưng mỗi request nhiều token vẫn có thể tốn nhiều tiền, còn request rẻ nhưng quá dồn dập vẫn gây quá tải.

Phạm vi kiểm chứng: Đã quan sát 401, 200 và 429 từ chạy thực tế. Các nhánh ngân sách 402/503 mới được đọc và phân tích code, chưa chạy thử tới ngưỡng; không khai là đã test thành công.

## Part 5 — Scaling & Reliability

### Health check, readiness và graceful shutdown

`/health` là liveness, cho biết process còn phản hồi; bản develop trả uptime, version, môi trường và thông tin bộ nhớ. `/ready` là readiness, dựa trên cờ `_is_ready` để quyết định instance có sẵn sàng nhận request không; khi cờ false thì trả 503. Bản develop chưa thực sự ping database trong readiness. Mất dependency không nhất thiết có nghĩa process chết: Part 6 yêu cầu health vẫn 200 nhưng ready phải 503 khi Redis không kết nối được.

Đã chạy bản develop; log người học cung cấp xác nhận:

```text
GET /health HTTP/1.1 200 OK
GET /ready HTTP/1.1 200 OK
```

Đã gửi `kill -SIGTERM 3965` từ terminal Ubuntu khác. Log:

```text
INFO:     Shutting down
INFO:     Waiting for application shutdown.
2026-11-25 10:14:37,533 INFO 🔄 Graceful shutdown initiated...
2026-11-25 10:14:37,534 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [3965]
```

Quan sát được cleanup khi nhận SIGTERM. Chưa gửi SIGTERM trong lúc có request đang xử lý, nên chưa kết luận từ phép thử này rằng request đang chạy được hoàn thành. SIGTERM cho phép ứng dụng xử lý tín hiệu và cleanup; SIGKILL không thể bị ứng dụng bắt để cleanup.

### Stateless scaling với Redis — Exercise 5.4–5.5

Chạy từ `05-scaling-reliability/production/`:

```bash
touch .env.local
docker compose -p k5-day14-scaling up -d --build --scale agent=3
python -m pip install -r requirements.txt
python test_stateless.py
```

Stack khởi động 3 agent, Nginx và Redis. Kết quả thực tế do người học cung cấp:

| Request | Instance |
| --- | --- |
| 1 | `instance-f17dce` |
| 2 | `instance-d2cd50` |
| 3 | `instance-eb90e4` |
| 4 | `instance-f17dce` |
| 5 | `instance-d2cd50` |

```text
Total requests: 5
Instances used: {'instance-f17dce', 'instance-d2cd50', 'instance-eb90e4'}
✅ All requests served despite different instances!
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

Cả 5 request trong cùng session đi qua 3 instance khác nhau, nhưng history vẫn đủ 10 message (5 câu hỏi và 5 câu trả lời). Nginx phân phối request; Redis giữ history dùng chung, giúp agent không phụ thuộc state trong RAM của một instance. Nếu history chỉ nằm trong RAM, instance tiếp theo có thể không biết các lượt hội thoại đã xử lý ở instance trước.

Script không tự tắt instance nào. Kết quả này kiểm tra chia sẻ history giữa nhiều instance đang chạy; chưa kiểm chứng failover khi một instance bị dừng hoặc độ bền dữ liệu khi Redis bị mất.

## Part 6 — Final Project

Ngày 25/11/2026, chạy trong `06-lab-complete/` bằng Python 3.11.18 trên WSL2, Docker 29.9.3:

```bash
python check_production_ready.py
```

Phần Checklist Deliverable từ output người học cung cấp:

```text
📋 Checklist Deliverable
   ✅ Dockerfile (multi-stage, < 500 MB)
   ✅ docker-compose.yml (agent + redis)
   ✅ .dockerignore
   ✅ Health check endpoint (GET /health)
   ✅ Readiness endpoint (GET /ready)
   ✅ API Key authentication
   ✅ Rate limiting
   ✅ Cost guard
   ✅ Config từ environment variables
   ✅ Structured logging
   ✅ Graceful shutdown
   ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
Result: 12/12 tiêu chí đạt · 41/41 checks passed
🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
```

Số đo trong lần chạy này: build image 21 giây; dung lượng image theo script 273 MB; `docker stop` exit code 0 trong 0.6 giây. Runtime hai worker: rate limit trả 429 sau 5 request và vẫn 429 sau restart; mất Redis thì ready 503 nhưng health 200; SIGTERM khi request đang xử lý vẫn hoàn thành 200, process thoát code 0; 14 dòng log app là JSON hợp lệ.

Giới hạn: mục Public URL ready của lần chạy này chỉ kiểm tra file cấu hình Railway và PORT. Chưa deploy cloud, chưa có public URL; phần Deployment của bài vẫn cần hoàn thành tại CP6.

## AI log

### Hỗ trợ hoàn thiện Part 1, Part 3 và chạy Part 7

- Hỏi: Nhờ AI thực hiện phần bài còn lại sau khi hoàn thành ảnh deploy.
- Nhận: AI bổ sung Exercise 1.1–1.2 theo code và kết quả người học đã cung cấp; so sánh file cấu hình Railway/Render và mô tả pipeline Cloud Run từ repo. AI viết script điều phối chạy nguyên bản load_test.py/run_eval.py, tạo bảng báo cáo từ JSON thực đo và workflow CI quality gate.
- Thực hiện bằng công cụ: Python 3.11.18 trong WSL, 7 load test × 300 request; eval v1 1/23, v2 ban đầu 21/23. AI chỉ bổ sung hai entry JWT/HPA vào KNOWLEDGE_BASE (develop và production), restart v2 và eval lại 23/23, không regression. Golden dataset và script chấm không sửa.
- Minh bạch: Các lần load test FAIL SLO được giữ nguyên; eval tắt lỗi upstream để tách chất lượng khỏi lỗi ngẫu nhiên. Console log và JSON nằm trong reports/. Các phép chạy Part 7 này do AI thực hiện qua công cụ, không khai là người học tự chạy. Người học cần đọc lại, chạy lại khi cần và giải thích được các kết quả.
- Trạng thái: Phần local đã kiểm tra; stack production và hồ sơ Part 7 tiếp tục được cập nhật dưới đây.

### Part 7 — Observability, lỗi triển khai và hiệu chỉnh phép đo

- AI sửa Dockerfile mẫu Part 7: home user agent phải là /home/agent để tìm được packages trong /home/agent/.local. Sau sửa, agent chạy và promtool test rules báo SUCCESS.
- Hai lượt Locust đầu bị compose run tự đưa topology về 2 agent dù trước đó đã up --scale 1 hoặc 3. AI phát hiện qua ps/log, loại các lượt này khỏi so sánh 1-vs-3, giữ nguyên bằng chứng trong reports/observability/discarded_two_instances. Script được sửa thêm --no-deps và kiểm tra số agent trước/sau; chạy lại là để sửa phép đo sai topology, không phải chọn số đẹp.
- Thí nghiệm chaos A+B thực tế trên 2 agent: error rate 0.2, slow rate 0.3, 30 users. AgentHighErrorRate được quan sát firing sau 103.9 giây; AgentHighLatencyP95 sau 164 giây, cùng firing trong alerts_firing.json. Poll 10 giây; số này tính từ lúc bắt đầu áp dụng cấu hình, không phải độ trễ chính xác tới mili giây.
- Jaeger API cũ trả 404; AI chuyển sang API v3 theo tài liệu Jaeger, lưu raw trace và chọn trace có log cùng trace_id. Bằng chứng nằm trong reports/observability/slow_trace.json, error_trace.json và trace_summary.json. Dùng truy vấn bổ sung duration >=1s để tìm tail latency.
- Công cụ trình duyệt báo browser access host unavailable, nên chưa chụp được bốn ảnh Part 7. Không dùng ảnh dựng hoặc khai ảnh đã có.

### Hỗ trợ Part 3 — Railway

- Hỏi: Nhờ AI hướng dẫn deploy và kiểm tra public URL.
- Nhận: Hướng dẫn kết nối GitHub, root directory, Redis và biến môi trường; chẩn đoán REDIS_URL sai và ký tự điều khiển trong header; AI tạo DEPLOYMENT.md từ kết quả thực tế.
- Tự kiểm tra: Người học thao tác Railway, xác nhận Active/Online; chạy curl health 200 và ask đúng key 200. AI kiểm tra URL public nhận health 200, ready 200 và ask thiếu key 401. Không đưa key hoặc URL Redis chứa mật khẩu vào repo.

### Hỗ trợ Part 6 — Kiểm tra đầy đủ

- Người học chạy `python check_production_ready.py` nguyên bản trong WSL2, môi trường Python 3.11.18, và cung cấp output PASS 12/12, 41/41 checks passed ngày 25/11/2026.
- AI ghi lại checklist và số đo từ output vào mục Part 6. Không sửa script chấm. Public URL thực tế chưa được kiểm tra hoặc triển khai trong bước này.

### Hỗ trợ Part 6 — Đóng gói và cấu hình deploy

- Hỏi: Tiếp tục sau kết quả kiểm tra --skip-docker.
- Nhận: AI viết Dockerfile hai stage python:3.11-slim, copy virtualenv, chạy non-root, healthcheck theo PORT và exec uvicorn làm PID 1; Compose agent + Redis với volume/AOF; .dockerignore loại secret/cache/venv và Part 7; railway.toml dùng Dockerfile và /health. Chưa deploy cloud.
- Tự kiểm tra đã thực hiện: Người học chạy script nguyên bản --skip-docker, nhận 7/12 và 25/35 checks passed. Runtime health, readiness, auth, rate limit (gồm restart), cost guard, env, JSON logging đều đạt; SIGTERM đang có request vẫn 200 và process thoát code 0. Phần Docker stop chưa kiểm tra.
- Chờ kiểm chứng: Build và kiểm tra đầy đủ sau thay đổi đóng gói; chưa khẳng định image <500 MB hay PASS 12/12.

### Hỗ trợ Part 6 — Graceful shutdown

- Hỏi: Tiếp tục thêm graceful shutdown sau khi dừng server.
- Nhận: AI thêm FastAPI lifespan, log startup/shutdown bằng JSON và đóng Redis client ở cleanup; giữ signal handler mặc định của Uvicorn để server chờ request đang chạy trước cleanup.
- Kiểm chứng: Chưa có phép thử SIGTERM trong lúc request chạy hoặc docker stop cho Part 6; cần script đầy đủ để xác nhận. Người học đã cung cấp một log request /health dạng JSON hợp lệ trước bước này.

### Hỗ trợ Part 6 — Structured logging

- Hỏi: Tiếp tục sửa structured logging sau khi dừng server.
- Nhận: AI thêm JsonFormatter dùng json.dumps, handler riêng không propagate để tránh log trùng; ghi event logging_initialized và request gồm method, route, HTTP status, thời gian ms. Không ghi API key, header hoặc nội dung câu hỏi.
- Kiểm chứng: Chờ người học chạy app và cung cấp log mới. Log Uvicorn thuộc server, không được tính là log app trong tiêu chí này.
- Bổ sung kiểm chứng cost guard: Người học cung cấp log POST /ask trả 402 với DAILY_BUDGET_USD=0. Chưa kiểm tra cộng dồn tới ngưỡng với ngân sách dương.

### Hỗ trợ Part 6 — Cost guard

- Hỏi: Tiếp tục hoàn thiện cost_guard.py từ bản khung.
- Nhận: AI thêm kiểm tra ngân sách trước LLM, cộng chi phí theo token ước tính sau LLM; dùng Redis INCRBYFLOAT trong transaction cùng TTL và key theo ngày UTC. Hết ngân sách trả 402, lỗi Redis trả 503. Đơn giá giữ theo mock của đề.
- Giới hạn: Check trước và ghi sau chưa đặt trước ngân sách cho request đồng thời, nên có thể vượt ngưỡng bởi các request đã được chấp nhận. Token là ước tính theo số từ vì mock chỉ trả chuỗi. Chờ kiểm tra thực tế; chưa ghi nhận PASS tiêu chí cost guard.

### Hỗ trợ Part 6 — Cấu hình môi trường

- Hỏi: Nhờ AI sửa cấu hình Part 6 theo hướng dẫn đọc biến môi trường.
- Nhận: AI sửa `06-lab-complete/app/config.py` để đọc PORT, ENVIRONMENT, AGENT_API_KEY, REDIS_URL, RATE_LIMIT_PER_MINUTE và DAILY_BUDGET_USD; bổ sung các biến trong `.env.example`, để trống API key; dùng python-dotenv hỗ trợ file .env.
- Kiểm chứng: Người học chạy với PORT=8123 và RATE_LIMIT_PER_MINUTE=7, nhận `8123 7`, xác nhận hai giá trị được đọc từ môi trường. Chưa kết luận tiêu chí 9 hoặc Part 6 đạt đầy đủ. Người học đã tự thêm /health và cung cấp log GET /health trả 200 trước bước này.

### Hỗ trợ Part 6 — API key

- Hỏi: Tiếp tục hoàn thiện authentication từ bản khung auth.py.
- Nhận: AI triển khai APIKeyHeader, so sánh key bằng secrets.compare_digest, trả 401 khi thiếu/sai key hoặc server chưa có key; nối dependency vào /ask. /health không yêu cầu key.
- Kiểm chứng: Người học cung cấp log POST /ask: thiếu key 401, sai key 401, đúng key 200. Chưa xác nhận tiêu chí authentication bằng script chấm đầy đủ.

### Hỗ trợ Part 6 — Redis và readiness

- Hỏi: Tiếp tục hoàn thiện Redis client và readiness từ bản khung.
- Nhận: AI tạo Redis client dùng REDIS_URL, không ping lúc import, đặt timeout kết nối/đọc 1 giây; redis_healthy() bắt RedisError và trả False. Thêm /ready trả 503 khi Redis không phản hồi và 200 khi ping thành công; /health vẫn độc lập Redis.
- Kiểm chứng: Người học cung cấp log khi không có Redis ở cổng 6399: health 200 và ready 503. Sau khi bật container Redis tại cổng 6399, ready trả 200.

### Hỗ trợ Part 6 — Rate limiting

- Hỏi: Tiếp tục hoàn thiện rate_limiter.py từ bản khung.
- Nhận: AI triển khai sliding window 60 giây bằng Redis sorted set và Lua để xóa bản ghi cũ, kiểm tra và thêm request nguyên tử; dùng Redis TIME, member UUID và TTL. Key được băm SHA-256 trước khi dùng làm tên Redis key. Nối check_rate_limit vào /ask; vượt giới hạn trả 429 kèm Retry-After, lỗi Redis trả 503.
- Kiểm chứng: Chờ người học chạy vòng lặp và thử restart agent trong cùng cửa sổ 60 giây; chưa ghi nhận PASS tiêu chí này.

- Hỏi: Nhờ AI hỗ trợ lập và điền bảng so sánh develop/production của Part 1 vào file bài làm.
- Nhận: Bảng so sánh dựa trên hai file `app.py` và `production/config.py`; AI tạo file và điền mục Exercise 1.3 cùng AI log.
- Tự kiểm tra đã thực hiện: Đọc code bằng `cat`; chạy hai phiên bản bằng `python app.py`; gọi `POST /ask?question=Hello` của develop và quan sát log trả 200; gọi `GET /health` của production và quan sát log trả 200.
- Phạm vi kiểm chứng: Chưa có kết quả kiểm tra graceful shutdown khi đang xử lý request hoặc kiểm chứng toàn bộ log là JSON hợp lệ. Chưa ghi nhận thay đổi code ứng dụng trong quá trình hỗ trợ Part 1.

### Hỗ trợ Part 2 — Exercise 2.1

- Hỏi: Nhờ AI giải thích Dockerfile develop và điền bốn câu trả lời Exercise 2.1 vào bài.
- Nhận: Giải thích base image, working directory, layer cache, sự khác nhau giữa CMD và ENTRYPOINT; AI điền câu trả lời vào file này.
- Tự kiểm tra đã thực hiện: Đọc `02-docker/develop/Dockerfile` bằng `cat` và gửi nội dung để đối chiếu.
- Kiểm chứng tiếp theo do người học thực hiện: Build/run hai image, cung cấp output dung lượng, log health check, trạng thái bốn service Compose và output curl qua Nginx. AI hỗ trợ giải thích multi-stage/Compose, tính mức giảm xấp xỉ 85.6% và ghi các kết quả được cung cấp vào bài; không tự tạo số đo.

### Hỗ trợ Part 4 — API Security

- Hỏi: Nhờ AI hướng dẫn chạy API key/JWT/rate limit và giải thích cost guard.
- Nhận: Lệnh chạy, lệnh lấy token và vòng lặp kiểm tra rate limit; phân tích cost guard dựa trên code; AI điền kết quả vào Part 4.
- Tự kiểm tra đã thực hiện: Cài dependencies, chạy develop và production; quan sát 401 khi thiếu key, 200 khi có key, lấy token thành công; chạy 12 request cho kết quả 10 mã 200 và 2 mã 429; đọc cost_guard.py bằng cat.
- Chưa kiểm chứng bằng chạy thực tế: Nhánh vượt ngân sách 402/503 và reset ngân sách theo ngày. Không sửa code ứng dụng trong bước này.

### Hỗ trợ Part 5 — Scaling & Reliability

- Hỏi: Nhờ AI giải thích health/readiness/shutdown và hướng dẫn chạy stack 3 instance cùng bài kiểm tra stateless.
- Nhận: Lệnh cài/chạy, kiểm tra HTTP, gửi SIGTERM, bật Compose với tên project riêng và chạy test_stateless.py; AI ghi kết quả được cung cấp vào Part 5.
- Tự kiểm tra đã thực hiện: Đọc app.py; chạy develop, gọi health/ready đạt 200, gửi SIGTERM và quan sát shutdown; chạy stack 3 agent và test_stateless.py, xác nhận 5 request qua 3 instance và 10 message history.
- Phạm vi kiểm chứng: Chưa thử dừng instance khi có tải hoặc gửi SIGTERM trong lúc có request; không tự tạo số đo và không sửa code ứng dụng trong bước hỗ trợ này.
