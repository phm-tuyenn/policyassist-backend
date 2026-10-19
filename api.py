import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from policyassist.abstention import missing_record_evidence
from policyassist.answering import generate_answer, validate_supporting_citations
from policyassist.data import load_corpus
from policyassist.retrieval import RetrievalEngine


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = APP_DIR.parent
DEPLOYED_DATA_DIR = APP_DIR / "data"
DEFAULT_REFERENCE_DATE = date(2026, 10, 17)
ABSTAIN_ANSWER = "Không đủ căn cứ trong Data Pack để xác định thông tin này."


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=2000)
    reference_date: date = Field(default=DEFAULT_REFERENCE_DATE)
    top_k: int = Field(default=5, ge=1, le=10)


class SourceResult(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    source_type: str
    citation: str
    source_url: str | None
    excerpt: str


class AskResponse(BaseModel):
    question: str
    reference_date: date
    answer: str
    citations: list[str]
    retrieved_document_ids: list[str]
    retrieved_chunk_ids: list[str]
    sources: list[SourceResult]
    confidence: float = Field(ge=0, le=1)
    abstain: bool
    latency_ms: int = Field(ge=0)


def _allowed_origins() -> list[str]:
    configured = os.getenv("POLICYASSIST_CORS_ORIGINS", "")
    if configured.strip():
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    default_data_dir = DEPLOYED_DATA_DIR if DEPLOYED_DATA_DIR.is_dir() else DEFAULT_DATA_DIR
    data_dir = Path(os.getenv("POLICYASSIST_DATA_DIR", str(default_data_dir))).resolve()
    chunks, _ = load_corpus(data_dir)
    mode = os.getenv("POLICYASSIST_RETRIEVAL", "bm25").strip().lower()
    if mode not in {"bm25", "hybrid"}:
        raise ValueError("POLICYASSIST_RETRIEVAL phải là 'bm25' hoặc 'hybrid'")
    model = os.getenv("POLICYASSIST_EMBEDDING_MODEL", "intfloat/multilingual-e5-base")
    engine = RetrievalEngine(chunks, mode=mode, embedding_model=model)
    app.state.retrieval_engine = engine
    app.state.min_confidence = float(os.getenv("POLICYASSIST_MIN_CONFIDENCE", "0.18"))
    if not 0 <= app.state.min_confidence <= 1:
        raise ValueError("POLICYASSIST_MIN_CONFIDENCE phải nằm trong khoảng 0..1")
    app.state.data_dir = data_dir
    yield


app = FastAPI(
    title="PolicyAssist API",
    description="API tra cứu chính sách với nguồn dẫn, versioning và cơ chế từ chối.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = exc.errors()
    if any(error.get("type") == "json_invalid" for error in errors):
        return JSONResponse(
            status_code=422,
            content={
                "detail": (
                    "Request body không phải JSON hợp lệ. "
                    "Hãy dùng dấu ngoặc kép cho tên thuộc tính và chuỗi; "
                    "trong JavaScript, truyền body: JSON.stringify(data)."
                )
            },
        )
    return JSONResponse(status_code=422, content={"detail": errors})


@app.get("/health")
def health(request: Request) -> dict[str, Any]:
    engine = getattr(request.app.state, "retrieval_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Retrieval engine chưa khởi tạo")
    return {
        "status": "ok",
        "retrieval": engine.mode,
        "chunks": len(engine.chunks),
    }


@app.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest, request: Request) -> AskResponse:
    engine: RetrievalEngine = request.app.state.retrieval_engine
    started = perf_counter()
    try:
        hits, confidence = engine.retrieve(
            payload.question,
            payload.reference_date,
            top_k=payload.top_k,
        )
        abstain = (
            not hits
            or confidence < request.app.state.min_confidence
            or missing_record_evidence(payload.question, hits)
        )
        answer_text = ABSTAIN_ANSWER
        supporting_hits = []
        citations: list[str] = []
        if hits and not abstain:
            generated = generate_answer(payload.question, hits)
            hit_by_id = {hit.chunk["chunk_id"]: hit for hit in hits}
            supporting_hits = [
                hit_by_id[chunk_id] for chunk_id in generated.supporting_chunk_ids
            ]
            citations = validate_supporting_citations(generated, supporting_hits)
            if not supporting_hits:
                abstain = True
            else:
                answer_text = generated.answer

        sources = [
            SourceResult(
                chunk_id=hit.chunk["chunk_id"],
                document_id=hit.chunk["document_id"],
                document_title=hit.chunk["document_title"],
                source_type=hit.chunk["source_type"],
                citation=hit.chunk["citation_label"],
                source_url=hit.chunk.get("source_url") or None,
                excerpt=hit.chunk["chunk_text"],
            )
            for hit in supporting_hits
        ]
        document_ids = list(dict.fromkeys(
            hit.chunk["document_id"] for hit in supporting_hits
        ))
        chunk_ids = [hit.chunk["chunk_id"] for hit in supporting_hits]
        if abstain:
            answer_text = ABSTAIN_ANSWER
            citations = []
            sources = []
            document_ids = []
            chunk_ids = []
            if not hits:
                confidence = 0.0

        return AskResponse(
            question=payload.question,
            reference_date=payload.reference_date,
            answer=answer_text,
            citations=citations,
            retrieved_document_ids=document_ids,
            retrieved_chunk_ids=chunk_ids,
            sources=sources,
            confidence=confidence,
            abstain=abstain,
            latency_ms=round((perf_counter() - started) * 1000),
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


app.mount(
    "/",
    StaticFiles(directory=APP_DIR / "static", html=True),
    name="site",
)
