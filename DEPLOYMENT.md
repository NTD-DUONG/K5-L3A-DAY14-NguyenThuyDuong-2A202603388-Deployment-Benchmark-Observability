# Deployment Information

## Public URL

https://k5-l3a-day14-nguyenthuyduong-2a202603388-deploym-production.up.railway.app

## Platform

Railway, project `lovely-radiance`, environment `production`. Agent deploy từ GitHub branch `main`, Root Directory `/06-lab-complete`, Dockerfile multi-stage. Redis là service riêng trong cùng project, có volume. Deployment hiển thị Active/Online sau khi sửa tham chiếu REDIS_URL.

## Environment Variables Set

- `ENVIRONMENT=production`
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`
- `AGENT_API_KEY`: đặt riêng trên Railway, không lưu giá trị vào repo.
- `REDIS_URL`: tham chiếu `${{Redis.REDIS_URL}}`, không lưu URL chứa mật khẩu vào repo.
- `PORT`: Railway cấp; Docker CMD đọc biến này. Public domain được cấu hình target port 8080.

## Test Commands

Chạy bằng Bash/Ubuntu. Nhập key đúng đã đặt trên Railway, không in key ra màn hình:

```bash
BASE=https://k5-l3a-day14-nguyenthuyduong-2a202603388-deploym-production.up.railway.app
read -r -s -p "API key: " AGENT_API_KEY; echo
curl --http1.1 -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
curl --http1.1 -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
curl --http1.1 -sS -o /dev/null -w '%{http_code}\n' "$BASE/ask" -H 'Content-Type: application/json' --data-raw '{"question":"Hello"}'
curl --http1.1 -sS -o /dev/null -w '%{http_code}\n' "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" --data-raw '{"question":"Hello"}'
```

Kết quả kiểm tra ngày 25/11/2026:

| Phép thử | Kết quả thực tế |
| --- | --- |
| GET /health | 200, `{"status":"ok"}` |
| GET /ready | 200, `{"ready":true}` |
| POST /ask không key | 401, Missing or invalid API key |
| POST /ask đúng key | 200; người học chạy curl và cung cấp mã HTTP |

Ba phép thử đầu được AI gọi URL public kiểm chứng; phép thử đúng key được người học thực hiện riêng trong WSL. Key không được chia sẻ cho AI.

## Troubleshooting

- Crash khi startup: REDIS_URL sai định dạng; đã sửa bằng tham chiếu tới REDIS_URL của service Redis.
- HTTP 400 từ proxy khi gửi header: biến key trên terminal chứa ký tự điều khiển; sau khi loại bỏ ký tự điều khiển và nhập đúng key, request trả 200.
- Dùng `--http1.1` trong các lệnh kiểm tra sau khi kết nối curl ban đầu gặp lỗi.

## Screenshots

Đã lưu đủ ba file ảnh vào repo:

- [Deployment dashboard](screenshots/dashboard.png): project có agent và Redis.
- [Service running](screenshots/running.png): deployment Active/Online.
- [Test results](screenshots/test.png): bốn kết quả HTTP 200, 200, 401, 200, không hiện secret.
