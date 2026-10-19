# PolicyAssist AI (Python)

MVP tra cứu chính sách từ Data Pack: lọc theo ngày hiệu lực, BM25 hoặc hybrid BM25 + embeddings, trích dẫn từ citation map, có chế độ từ chối, và xuất CSV theo template.

## License

Phần mềm trong thư mục này do `phm-tuyenn` phát hành theo GNU General Public License v3.0; xem [LICENSE](./LICENSE). License này không bao gồm corpus Data Pack được đóng gói trong `data/` hoặc các tài liệu nguồn bên ngoài thư mục dự án; quyền sử dụng các dữ liệu/tài liệu đó tuân theo điều khoản riêng của chủ sở hữu tương ứng.

Mặc định chương trình dùng BM25, không cần API key hoặc tải mô hình embedding. Có thể bật hybrid retrieval và LLM bằng các tham số riêng.

## 1. Cài đặt

Mở PowerShell tại thư mục `policyassist_python`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Nếu chính sách PowerShell không cho kích hoạt virtual environment, chạy lệnh qua đường dẫn đầy đủ:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. Chạy bộ câu hỏi mẫu

Từ thư mục `policyassist_python`:

```powershell
python run.py
```

Mặc định:

- Đọc chunks, metadata và citation map từ thư mục Data Pack cha.
- Đọc `04_questions/questions_sample.csv`.
- Ghi kết quả vào `policyassist_python/output/submission.csv`.
- Dùng BM25 và câu trả lời trích xuất từ các chunk được truy xuất.

Nếu cần bật hybrid embeddings hoặc gọi LLM, cài dependencies bổ sung riêng:

```powershell
python -m pip install -r requirements-optional.txt
```

Chỉ định đường dẫn khác:

```powershell
python run.py --data-dir "C:\path\to\DataPack" --questions "C:\path\to\questions.csv" --output "C:\path\to\submission.csv"
```

## 3. HTTP API cho UI

Cài dependencies, rồi khởi động API từ thư mục `policyassist_python`:

```powershell
python -m pip install -r requirements.txt
uvicorn api:app --host 127.0.0.1 --port 8000
```

Hướng dẫn endpoint, request/response mẫu, tích hợp JavaScript và xử lý lỗi nằm trong [API_GUIDE.md](./API_GUIDE.md).

- Kiểm tra dịch vụ: `GET http://127.0.0.1:8000/health`
- Hỏi đáp: `POST http://127.0.0.1:8000/ask`
- Trang tài liệu và playground: `http://127.0.0.1:8000/`
- Swagger UI: `http://127.0.0.1:8000/docs`

Ví dụ body:

```json
{
  "question": "Chứng từ kế toán được hiểu là gì?",
  "reference_date": "2026-10-17",
  "top_k": 5
}
```

Phản hồi gồm `answer`, `citations`, `sources`, các ID tài liệu/chunk, `confidence`, `abstain` và `latency_ms`. `reference_date` không bắt buộc; mặc định là `2026-10-17`. `top_k` từ 1 đến 10. API chạy BM25 cục bộ, không cần API key.

Ví dụ gọi từ JavaScript:

```javascript
const response = await fetch("http://127.0.0.1:8000/ask", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    question: "Chứng từ kế toán được hiểu là gì?",
    reference_date: "2026-10-17"
  })
});
const result = await response.json();
```

Trong JavaScript, cần dùng `JSON.stringify(...)` cho `body`. Không đưa object trực tiếp vào `body` và không tự ghép chuỗi JSON.

CORS cho phép mặc định các origin localhost cổng 3000, 5173 và 8080. Để cấu hình origin frontend khác, đặt danh sách origin phân cách dấu phẩy trước khi khởi động:

```powershell
$env:POLICYASSIST_CORS_ORIGINS = "http://localhost:4200"
```

## 4. Hybrid retrieval (BM25 + embedding)

```powershell
python run.py --retrieval hybrid --embedding-model intfloat/multilingual-e5-base
```

Lần chạy đầu có thể cần tải model embedding. Có thể thay bằng model đa ngôn ngữ tương thích với `sentence-transformers`. Với model E5, chương trình tự thêm tiền tố `query:` và `passage:`.

BM25 phù hợp tìm từ khóa, mã điều khoản và cụm từ chính xác; bộ tokenizer loại một số từ dừng tiếng Việt và từ chung như “Data Pack”. Embeddings giúp tìm các cách diễn đạt tương tự. Kết quả được gộp bằng Reciprocal Rank Fusion (RRF). Tất cả thứ hạng được tính sau khi lọc theo `reference_date`.

## 5. Bật LLM tùy chọn

