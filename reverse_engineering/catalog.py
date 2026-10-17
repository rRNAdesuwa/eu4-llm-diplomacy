"""Read-only catalog and validation helpers for the EU4 reverse-engineering index.

The catalog is deliberately a small JSON registry.  This module never opens a
game process, attaches to a debugger, or asks REA to analyse a target.  It only
reads the registry and, when requested by the caller, streams a SHA-256 over a
user-supplied binary.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = 1
MAX_CATALOG_BYTES = 10 * 1024 * 1024
ALLOWED_NODE_EDGE_STATUSES = frozenset(
    {"runtime_observed", "static_observed", "inferred", "unknown", "fixture_verified"}
)
ALLOWED_QUESTION_STATUSES = frozenset({"open", "partial", "answered"})
ALLOWED_SOURCE_KINDS = frozenset({"runtime", "static", "source", "fixture", "rea"})
CONFIRMED_STATUSES = frozenset({"runtime_observed", "static_observed", "fixture_verified"})
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")

REQUIRED_TOP_LEVEL = (
    "schema_version",
    "title",
    "scope",
    "binary",
    "sources",
    "nodes",
    "edges",
    "questions",
)


class CatalogError(ValueError):
    """Raised when a catalog cannot be safely loaded."""


@dataclass(frozen=True)
class ValidationIssue:
    """A human-readable validation diagnostic."""

    path: str
    message: str
    severity: str = "error"

    def __str__(self) -> str:
        prefix = "错误" if self.severity == "error" else "警告"
        return f"{prefix}: {self.path}: {self.message}"


@dataclass
class ValidationResult:
    """Result returned by :func:`validate_catalog`."""

    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    binary_size: int | None = None
    binary_sha256: str | None = None

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def error_messages(self) -> list[str]:
        return [str(item) for item in self.errors]

    @property
    def warning_messages(self) -> list[str]:
        return [str(item) for item in self.warnings]


def project_root() -> Path:
    """Return the repository root used by the default catalog."""

    return Path(__file__).resolve().parent.parent


def default_catalog_path() -> Path:
    """Return the default registry path without reading it."""

    return Path(__file__).resolve().parent / "data" / "alliance.json"


def _catalog_path(path: str | os.PathLike[str] | None) -> Path:
    raw = default_catalog_path() if path is None else Path(path)
    return raw.expanduser().resolve()


def load_catalog(
    path: str | os.PathLike[str] | None = None,
    *,
    max_bytes: int = MAX_CATALOG_BYTES,
) -> dict[str, Any]:
    """Load a small JSON registry, rejecting oversized or malformed input.

    The size check happens before reading the file.  A catalog is expected to
    be a compact evidence index, so accidentally pointing this function at a
    large dump is treated as an error.
    """

    catalog_path = _catalog_path(path)
    try:
        size = catalog_path.stat().st_size
    except OSError as exc:
        raise CatalogError(f"无法读取索引文件 {catalog_path}: {exc}") from exc
    if size > max_bytes:
        raise CatalogError(
            f"索引文件 {catalog_path} 大小为 {size} 字节，超过 {max_bytes} 字节上限；"
            "拒绝读取大型反汇编或转储文件。"
        )
    try:
        text = catalog_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CatalogError(f"无法读取索引文件 {catalog_path}: {exc}") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CatalogError(f"索引文件不是有效 JSON ({catalog_path}:{exc.lineno}:{exc.colno})") from exc
    if not isinstance(value, dict):
        raise CatalogError("索引 JSON 顶层必须是对象")
    return value


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_nonnegative_int(value: Any) -> int | None:
    """Parse JSON integer values and convenient decimal/hex strings."""

    if _is_int(value):
        return value if value >= 0 else None
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            parsed = int(candidate, 0)
        except ValueError:
            return None
        return parsed if parsed >= 0 else None
    return None


def _is_absolute_path(raw_path: str) -> bool:
    """Recognise POSIX, Windows drive, and UNC absolute paths on every host."""

    if os.path.isabs(raw_path) or Path(raw_path).is_absolute():
        return True
    windows = PureWindowsPath(raw_path)
    return windows.is_absolute() or bool(windows.drive) or raw_path.startswith(("/", "\\"))


def _safe_source_path(root: Path, raw_path: Any) -> tuple[Path | None, str | None]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None, "path 必须是非空字符串"
    if _is_absolute_path(raw_path):
        return None, "path 不得使用绝对路径"

    # Normalise both separators so a Windows-style traversal is checked even
    # when a fixture is validated by a POSIX Python interpreter.
    normalised = raw_path.replace("\\", "/")
    root = root.expanduser().resolve()
    candidate = (root / Path(normalised)).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError:
        return None, "path 解析后越出项目根目录"
    return candidate, None


def _add_issue(result: ValidationResult, path: str, message: str, *, warning: bool = False) -> None:
    issue = ValidationIssue(path=path, message=message, severity="warning" if warning else "error")
    (result.warnings if warning else result.errors).append(issue)


def _require_list(data: Mapping[str, Any], key: str, result: ValidationResult) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        _add_issue(result, key, "必须是数组")
        return []
    return value


def _validate_unique_ids(items: Sequence[Any], kind: str, result: ValidationResult) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(items):
        item_path = f"{kind}[{index}]"
        if not isinstance(item, Mapping):
            _add_issue(result, item_path, "必须是对象")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            _add_issue(result, f"{item_path}.id", "必须是非空字符串")
            continue
        if item_id in indexed:
            _add_issue(result, f"{item_path}.id", f"重复 ID {item_id!r}")
            continue
        indexed[item_id] = item
    return indexed


def _validate_source_refs(
    item: Mapping[str, Any],
    item_path: str,
    source_index: Mapping[str, Mapping[str, Any]],
    result: ValidationResult,
) -> list[str]:
    refs = item.get("sources")
    if refs is None:
        refs = []
    if not isinstance(refs, list):
        _add_issue(result, f"{item_path}.sources", "必须是数组")
        return []
    valid_refs: list[str] = []
    for ref_index, source_id in enumerate(refs):
        if not isinstance(source_id, str) or not source_id.strip():
            _add_issue(result, f"{item_path}.sources[{ref_index}]", "必须是非空 source ID")
            continue
        if source_id not in source_index:
            _add_issue(result, f"{item_path}.sources[{ref_index}]", f"引用不存在的 source {source_id!r}")
            continue
        valid_refs.append(source_id)
    if len(valid_refs) != len(set(valid_refs)):
        _add_issue(result, f"{item_path}.sources", "不得重复引用同一个 source")
    return valid_refs


def _source_kinds(source_ids: Iterable[str], source_index: Mapping[str, Mapping[str, Any]]) -> set[str]:
    return {
        str(source_index[source_id].get("kind"))
        for source_id in source_ids
        if source_id in source_index
    }


def _validate_sources(
    source_items: Sequence[Any],
    *,
    root: Path,
    result: ValidationResult,
    check_sources: bool,
) -> dict[str, Mapping[str, Any]]:
    source_index = _validate_unique_ids(source_items, "sources", result)
    for index, source in enumerate(source_items):
        if not isinstance(source, Mapping):
            continue
        source_path = f"sources[{index}]"
        kind = source.get("kind")
        if kind not in ALLOWED_SOURCE_KINDS:
            _add_issue(result, f"{source_path}.kind", f"不支持的 source kind {kind!r}")
        raw_path = source.get("path")
        resolved, path_error = _safe_source_path(root, raw_path)
        if path_error:
            _add_issue(result, f"{source_path}.path", path_error)
        elif check_sources and resolved is not None:
            try:
                exists = resolved.is_file()
            except OSError:
                exists = False
            if not exists:
                if kind == "runtime":
                    _add_issue(
                        result,
                        f"{source_path}.path",
                        f"缺少本机 runtime 证据文件 {raw_path!r}",
                    )
                else:
                    _add_issue(result, f"{source_path}.path", f"证据文件不存在 {raw_path!r}")
        line = source.get("line")
        if line is not None and (not _is_int(line) or line < 1):
            _add_issue(result, f"{source_path}.line", "line 必须是大于等于 1 的整数")
    return source_index


def _validate_binary(binary: Any, result: ValidationResult) -> tuple[int | None, str | None]:
    if not isinstance(binary, Mapping):
        _add_issue(result, "binary", "必须是对象")
        return None, None
    for key in ("version", "sha256", "image_base"):
        if key not in binary:
            _add_issue(result, f"binary.{key}", "缺少必填字段")
    version = binary.get("version")
    if version is not None and not isinstance(version, str):
        _add_issue(result, "binary.version", "必须是字符串")
    digest = binary.get("sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        _add_issue(result, "binary.sha256", "必须是 64 位十六进制 SHA-256")
        digest = None
    image_base = _parse_nonnegative_int(binary.get("image_base"))
    if image_base is None:
        _add_issue(result, "binary.image_base", "必须是大于等于 0 的整数或十进制/十六进制数字字符串")
    return image_base, digest.lower() if digest else None


def _validate_node_edge_status(
    item: Mapping[str, Any],
    item_path: str,
    source_ids: list[str],
    source_index: Mapping[str, Mapping[str, Any]],
    result: ValidationResult,
) -> None:
    status = item.get("status")
    if status not in ALLOWED_NODE_EDGE_STATUSES:
        _add_issue(result, f"{item_path}.status", f"不支持的状态 {status!r}")
    if status in CONFIRMED_STATUSES and not source_ids:
        _add_issue(result, f"{item_path}.sources", f"状态 {status!r} 的节点/边至少需要一个 source")
    if status == "runtime_observed":
        kinds = _source_kinds(source_ids, source_index)
        if "runtime" not in kinds:
            _add_issue(
                result,
                f"{item_path}.sources",
                "runtime_observed 必须引用 kind=runtime 的 source；fixture 不能冒充 runtime 证据",
            )


def _validate_rva(item: Mapping[str, Any], item_path: str, result: ValidationResult) -> None:
    if "rva" not in item or item.get("rva") is None:
        return
    if _parse_nonnegative_int(item.get("rva")) is None:
        _add_issue(result, f"{item_path}.rva", "必须是大于等于 0 的整数或数字字符串")


def validate_catalog(
    data: Mapping[str, Any],
    *,
    project_root_path: str | os.PathLike[str] | None = None,
    check_sources: bool = False,
    binary_path: str | os.PathLike[str] | None = None,
) -> ValidationResult:
    """Validate a loaded registry and optionally verify an artifact hash.

    ``binary_path`` is used only for a streaming SHA-256 check and a bounded
    PE ``SizeOfImage`` RVA check.  It is never attached to or executed.
    """

    result = ValidationResult()
    if not isinstance(data, Mapping):
        _add_issue(result, "$", "顶层必须是对象")
        return result

    for key in REQUIRED_TOP_LEVEL:
        if key not in data:
            _add_issue(result, key, "缺少必填字段")
    schema_version = data.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        _add_issue(result, "schema_version", f"只支持 schema_version={SCHEMA_VERSION}，收到 {schema_version!r}")
    for key in ("title", "scope"):
        if key in data and not isinstance(data.get(key), str):
            _add_issue(result, key, "必须是字符串")

    root = (
        Path(project_root_path).expanduser().resolve()
        if project_root_path is not None
        else project_root()
    )
    source_items = _require_list(data, "sources", result)
    node_items = _require_list(data, "nodes", result)
    edge_items = _require_list(data, "edges", result)
    question_items = _require_list(data, "questions", result)

    image_base, expected_digest = _validate_binary(data.get("binary"), result)
    source_index = _validate_sources(
        source_items,
        root=root,
        result=result,
        check_sources=check_sources,
    )
    node_index = _validate_unique_ids(node_items, "nodes", result)
    question_index = _validate_unique_ids(question_items, "questions", result)

    for index, node in enumerate(node_items):
        if not isinstance(node, Mapping):
            continue
        item_path = f"nodes[{index}]"
        source_ids = _validate_source_refs(node, item_path, source_index, result)
        _validate_node_edge_status(node, item_path, source_ids, source_index, result)
        _validate_rva(node, item_path, result)
        for key in ("label", "stage"):
            if key in node and not isinstance(node.get(key), str):
                _add_issue(result, f"{item_path}.{key}", "必须是字符串")

    for index, edge in enumerate(edge_items):
        if not isinstance(edge, Mapping):
            continue
        item_path = f"edges[{index}]"
        source_ids = _validate_source_refs(edge, item_path, source_index, result)
        _validate_node_edge_status(edge, item_path, source_ids, source_index, result)
        for field_name in ("from", "to"):
            target = edge.get(field_name)
            if not isinstance(target, str) or target not in node_index:
                _add_issue(result, f"{item_path}.{field_name}", f"引用不存在的 node {target!r}")
        if "kind" in edge and not isinstance(edge.get("kind"), str):
            _add_issue(result, f"{item_path}.kind", "必须是字符串")

    for index, question in enumerate(question_items):
        if not isinstance(question, Mapping):
            continue
        item_path = f"questions[{index}]"
        status = question.get("status")
        if status not in ALLOWED_QUESTION_STATUSES:
            _add_issue(result, f"{item_path}.status", f"不支持的问题状态 {status!r}")
        if "title" not in question or not isinstance(question.get("title"), str):
            _add_issue(result, f"{item_path}.title", "必须是字符串")
        node_refs = question.get("nodes", [])
        if not isinstance(node_refs, list):
            _add_issue(result, f"{item_path}.nodes", "必须是数组")
        else:
            for ref_index, node_id in enumerate(node_refs):
                if not isinstance(node_id, str) or node_id not in node_index:
                    _add_issue(result, f"{item_path}.nodes[{ref_index}]", f"引用不存在的 node {node_id!r}")
        source_refs = _validate_source_refs(question, item_path, source_index, result)
        # A question may be open before it has evidence, but a supplied source
        # must still point to a real source; the helper above enforces that.
        del source_refs
        if "next_step" in question and question.get("next_step") is not None and not isinstance(
            question.get("next_step"), str
        ):
            _add_issue(result, f"{item_path}.next_step", "必须是字符串")

    if binary_path is not None:
        _verify_binary(binary_path, expected_digest, node_items, result)
    elif check_sources:
        _add_issue(
            result,
            "binary",
            "未提供 --binary；只检查了索引合同和证据路径，未验证二进制哈希",
            warning=True,
        )

    # A runtime source is intentionally not checked unless --check-sources is
    # requested.  Make that boundary explicit in the CLI output.
    if not check_sources:
        if any(
            isinstance(source, Mapping) and source.get("kind") == "runtime"
            for source in source_items
        ):
            _add_issue(
                result,
                "sources",
                "未检查本机 runtime 证据文件；如需检查请使用 --check-sources",
                warning=True,
            )

    return result


def _verify_binary(
    binary_path: str | os.PathLike[str],
    expected_digest: str | None,
    node_items: Sequence[Any],
    result: ValidationResult,
) -> None:
    path = Path(binary_path).expanduser().resolve()
    try:
        size = path.stat().st_size
    except OSError as exc:
        _add_issue(result, "--binary", f"无法读取二进制文件 {path}: {exc}")
        return
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        _add_issue(result, "--binary", f"无法流式读取二进制文件 {path}: {exc}")
        return
    actual = digest.hexdigest()
    result.binary_size = size
    result.binary_sha256 = actual
    if expected_digest is None:
        _add_issue(result, "binary.sha256", "无法比较二进制哈希，因为索引中的 sha256 无效")
    elif actual.lower() != expected_digest.lower():
        _add_issue(
            result,
            "--binary",
            f"SHA-256 不匹配：索引为 {expected_digest}，实际为 {actual}",
        )

    size_of_image, pe_note = _read_pe_size_of_image(path, size)
    if pe_note:
        _add_issue(result, "--binary", pe_note, warning=True)

    for index, node in enumerate(node_items):
        if not isinstance(node, Mapping) or node.get("rva") is None:
            continue
        rva = _parse_nonnegative_int(node.get("rva"))
        if rva is None or size_of_image is None:
            continue
        if rva >= size_of_image:
            _add_issue(
                result,
                f"nodes[{index}].rva",
                f"RVA 0x{rva:X} 超出 PE SizeOfImage 0x{size_of_image:X}",
            )
        elif rva >= size:
            _add_issue(
                result,
                f"nodes[{index}].rva",
                f"RVA 0x{rva:X} 超出磁盘文件长度但仍在 PE SizeOfImage 0x{size_of_image:X} 内；"
                "按虚拟映像布局视为有效",
                warning=True,
            )


def _read_pe_size_of_image(path: Path, file_size: int) -> tuple[int | None, str | None]:
    """Read only bounded PE headers and return IMAGE_OPTIONAL_HEADER.SizeOfImage.

    PE32 and PE32+ place ``SizeOfImage`` at offset 56 within the optional
    header.  A malformed or non-PE file is intentionally not treated as an
    RVA failure: its image boundary is unknown, so hash verification remains
    the only binary check available.
    """

    if file_size < 64:
        return None, "非 PE 或文件过短，无法确定 SizeOfImage；仅完成 SHA-256 校验"
    try:
        with path.open("rb") as stream:
            dos_header = stream.read(64)
            if len(dos_header) < 64 or dos_header[:2] != b"MZ":
                return None, "二进制不是 PE 文件，无法确定 SizeOfImage；仅完成 SHA-256 校验"
            pe_offset = int.from_bytes(dos_header[0x3C:0x40], "little")
            minimum_header_end = pe_offset + 4 + 20 + 2
            if pe_offset < 64 or minimum_header_end > file_size:
                return None, "PE 头位置越界，无法确定 SizeOfImage；仅完成 SHA-256 校验"
            stream.seek(pe_offset)
            if stream.read(4) != b"PE\0\0":
                return None, "PE 签名无效，无法确定 SizeOfImage；仅完成 SHA-256 校验"
            coff = stream.read(20)
            if len(coff) != 20:
                return None, "COFF 头不完整，无法确定 SizeOfImage；仅完成 SHA-256 校验"
            optional_size = int.from_bytes(coff[16:18], "little")
            if optional_size < 60:
                return None, "PE optional header 过短，无法确定 SizeOfImage；仅完成 SHA-256 校验"
            optional = stream.read(60)
            if len(optional) != 60:
                return None, "PE optional header 不完整，无法确定 SizeOfImage；仅完成 SHA-256 校验"
            magic = int.from_bytes(optional[0:2], "little")
            if magic not in (0x10B, 0x20B):
                return None, f"不支持的 PE optional header 类型 0x{magic:X}，无法确定 SizeOfImage；仅完成 SHA-256 校验"
            image_size = int.from_bytes(optional[56:60], "little")
            if image_size <= 0:
                return None, "PE SizeOfImage 无效，无法确定 RVA 边界；仅完成 SHA-256 校验"
            return image_size, None
    except OSError as exc:
        return None, f"读取 PE 头失败，无法确定 SizeOfImage ({exc})；仅完成 SHA-256 校验"


def _parse_int_for_display(value: Any) -> int | None:
    return _parse_nonnegative_int(value)


def iter_symbols(data: Mapping[str, Any], query: str | None = None) -> list[Mapping[str, Any]]:
    """Return nodes matching names, RVA/static VA, or informational addresses.

    The node-level ``rva`` is the only address used by binary validation.  An
    optional ``addresses`` mapping is treated as display/search metadata only;
    its keys and values are converted to strings and never used as PE bounds.
    """

    nodes = data.get("nodes", [])
    if not isinstance(nodes, list):
        return []
    needle = (query or "").strip().casefold()
    binary = data.get("binary", {})
    image_base = binary.get("image_base") if isinstance(binary, Mapping) else None
    base = _parse_int_for_display(image_base)
    matches: list[Mapping[str, Any]] = []
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        fields = [str(node.get(key, "")) for key in ("id", "label", "stage", "status")]
        rva = _parse_int_for_display(node.get("rva"))
        if rva is not None:
            fields.extend((str(rva), f"0x{rva:X}", f"{rva:X}"))
            if base is not None:
                static_va = base + rva
                fields.extend((str(static_va), f"0x{static_va:X}", f"{static_va:X}"))
        addresses = node.get("addresses")
        if isinstance(addresses, Mapping):
            fields.extend(str(key) for key in addresses)
            fields.extend(str(value) for value in addresses.values())
        haystack = " ".join(fields)
        if not needle or needle in haystack.casefold():
            matches.append(node)
    return matches


def format_rva(node: Mapping[str, Any], image_base: Any) -> str:
    rva = _parse_int_for_display(node.get("rva"))
    if rva is None:
        return "RVA=?；静态 VA=?"
    base = _parse_int_for_display(image_base)
    if base is None:
        return f"RVA=0x{rva:X}；静态 VA=?"
    return f"RVA=0x{rva:X}；静态 VA=0x{base + rva:X}"


def format_symbol(node: Mapping[str, Any], image_base: Any) -> str:
    node_id = node.get("id", "?")
    label = node.get("label", "")
    stage = node.get("stage", "?")
    status = node.get("status", "?")
    return f"{node_id} | {label} | stage={stage} | {format_rva(node, image_base)} | status={status}"


def summarize_catalog(data: Mapping[str, Any]) -> dict[str, Any]:
    """Build a small, deterministic overview suitable for CLI output."""

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    questions = data.get("questions", [])
    return {
        "title": data.get("title", ""),
        "scope": data.get("scope", ""),
        "binary": data.get("binary", {}),
        "sources": len(data.get("sources", [])) if isinstance(data.get("sources"), list) else 0,
        "nodes": len(nodes) if isinstance(nodes, list) else 0,
        "edges": len(edges) if isinstance(edges, list) else 0,
        "questions": len(questions) if isinstance(questions, list) else 0,
    }


__all__ = [
    "ALLOWED_NODE_EDGE_STATUSES",
    "ALLOWED_QUESTION_STATUSES",
    "ALLOWED_SOURCE_KINDS",
    "CatalogError",
    "MAX_CATALOG_BYTES",
    "SCHEMA_VERSION",
    "ValidationIssue",
    "ValidationResult",
    "default_catalog_path",
    "format_rva",
    "format_symbol",
    "iter_symbols",
    "load_catalog",
    "project_root",
    "summarize_catalog",
    "validate_catalog",
]
