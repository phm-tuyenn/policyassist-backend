# PolicyAssist API — Hướng dẫn tích hợp

API này cung cấp giao diện HTTP để ứng dụng frontend gửi câu hỏi và nhận câu trả lời cùng nguồn dẫn. Chế độ mặc định chạy BM25 cục bộ trên Data Pack, không cần API key hoặc dịch vụ LLM.

## 1. Khởi động

Mở PowerShell tại thư mục `policyassist_python`:

```powershell
python -m pip install -r requirements.txt
uvicorn api:app --host 127.0.0.1 --port 8000
```

Giữ cửa sổ PowerShell này mở khi sử dụng API. Nếu chạy trên máy phát triển của bạn, `127.0.0.1` giới hạn dịch vụ vào máy đó.

| Mục đích | URL |
|---|---|
| Trang tài liệu và playground | `http://127.0.0.1:8000/` |
| Kiểm tra trạng thái | `GET http://127.0.0.1:8000/health` |
| Hỏi đáp | `POST http://127.0.0.1:8000/ask` |
| Giao diện thử API | `http://127.0.0.1:8000/docs` |

Trang gốc (`/`) có hướng dẫn endpoint, ví dụ gọi API và form thử hỏi đáp trực tiếp. `/docs` vẫn là Swagger UI tự sinh từ schema của FastAPI.

### Deploy trên Vercel

Từ thư mục `policyassist_python`, cài Vercel CLI, đăng nhập và liên kết project:

```powershell
npm install --global vercel
vercel login
vercel
```

Sau khi kiểm tra preview deployment, tạo production deployment bằng `vercel --prod`. Cấu hình entrypoint, Python runtime và bản corpus dành cho deployment đã nằm trong thư mục này. Các URL `/`, `/health`, `/ask` và `/docs` tiếp tục được phục vụ trên domain Vercel.

## 2. Endpoint `GET /health`

Request:

```http
GET /health
```

Phản hồi mẫu:

```json
{
  "status": "ok",
  "retrieval": "bm25",
  "chunks": 374
}
```

Nếu corpus không tải được, server sẽ không khởi động thành công. Endpoint này xác nhận ứng dụng đã tải retrieval engine và số lượng chunks.

## 3. Endpoint `POST /ask`

Header bắt buộc:

```http
Content-Type: application/json
```

Body:

```json
{
  "question": "Chứng từ kế toán được hiểu là gì?",
  "reference_date": "2026-10-17",
  "top_k": 5
}
```

Trường request:

| Trường | Bắt buộc | Kiểu | Quy tắc |
|---|---:|---|---|
| `question` | Có | chuỗi | 1–2000 ký tự, không được để trống |
| `reference_date` | Không | ngày `YYYY-MM-DD` | Mặc định `2026-10-17`, ngày snapshot của Data Pack |
| `top_k` | Không | số nguyên | Từ 1 đến 10, mặc định 5 |

Phản hồi thành công mẫu:

```json
{
  "question": "Chứng từ kế toán được hiểu là gì?",
  "reference_date": "2026-10-17",
  "answer": "Chứng từ kế toán là giấy tờ hoặc vật mang tin phản ánh nghiệp vụ kinh tế, tài chính đã phát sinh và hoàn thành, được dùng làm căn cứ ghi sổ kế toán. (LAW01 – Điều 3 khoản 3)",
  "citations": [
    "LAW01 – Điều 3 khoản 3"
  ],
  "retrieved_document_ids": [
    "LAW01"
  ],
  "retrieved_chunk_ids": [
    "LAW01_C001"
  ],
  "sources": [
    {
      "chunk_id": "LAW01_C001",
      "document_id": "LAW01",
      "document_title": "Luật Kế toán số 88/2015/QH13",
      "source_type": "LEGAL",
      "citation": "LAW01 – Điều 3 khoản 3",
      "source_url": null,
      "excerpt": "Nội dung chunk được trích từ Data Pack."
    }
  ],
  "confidence": 0.68,
  "abstain": false,
  "latency_ms": 2
}
```

Các giá trị confidence và latency trong ví dụ chỉ minh họa; kết quả thực tế phụ thuộc lần chạy. `sources` chứa nội dung trích từ Data Pack và metadata nguồn. Nếu không đủ căn cứ, API trả câu từ chối, `abstain: true` và các mảng citations/chunks/sources rỗng.

## 4. Gọi từ giao diện JavaScript