Chế độ mặc định là extractive: câu trả lời được ghép từ chính nội dung đã truy xuất. Để tạo câu trả lời tự nhiên hơn, cấu hình biến môi trường `OPENAI_API_KEY` rồi chạy:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
python run.py --llm --model gpt-4o-mini
```

Nếu dùng endpoint tương thích OpenAI, có thể cấu hình `$env:OPENAI_BASE_URL`. Không ghi API key vào mã nguồn hoặc file được commit. LLM chỉ được cung cấp các chunk đã truy xuất; citation vẫn được xác nhận từ citation map và chunk IDs, không lấy citation tự do từ mô hình.

## 6. Chỉnh ngưỡng từ chối

`--min-confidence` nhận giá trị từ `0` đến `1`, mặc định `0.18`:

```powershell
python run.py --min-confidence 0.22
```

Confidence hiện là điểm căn cứ retrieval có tính heuristic, chưa phải xác suất đã hiệu chuẩn. Hệ thống cũng từ chối các yêu cầu về hồ sơ thực tế cụ thể (ví dụ mã số thuế, danh tính nhà cung cấp, trạng thái thanh tra, tỷ giá hoặc dữ liệu cá nhân) nếu nội dung bằng chứng không có giá trị được hỏi. Các quy tắc này là hàng rào an toàn theo loại dữ liệu, không thay thế đánh giá chuyên môn. Hãy đánh giá và hiệu chỉnh trên `answer_key_sample.csv`; đặc biệt theo dõi Unsupported Answer Rate và Abstention Quality. Có thể dùng `--top-k` để thay đổi số chunk trả về cho phần trả lời (mặc định 5).

## 7. Đánh giá retrieval

```powershell
python evaluate.py
```

Đánh giá Recall@5 trên các câu hỏi có trong answer key. Đây là chỉ số retrieval, không thay thế đánh giá độ đúng câu trả lời, độ chính xác citation, versioning hoặc abstention.

## 8. Kiểm thử

```powershell
python -m unittest discover -s tests -v
```

Các bài kiểm thử không cần tải model embedding hoặc gọi LLM.

## 9. Logic và giới hạn

- Thời điểm truy vấn lấy từ cột `reference_date`; nếu bỏ trống mới dùng `--default-reference-date` (mặc định `2026-10-17`, ngày snapshot trong Data Pack).
- `effective_from` và `effective_to` của chunk được ưu tiên; nếu thiếu thì dùng ngày hiệu lực/hết hiệu lực trong metadata. Trạng thái `REPLACED` không tự loại chunk, vì các câu hỏi lịch sử vẫn cần dùng văn bản cũ đúng thời điểm.
- RRF kết hợp BM25 và embeddings. Nguồn pháp luật được ưu tiên nhẹ khi điểm tương đương; loại văn bản và nội dung liên quan vẫn cần quyết định kết quả truy xuất, để câu hỏi quy trình nội bộ không bị lấn át bởi văn bản luật không liên quan.
- Câu trả lời extractive có thể chưa trôi chảy; bật LLM sau khi đã kiểm tra retrieval.
- Chương trình không thể đảm bảo chất lượng pháp lý độc lập với Data Pack. Nội dung `NORMALIZED_SUMMARY` là nội dung tóm tắt/chuẩn hóa, không phải bản nguyên văn luật; tài liệu `SIMULATED_INTERNAL` là giả lập.

## 10. Deploy API lên Vercel

Project có cấu hình entrypoint trong `pyproject.toml`, phiên bản Python trong `.python-version` và bản corpus nhỏ gọn trong `data/`. Từ thư mục `policyassist_python`, chạy:

Deployment production hiện tại: [https://policyassist-backend.vercel.app](https://policyassist-backend.vercel.app). Trang UI/docs ở `/`, API hỏi đáp ở `/ask`, health ở `/health` và Swagger ở `/docs`.

```powershell
npm install --global vercel
vercel login
vercel
```

Làm theo CLI để liên kết project và tạo preview. Khi preview chạy đúng, deploy production:

```powershell
vercel --prod
```

Trang docs/playground nằm ở URL gốc deployment; API tại `/health`, `/ask` và `/docs`. Dependencies mặc định không cài PyTorch, sentence-transformers hoặc SDK LLM để giảm kích thước gói function.

`data/` chứa bản deploy của các CSV cần thiết. Khi cập nhật Data Pack, đồng bộ:

- `03_metadata/legal_chunks.csv` → `data/03_metadata/legal_chunks.csv`
- `03_metadata/document_metadata.csv` → `data/03_metadata/document_metadata.csv`
- `citation_map.csv` → `data/citation_map.csv`

Vercel chạy theo dạng serverless function, có thể tạo process mới giữa các request; không dùng bộ nhớ ứng dụng để lưu hội thoại. Kiểm tra giới hạn runtime của Vercel trước khi public và không đưa dữ liệu nhạy cảm vào deployment.
