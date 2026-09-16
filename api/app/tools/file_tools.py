from pathlib import Path

TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".md", ".txt", ".json",
    ".yml", ".yaml", ".toml", ".cfg", ".ini", ".xml", ".html",
    ".css", ".go", ".java", ".rs", ".c", ".cpp", ".h", ".hpp",
    ".sh", ".bash", ".ps1", ".sql", ".graphql", ".proto",
}


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
    """读取单个本地文件。"""
    if not path.exists():
        return {"status": "failed", "title": path.name,
                "metadata": {}, "skipped_items": [],
                "error_message": "File not found"}
    try:
        content_excerpt = read_text_excerpt(path, excerpt_chars)
    except Exception:
        content_excerpt = None

    return {
        "status": "collected",
        "title": path.name,
        "content_excerpt": content_excerpt,
        "content_path": str(path),
        "metadata": {"size_bytes": path.stat().st_size, "suffix": path.suffix},
        "skipped_items": [],
    }
