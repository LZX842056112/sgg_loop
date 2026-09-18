from pathlib import Path

TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".md", ".txt", ".json",
    ".yml", ".yaml", ".toml", ".cfg", ".ini", ".xml", ".html",
    ".css", ".go", ".java", ".rs", ".c", ".cpp", ".h", ".hpp",
    ".sh", ".bash", ".ps1", ".sql", ".graphql", ".proto",
}
PDF_PAGE_LIMIT = 5


def read_pdf_excerpt(path: Path, excerpt_chars: int) -> tuple[str | None, int]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required to parse PDF files") from exc

    reader = PdfReader(str(path))
    page_count = len(reader.pages)
    excerpt_parts: list[str] = []
    remaining_chars = excerpt_chars
    for page in reader.pages[:PDF_PAGE_LIMIT]:
        if remaining_chars <= 0:
            break
        page_text = page.extract_text() or ""
        if not page_text:
            continue
        excerpt_parts.append(page_text[:remaining_chars])
        remaining_chars -= len(excerpt_parts[-1])
    excerpt = "\n".join(excerpt_parts)[:excerpt_chars]
    return (excerpt or None), page_count


def read_text_excerpt(file_path: Path, max_chars: int) -> str | None:
    """读取文本文件的前 max_chars 个字符。"""
    if file_path.suffix.lower() not in TEXT_EXTENSIONS:
        return None
    try:
        text = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
    return text[:max_chars]


def read_local_file(path: Path, max_file_bytes: int, excerpt_chars: int) -> dict:
    """读取单个本地文件（文本或 PDF）。"""
    if not path.exists():
        return {"status": "failed", "title": path.name,
                "metadata": {}, "skipped_items": [],
                "error_message": "File not found"}
    metadata = {"size_bytes": path.stat().st_size, "suffix": path.suffix}
    if path.suffix.lower() == ".pdf":
        metadata["file_type"] = "pdf"
        content_excerpt = None
        try:
            content_excerpt, page_count = read_pdf_excerpt(path, excerpt_chars)
            metadata["page_count"] = page_count
        except RuntimeError:
            raise
        except Exception as exc:
            metadata["pdf_parse_error"] = str(exc)
        return {
            "status": "collected",
            "title": path.name,
            "content_excerpt": content_excerpt,
            "content_path": str(path),
            "metadata": metadata,
            "skipped_items": [],
        }
    try:
        content_excerpt = read_text_excerpt(path, excerpt_chars)
    except Exception:
        content_excerpt = None
    return {
        "status": "collected",
        "title": path.name,
        "content_excerpt": content_excerpt,
        "content_path": str(path),
        "metadata": metadata,
        "skipped_items": [],
    }
