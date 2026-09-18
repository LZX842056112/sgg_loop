from html.parser import HTMLParser

import httpx


class ReadableHTMLParser(HTMLParser):
    """提取网页标题和正文文本，忽略 script/style 这类不可作为证据的内容。"""

    # 初始化解析器状态：标题、忽略深度、正文文本片段
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self._in_title = False
        self._ignored_depth = 0
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []

    # 进入 title/script/style 标签时记录状态；script 等不可作为证据的内容标记忽略
    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1

    # 退出标签：title 结束时拼出标题，script/style 结束时恢复普通文本收集
    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            self.title = " ".join(part.strip() for part in self._title_parts if part.strip()) or None
        if tag in {"script", "style", "noscript"} and self._ignored_depth > 0:
            self._ignored_depth -= 1

    # 收集文本：标题单独累积，普通正文仅在非忽略深度下累积
    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if not stripped:
            return
        if self._in_title:
            self._title_parts.append(stripped)
            return
        if self._ignored_depth == 0:
            self._text_parts.append(stripped)

    # 返回拼接后的网页正文文本
    @property
    def text(self) -> str:
        return " ".join(self._text_parts)


def fetch_web_url(
        url: str,
        timeout_seconds: float,
        excerpt_chars: int,
        transport: httpx.BaseTransport | None = None,
) -> dict:
    """读取公开网页并提取短摘要；不执行页面脚本。"""

    with httpx.Client(
            follow_redirects=True,
            timeout=timeout_seconds,
            transport=transport,
    ) as client:
        response = client.get(url)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    title: str | None = None
    if "html" in content_type.lower():
        parser = ReadableHTMLParser()
        parser.feed(response.text)
        title = parser.title
        text = parser.text
    else:
        text = response.text

    return {
        "status": "collected",
        "title": title,
        "content_excerpt": text[:excerpt_chars],
        "metadata": {
            "content_type": content_type,
            "final_url": str(response.url),
            "status_code": response.status_code,
            "excerpt_chars": min(len(text), excerpt_chars),
        },
        "skipped_items": [],
    }
