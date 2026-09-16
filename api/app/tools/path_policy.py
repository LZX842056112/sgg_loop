from pathlib import Path

SKIP_DIR_NAMES = {
    ".git", "__pycache__", "node_modules", ".next", "venv", ".venv",
    ".idea", ".vscode", "build", "dist", ".tox", ".eggs", "*.egg-info",
}
SKIP_FILE_PATTERNS = {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin"}
MAX_FILE_BYTES_DEFAULT = 1_000_000


def should_skip_path(file_path: Path, root: Path, max_file_bytes: int) -> dict | None:
    """返回 None 表示不跳过；返回 dict 表示跳过（含原因）。"""
    try:
        relative = file_path.relative_to(root)
    except ValueError:
        return {"path": str(file_path), "reason": "outside_root"}

    parts = relative.parts
    for part in parts:
        if part in SKIP_DIR_NAMES:
            return {"path": str(relative), "reason": f"skipped_dir:{part}"}

    if file_path.is_symlink():
        return {"path": str(relative), "reason": "symlink"}

    if file_path.is_file():
        suffix = file_path.suffix.lower()
        if suffix in SKIP_FILE_PATTERNS:
            return {"path": str(relative), "reason": f"binary_extension:{suffix}"}
        try:
            if file_path.stat().st_size > max_file_bytes:
                return {"path": str(relative), "reason": "file_too_large"}
        except OSError:
            return {"path": str(relative), "reason": "stat_failed"}

    return None


def to_relative_posix(absolute: Path, root: Path) -> str:
    """将绝对路径转换为相对路径 要求不能是快捷方式跳转 统一转换为"""
    try:
        return absolute.relative_to(root).as_posix()
    except ValueError:
        # 路径不在 root 下时退回文件名,避免一次越界中断整个目录扫描
        return absolute.name