```javascript
async function askPolicy(question, referenceDate = "2026-10-17") {
  const response = await fetch("http://127.0.0.1:8000/ask", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      question,
      reference_date: referenceDate,
      top_k: 5
    })
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(
      typeof result.detail === "string"
        ? result.detail
        : JSON.stringify(result.detail)
    );
  }
  return result;
}

askPolicy("Chứng từ kế toán được hiểu là gì?")
  .then(result => console.log(result.answer, result.citations))
  .catch(error => console.error(error));
```

**Quan trọng:** `fetch` cần nhận một chuỗi JSON ở `body`, vì vậy hãy gọi `JSON.stringify(object)`. Không truyền object trực tiếp, không tự ghép JSON bằng template string và không viết JSON với dấu nháy đơn.

## 5. Gọi bằng PowerShell

```powershell
$body = @{
  question = "Chứng từ kế toán được hiểu là gì?"
  reference_date = "2026-10-17"
  top_k = 5
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/ask" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body
```

Hoặc kiểm tra nhanh bằng `curl.exe`:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/ask" `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"Chứng từ kế toán được hiểu là gì?\",\"reference_date\":\"2026-10-17\",\"top_k\":5}"
```

## 6. Lỗi HTTP 422 — JSON không hợp lệ

Lỗi bạn gặp:

```text
Expecting property name enclosed in double quotes
```

nghĩa là server chưa đọc được JSON body, chưa phải lỗi retrieval hay Data Pack. JSON yêu cầu tên thuộc tính và chuỗi dùng dấu ngoặc kép `"`:

```json
{"question": "Chứng từ kế toán được hiểu là gì?", "reference_date": "2026-10-17"}
```

Ví dụ sai — key `reference_date` không có dấu ngoặc kép:

```text
{"question": "Câu hỏi", reference_date: "2026-10-17"}
```

Một lỗi thường gặp khác khi gọi bằng JavaScript là:

```javascript
body: { question: "Câu hỏi" } // Sai: body phải là chuỗi hoặc dữ liệu dạng stream
```

Hãy đổi thành:

```javascript
body: JSON.stringify({ question: "Câu hỏi" })
```

Server vẫn trả HTTP `422` cho JSON sai cú pháp, nhưng nội dung lỗi đã được chỉnh để chỉ rõ cần dùng dấu ngoặc kép và `JSON.stringify(data)`. Các lỗi kiểm tra trường request cũng trả `422`, ví dụ câu hỏi rỗng, ngày sai định dạng hoặc `top_k` ngoài khoảng 1–10.

## 7. Lỗi CORS khi frontend chạy ở cổng khác

Mặc định API cho phép frontend ở `localhost`/`127.0.0.1` cổng `3000`, `5173` và `8080`. Nếu frontend chạy cổng khác, đặt origin chính xác trước khi khởi động API:

```powershell
$env:POLICYASSIST_CORS_ORIGINS = "http://localhost:4200"
uvicorn api:app --host 127.0.0.1 --port 8000
```

Nhiều origin có thể cách nhau bằng dấu phẩy. Origin gồm scheme, hostname và port, không kèm đường dẫn như `/dashboard`.

## 8. Cấu hình tùy chọn

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `POLICYASSIST_DATA_DIR` | Thư mục Data Pack cha của app | Đường dẫn đến Data Pack |
| `POLICYASSIST_RETRIEVAL` | `bm25` | `bm25` hoặc `hybrid` |
| `POLICYASSIST_EMBEDDING_MODEL` | `intfloat/multilingual-e5-base` | Model dùng khi bật hybrid |
| `POLICYASSIST_MIN_CONFIDENCE` | `0.18` | Ngưỡng confidence để từ chối |
| `POLICYASSIST_CORS_ORIGINS` | Các origin localhost thường dùng | Origin frontend được phép, phân cách dấu phẩy |

Mặc định không cần LLM và không gọi dịch vụ AI trả phí.

## 9. Lưu ý triển khai

- API hiện không có xác thực người dùng; chỉ chạy trong máy/mạng phát triển đáng tin cậy. Không mở trực tiếp ra Internet nếu chưa bổ sung xác thực, giới hạn truy cập và HTTPS.
- Không đặt API key bí mật trong frontend. Cấu hình CORS không phải cơ chế xác thực.
- `confidence` là điểm heuristic từ retrieval, không phải xác suất hiệu chuẩn.
- Kết quả căn cứ vào Data Pack; tài liệu `SIMULATED_INTERNAL` là giả lập và `NORMALIZED_SUMMARY` không phải nguyên văn văn bản pháp luật.
- Phần mềm được cấp phép theo GPL-3.0; corpus Data Pack không thuộc license phần mềm này. Xem [README](./README.md#license) và [LICENSE](./LICENSE).
