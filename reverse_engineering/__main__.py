"""Command-line interface for the read-only reverse-engineering catalog."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Mapping

from .catalog import (
    CatalogError,
    format_symbol,
    iter_symbols,
    load_catalog,
    project_root as repository_root,
    summarize_catalog,
    validate_catalog,
)


def _add_catalog_option(parser: argparse.ArgumentParser, *, dest: str) -> None:
    parser.add_argument(
        "--catalog",
        dest=dest,
        metavar="PATH",
        help="指定只读 JSON 索引文件（默认：reverse_engineering/data/alliance.json）",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m reverse_engineering",
        description="EU4 外交逆向索引的只读查询与校验工具",
    )
    _add_catalog_option(parser, dest="catalog_global")
    parser.add_argument(
        "--project-root",
        dest="project_root",
        metavar="PATH",
        help="源文件路径校验所使用的项目根目录（测试自定义 registry 时可指定）",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    overview = commands.add_parser("overview", help="显示索引概览")
    _add_catalog_option(overview, dest="catalog_local")

    symbols = commands.add_parser("symbols", help="列出节点/符号，可按名称、RVA、静态 VA 或地址关键词过滤")
    _add_catalog_option(symbols, dest="catalog_local")
    symbols.add_argument(
        "query",
        nargs="?",
        help="匹配 id、label、stage、status、RVA、静态 VA 或 addresses 字典内容的关键词",
    )

    questions = commands.add_parser("questions", help="显示待解决问题")
    _add_catalog_option(questions, dest="catalog_local")

    validate = commands.add_parser("validate", help="校验索引、证据引用和可选二进制哈希")
    _add_catalog_option(validate, dest="catalog_local")
    validate.add_argument(
        "--check-sources",
        action="store_true",
        help="检查 source.path 是否存在于项目根目录，并报告缺少的 runtime 证据",
    )
    validate.add_argument(
        "--binary",
        metavar="PATH",
        help="流式计算该二进制的 SHA-256，并按 PE SizeOfImage 检查 RVA；非 PE 仅哈希，不会 attach",
    )
    return parser


def _context(args: argparse.Namespace) -> tuple[str | None, Path | None]:
    raw_catalog = getattr(args, "catalog_local", None) or getattr(args, "catalog_global", None)
    explicit_root = getattr(args, "project_root", None)
    if explicit_root:
        return raw_catalog, Path(explicit_root).expanduser().resolve()
    if raw_catalog:
        # A registry inside this repository still resolves evidence from the
        # repository root.  An outside test fixture is treated as a small
        # self-contained project unless --project-root says otherwise.
        catalog_path = Path(raw_catalog).expanduser().resolve()
        repo = repository_root()
        try:
            catalog_path.relative_to(repo)
        except ValueError:
            return raw_catalog, catalog_path.parent
        return raw_catalog, repo
    return None, None


def _load(args: argparse.Namespace) -> tuple[dict[str, Any], Path | None, Path | None]:
    raw_catalog, root = _context(args)
    data = load_catalog(raw_catalog)
    return data, root, Path(raw_catalog).expanduser().resolve() if raw_catalog else None


def _print_issues(result: Any) -> None:
    for issue in result.errors:
        print(str(issue), file=sys.stderr)
    for issue in result.warnings:
        print(str(issue))


def _structural_result(data: Mapping[str, Any], root: Path | None) -> Any:
    return validate_catalog(data, project_root_path=root, check_sources=False)


def _cmd_overview(args: argparse.Namespace) -> int:
    data, root, catalog_path = _load(args)
    result = _structural_result(data, root)
    summary = summarize_catalog(data)
    print("逆向索引概览")
    if catalog_path:
        print(f"索引：{catalog_path}")
    print(f"标题：{summary['title']}")
    print(f"范围：{summary['scope']}")
    binary = summary["binary"] if isinstance(summary["binary"], Mapping) else {}
    print(
        "二进制："
        f"version={binary.get('version', '?')} "
        f"sha256={binary.get('sha256', '?')} "
        f"image_base={binary.get('image_base', '?')}"
    )
    print(
        f"记录：sources={summary['sources']} nodes={summary['nodes']} "
        f"edges={summary['edges']} questions={summary['questions']}"
    )
    print("证据说明：当前索引描述已记录的 r17c/静态 r18 证据，不代表当前游戏进程状态。")
    _print_issues(result)
    return 0 if result.valid else 1


def _cmd_symbols(args: argparse.Namespace) -> int:
    data, root, _ = _load(args)
    result = _structural_result(data, root)
    if not result.valid:
        _print_issues(result)
        return 1
    binary = data.get("binary", {})
    image_base = binary.get("image_base") if isinstance(binary, Mapping) else None
    matches = iter_symbols(data, args.query)
    if args.query:
        print(f"符号（查询：{args.query}）")
    else:
        print("符号")
    print("静态 VA = image_base + RVA；运行时 base 需另取。")
    for node in matches:
        print(format_symbol(node, image_base))
    print(f"共 {len(matches)} 项")
    return 0


def _cmd_questions(args: argparse.Namespace) -> int:
    data, root, _ = _load(args)
    result = _structural_result(data, root)
    if not result.valid:
        _print_issues(result)
        return 1
    questions = data.get("questions", [])
    print("逆向问题")
    count = 0
    for question in questions:
        if not isinstance(question, Mapping):
            continue
        count += 1
        status = question.get("status", "?")
        priority = question.get("priority", "?")
        title = question.get("title", "")
        line = f"[{status}] {question.get('id', '?')} | priority={priority} | {title}"
        nodes = question.get("nodes")
        if isinstance(nodes, list) and nodes:
            line += f" | nodes={','.join(str(node) for node in nodes)}"
        next_step = question.get("next_step")
        if next_step:
            line += f" | 下一步：{next_step}"
        print(line)
    print(f"共 {count} 项")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    data, root, _ = _load(args)
    result = validate_catalog(
        data,
        project_root_path=root,
        check_sources=args.check_sources,
        binary_path=args.binary,
    )
    if result.valid:
        print("索引校验通过。")
    else:
        print("索引校验失败。")
    _print_issues(result)
    if args.binary and result.binary_sha256:
        print(f"二进制：size={result.binary_size} sha256={result.binary_sha256}")
    if not args.check_sources:
        print("说明：未检查 source 文件是否存在；runtime 证据存在性需加 --check-sources。")
    return 0 if result.valid else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "overview":
            return _cmd_overview(args)
        if args.command == "symbols":
            return _cmd_symbols(args)
        if args.command == "questions":
            return _cmd_questions(args)
        if args.command == "validate":
            return _cmd_validate(args)
    except CatalogError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    parser.error("未知命令")
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised by the CLI tests
    raise SystemExit(main())

