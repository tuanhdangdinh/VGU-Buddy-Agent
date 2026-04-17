"""
RAG pipeline: loads PDFs from data/handbooks/ and builds a FAISS vector store.
Falls back to built-in VGU demo content when no PDFs are present.
"""
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "handbooks"
FAISS_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "faiss_cache"
EMBEDDING_MODEL = "models/gemini-embedding-001"

_vectorstore: FAISS | None = None
_vectorstore_ready = False

# Built-in VGU knowledge base used when no PDF handbooks are loaded
_DEMO_DOCS = [
    Document(
        page_content=(
            "VGU (Đại học Việt-Đức) là trường đại học theo mô hình Đức tại Việt Nam, "
            "thành lập năm 2008. VGU cung cấp các chương trình đào tạo kỹ thuật và khoa "
            "học ứng dụng theo tiêu chuẩn giáo dục Đức. Các ngành: Khoa học Máy tính, "
            "Kỹ thuật Điện tử, Kỹ thuật Xây dựng, Quản trị Kinh doanh."
        ),
        metadata={"source": "vgu_overview"},
    ),
    Document(
        page_content=(
            "Quy chế học tập VGU: Sinh viên cần đạt GPA tối thiểu 2.0/4.0 để tiếp tục học. "
            "Mỗi học kỳ có 2 kỳ thi: giữa kỳ (midterm) và cuối kỳ (final). "
            "Điểm tổng kết = 30% midterm + 70% final. "
            "Sinh viên cần tích lũy đủ tín chỉ theo kế hoạch học tập."
        ),
        metadata={"source": "academic_regulations"},
    ),
    Document(
        page_content=(
            "Thủ tục hành chính VGU: Đăng ký môn học qua portal sinh viên. "
            "Thời gian đăng ký: 2 tuần trước khi học kỳ bắt đầu. "
            "Rút môn: trong 2 tuần đầu học kỳ, không bị ghi điểm F. "
            "Nghỉ học có phép: thông báo giảng viên và nộp đơn xin phép."
        ),
        metadata={"source": "admin_procedures"},
    ),
    Document(
        page_content=(
            "Học bổng VGU: Học bổng xuất sắc cho sinh viên GPA >= 3.5. "
            "Học bổng hỗ trợ cho sinh viên có hoàn cảnh khó khăn. "
            "Học bổng DAAD cho sinh viên trao đổi sang Đức. "
            "Deadline nộp hồ sơ: thường vào tháng 10 hàng năm."
        ),
        metadata={"source": "scholarships"},
    ),
    Document(
        page_content=(
            "Chương trình Khoa học Máy tính VGU: "
            "Môn cơ sở: Lập trình C/C++, Cấu trúc dữ liệu & Giải thuật, Toán rời rạc, Đại số tuyến tính. "
            "Môn chuyên ngành: Machine Learning, Cloud Computing, Software Engineering, Database Systems. "
            "Chuẩn đầu ra: Tiếng Anh B2 CEFR, 140 tín chỉ, đồ án tốt nghiệp."
        ),
        metadata={"source": "cs_curriculum"},
    ),
    Document(
        page_content=(
            "Ký túc xá VGU: Có ký túc xá dành cho sinh viên với đầy đủ tiện nghi. "
            "Phòng đôi và phòng đơn có sẵn. Đăng ký ký túc xá vào đầu năm học. "
            "Có wifi, giặt sấy công cộng, khu vực học tập chung 24/7."
        ),
        metadata={"source": "dormitory"},
    ),
    Document(
        page_content=(
            "Hoạt động sinh viên VGU: CLB học thuật (Robotics, AI, Programming), "
            "CLB thể thao, CLB văn nghệ. "
            "Hội sinh viên VGU tổ chức các sự kiện học thuật và giao lưu văn hóa. "
            "VGU Day hàng năm là sự kiện lớn nhất của trường."
        ),
        metadata={"source": "student_activities"},
    ),
    Document(
        page_content=(
            "Lịch học VGU: Năm học chia thành 2 học kỳ chính (Winter và Summer semester). "
            "Winter semester: tháng 9 – tháng 1. Summer semester: tháng 3 – tháng 7. "
            "Kỳ thi cuối kỳ thường diễn ra vào cuối tháng 1 và tháng 7."
        ),
        metadata={"source": "academic_calendar"},
    ),
    Document(
        page_content=(
            "Thư viện VGU: Mở cửa từ 8h–20h các ngày trong tuần. "
            "Có hơn 10,000 đầu sách và tài liệu kỹ thuật. "
            "Sinh viên được mượn tối đa 5 cuốn sách trong 2 tuần. "
            "Truy cập online vào cơ sở dữ liệu IEEE, Springer, Elsevier."
        ),
        metadata={"source": "library"},
    ),
    Document(
        page_content=(
            "Phòng thí nghiệm VGU: Lab máy tính mở cửa 24/7 cho sinh viên. "
            "Lab điện tử, lab cơ khí, lab xây dựng được trang bị hiện đại. "
            "Sinh viên cần đăng ký trước khi sử dụng lab chuyên dụng. "
            "Có phòng maker space cho các dự án sáng tạo."
        ),
        metadata={"source": "laboratories"},
    ),
]


