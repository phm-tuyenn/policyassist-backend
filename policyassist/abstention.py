import re

from .retrieval import RetrievalHit


TAX_ID_QUESTION = re.compile(
    r"\bmã số thuế\b[^,.;?!\n]{0,60}\b"
    r"(?:chính thức|đăng ký|bao nhiêu|là gì|là bao nhiêu)\b",
    re.IGNORECASE,
)
SUPPLIER_QUESTION = re.compile(
    r"\b(?:nhà cung cấp|đơn vị cung cấp|nhà thầu)\b"
    r".{0,100}\b(?:cụ thể|công ty nào|đơn vị nào|tên gì|là ai)\b",
    re.IGNORECASE,
)
AUDIT_STATUS_QUESTION = re.compile(
    r"\b(?:đang|hiện|có đang)\b.{0,80}\b(?:thanh tra|kiểm tra)\b",
    re.IGNORECASE,
)
EXCHANGE_RATE_QUESTION = re.compile(r"\b(?:tỷ giá|exchange rate)\b", re.IGNORECASE)
PERSONAL_DATA_QUESTION = re.compile(
    r"\b(?:số điện thoại|địa chỉ email|email cá nhân|số căn cước|cccd)\b",
    re.IGNORECASE,
)
TAX_ID_VALUE = re.compile(r"\bmã số thuế\b.{0,100}\b\d{10,13}\b", re.IGNORECASE)
SUPPLIER_IDENTITY = re.compile(
    r"\b(?:nhà cung cấp|đơn vị cung cấp|nhà thầu)\b"
    r".{0,100}\b(?:là|:)\s*(?!dịch vụ\b|bên bán\b)"
    r"(?:công ty|tập đoàn|doanh nghiệp)\s+[A-ZÀ-Ỹ]",
    re.IGNORECASE,
)
AUDIT_STATUS_VALUE = re.compile(
    r"\b(?:đang|hiện)\s+(?:bị\s+)?(?:thanh tra|kiểm tra)\b"
    r"|\bkhông\s+(?:bị\s+)?(?:thanh tra|kiểm tra)\b",
    re.IGNORECASE,
)
EXCHANGE_RATE_VALUE = re.compile(
    r"\b(?:USD\s*/\s*VND|tỷ giá)\b.{0,50}\b\d[\d.,]*\b"
    r"|\b\d[\d.,]*\b.{0,50}\b(?:USD\s*/\s*VND|tỷ giá)\b",
    re.IGNORECASE,
)
PERSONAL_DATA_VALUE = re.compile(
    r"\b(?:\+?84|0)\d{8,10}\b"
    r"|\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"
    r"|\b\d{12}\b",
    re.IGNORECASE,
)


def missing_record_evidence(question: str, hits: list[RetrievalHit]) -> bool:
    """Reject requests for specific records unless retrieved evidence contains the value."""
    texts = [hit.chunk["chunk_text"] for hit in hits]
    checks = (
        (TAX_ID_QUESTION, TAX_ID_VALUE),
        (SUPPLIER_QUESTION, SUPPLIER_IDENTITY),
        (AUDIT_STATUS_QUESTION, AUDIT_STATUS_VALUE),
        (EXCHANGE_RATE_QUESTION, EXCHANGE_RATE_VALUE),
        (PERSONAL_DATA_QUESTION, PERSONAL_DATA_VALUE),
    )
    for question_pattern, evidence_pattern in checks:
        if question_pattern.search(question) and not any(
            evidence_pattern.search(text) for text in texts
        ):
            return True
    return False
