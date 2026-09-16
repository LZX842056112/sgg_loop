from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


# 校验失败 抛出这个异常
class SourceValidationError(ValueError):
    """资料来源检验失败"""


# 校验成功 返回这个类型的数据 表示这个源
@dataclass(frozen=True)
class ValidatedSource:
    normalized_uri: str
    metadata: dict = field(default_factory=dict)


# 校验方法
def validate_source_input(source_type: str, uri: str) -> ValidatedSource:
    """校验资料来源的合法性并规范会输出结果"""
    # 去空格操作
    uri = uri.strip()
    # 说明uri里面只有空格
    if not uri:
        raise SourceValidationError("URI must be not empty")

    # 根据不同的类型判断 进行不同的校验函数
    if source_type == "github_repo":
        return _validate_github_repo(uri)
    if source_type in ("local_directory", "local_file"):
        return _validate_local_path(uri)
    if source_type == "web_url":
        return _validate_web_url(uri)
    # 如果类型都没法匹配  直接抛出异常
    raise SourceValidationError(f"Unsupported source type:{source_type}")


def _validate_github_repo(uri: str) -> ValidatedSource:
    """校验传入的github仓库地址是否合法"""
    parsed = urlparse(uri)
    # 只接受 https 协议,且主机必须恰好是 github.com
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise SourceValidationError("Github repo must be an https://github.com/owner/repo URL")
    # 带端口/凭据/query/fragment 的地址一律拒绝,否则会拼出错误的 owner/repo
    if parsed.port or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SourceValidationError("Github repo URL must not include port, credentials, query or fragment")

    # 路径必须恰好是 owner/repo 两段
    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) != 2:
        raise SourceValidationError("Github URL must include owner and repo name")

    owner, repo = path_parts
    repo = repo.removesuffix(".git")
    normalized = f"https://github.com/{owner}/{repo}"
    return ValidatedSource(
        normalized_uri=normalized,
        metadata={"owner": owner, "repo": repo}
    )


def _validate_local_path(uri: str) -> ValidatedSource:
    """校验传入的本地路径是否合法"""
    # 统一转换为标准格式的绝对路径
    path = Path(uri).expanduser().resolve()
    if not path.exists():
        raise SourceValidationError(f"Path does not exist:{path}")
    return ValidatedSource(normalized_uri=str(path), metadata={"absolute_path": str(path)})


def _validate_web_url(uri: str) -> ValidatedSource:
    """校验传入的网址是否合法"""
    parsed = urlparse(uri)
    if not parsed.hostname:
        raise SourceValidationError("web uri parsed fail")
    if parsed.scheme not in ("http", "https"):
        raise SourceValidationError("web URL must start with https:// or http://")
    return ValidatedSource(normalized_uri=uri, metadata={})