def _get_embeddings() -> GoogleGenerativeAIEmbeddings:
    from ..config import settings
    return GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL,
        google_api_key=settings.gemini_api_key,
    )


def _load_file(path: Path) -> List[Document]:
    """Load a single PDF or Markdown file into LangChain Documents."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            from langchain_community.document_loaders import PyPDFLoader
            return PyPDFLoader(str(path)).load()
        elif suffix in (".md", ".markdown"):
            from langchain_community.document_loaders import TextLoader
            return TextLoader(str(path), encoding="utf-8").load()
    except Exception as exc:
        logger.warning(f"Failed to load {path.name}: {exc}")
    return []


def _source_fingerprint() -> str:
    """Hash of all handbook filenames + sizes + mtimes. Changes when docs are added/modified."""
    entries = []
    if DATA_DIR.exists():
        for f in sorted(DATA_DIR.glob("*")):
            if f.suffix.lower() in (".pdf", ".md", ".markdown"):
                stat = f.stat()
                entries.append(f"{f.name}:{stat.st_size}:{stat.st_mtime}")
    return hashlib.md5("|".join(entries).encode()).hexdigest()


def _cached_fingerprint() -> str:
    fp_file = FAISS_CACHE_DIR / "fingerprint.json"
    if fp_file.exists():
        return json.loads(fp_file.read_text()).get("fingerprint", "")
    return ""


def _save_fingerprint(fp: str) -> None:
    (FAISS_CACHE_DIR / "fingerprint.json").write_text(json.dumps({"fingerprint": fp}))


def build_vectorstore() -> None:
    global _vectorstore, _vectorstore_ready
    embeddings = _get_embeddings()

    # Load from disk cache if fingerprint matches — avoids re-embedding on every restart
    current_fp = _source_fingerprint()
    if FAISS_CACHE_DIR.exists() and _cached_fingerprint() == current_fp:
        try:
            _vectorstore = FAISS.load_local(
                str(FAISS_CACHE_DIR), embeddings, allow_dangerous_deserialization=True
            )
            _vectorstore_ready = True
            logger.info("Vectorstore loaded from disk cache")
            return
        except Exception as e:
            logger.warning(f"Cache load failed, rebuilding: {e}")
    else:
        logger.info("Document fingerprint changed — rebuilding vectorstore")

    docs: List[Document] = list(_DEMO_DOCS)
    logger.info("Building vectorstore from handbook sources")

    if DATA_DIR.exists():
        supported = list(DATA_DIR.glob("*.pdf")) + \
                    list(DATA_DIR.glob("*.md")) + \
                    list(DATA_DIR.glob("*.markdown"))
        for file_path in supported:
            loaded = _load_file(file_path)
            if loaded:
                docs.extend(loaded)
                logger.info(f"Loaded {file_path.suffix} handbook: {file_path.name} ({len(loaded)} pages/sections)")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = splitter.split_documents(docs)

    # Build FAISS in batches — free-tier Gemini embedding is ~5 RPM
    BATCH = 40
    _vectorstore = None
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i:i + BATCH]
        for attempt in range(4):
            try:
                if _vectorstore is None:
                    _vectorstore = FAISS.from_documents(batch, embeddings)
                else:
                    _vectorstore.add_documents(batch)
                break
            except Exception as e:
                if "429" in str(e) and attempt < 3:
                    wait = 15 * (attempt + 1)
                    logger.warning(f"Rate limited, retrying in {wait}s (attempt {attempt + 1})")
                    time.sleep(wait)
                else:
                    raise
        if i + BATCH < len(chunks):
            time.sleep(12)

    FAISS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _vectorstore.save_local(str(FAISS_CACHE_DIR))
    _save_fingerprint(current_fp)
    logger.info(f"Vectorstore saved to cache — {len(chunks)} chunks from {len(docs)} documents")

    _vectorstore_ready = True
    logger.info(f"Vectorstore ready — {len(chunks)} chunks from {len(docs)} documents")


def is_vectorstore_ready() -> bool:
    return _vectorstore_ready and _vectorstore is not None


def search_docs(query: str, k: int = 6) -> List[str]:
    global _vectorstore
    if _vectorstore is None:
        logger.info("Vectorstore not ready yet; building on demand")
        build_vectorstore()

    # Use MMR (Maximal Marginal Relevance) to diversify retrieved chunks
    results = _vectorstore.max_marginal_relevance_search(query, k=k, fetch_k=20)

    formatted_results = []
    for r in results:
        source = os.path.basename(r.metadata.get("source", "VGU Document"))
        formatted_results.append(f"[Source: {source}]\n{r.page_content}")

    return formatted_results
