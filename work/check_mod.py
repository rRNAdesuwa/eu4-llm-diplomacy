#!/usr/bin/env python3
"""Static checks for the local EU4 bridge overlay.

This checker intentionally does not start EU4 or run the installer.  It checks
the generated script files, compares the diplomatic-action overlay with the
installed vanilla source, and inspects the installer with Python's AST.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from local_config import get_path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MOD = ROOT / "mod" / "llm_bridge"
DEFAULT_INSTALLER = ROOT / "work" / "install.py"
DIP_REL = Path("common") / "diplomatic_actions" / "00_diplomatic_actions.txt"
MOD_ENTRY = "mod/llm_bridge.mod"
LOCK_TOOLTIP = "LLM_BRIDGE_LOCKED"
LOCK_FLAG = "llm_diplomacy_locked"
LOCK_ACTIONS = ("declarewar", "break_alliance")


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    column: int
    start: int
    end: int


@dataclass(frozen=True)
class Assignment:
    key: str
    key_index: int
    open_index: int | None
    close_index: int | None
    scalar_index: int | None


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.passes: list[str] = []

    def ok(self, message: str) -> None:
        self.passes.append(message)

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def print(self) -> None:
        for message in self.passes:
            print(f"PASS: {message}")
        for message in self.errors:
            print(f"FAIL: {message}")


def read_text(path: Path) -> str:
    """Read Clausewitz/Python text while accepting an optional UTF-8 BOM."""

    return path.read_text(encoding="utf-8-sig")


def lex(text: str) -> tuple[list[Token], list[str]]:
    """Tokenize enough of Clausewitz syntax for structural checks.

    Comments begin with ``#`` outside strings.  Braces and ``#`` characters
    inside double-quoted strings are retained as string content and therefore
    cannot affect brace balancing.
    """

    tokens: list[Token] = []
    errors: list[str] = []
    i = 0
    line = 1
    column = 1

    def take() -> str:
        nonlocal i, line, column
        char = text[i]
        i += 1
        if char == "\n":
            line += 1
            column = 1
        else:
            column += 1
        return char

    while i < len(text):
        char = text[i]
        if char.isspace():
            take()
            continue
        if char == "#":
            while i < len(text) and text[i] != "\n":
                take()
            continue
        if char in "{}=":
            start = i
            token_line = line
            token_column = column
            take()
            tokens.append(Token("symbol", text[start:i], token_line, token_column, start, i))
            continue
        if char == '"':
            start = i
            token_line = line
            token_column = column
            take()
            closed = False
            while i < len(text):
                if text[i] == "\\":
                    take()
                    if i < len(text):
                        take()
                    continue
                if text[i] == '"':
                    take()
                    closed = True
                    break
                take()
            tokens.append(Token("string", text[start:i], token_line, token_column, start, i))
            if not closed:
                errors.append(f"unterminated string at line {token_line}, column {token_column}")
            continue

        start = i
        token_line = line
        token_column = column
        while i < len(text):
            current = text[i]
            if current.isspace() or current in "{}=\"#":
                break
            take()
        if i == start:
            # This is defensive: all one-character delimiters are handled
            # above, so advancing prevents an unexpected infinite loop.
            take()
        else:
            tokens.append(Token("word", text[start:i], token_line, token_column, start, i))

    return tokens, errors


def match_braces(tokens: list[Token]) -> tuple[dict[int, int], list[str]]:
    matching: dict[int, int] = {}
    stack: list[int] = []
    errors: list[str] = []
    for index, token in enumerate(tokens):
        if token.value == "{":
            stack.append(index)
        elif token.value == "}":
            if not stack:
                errors.append(f"unmatched closing brace at line {token.line}, column {token.column}")
            else:
                opening = stack.pop()
                matching[opening] = index
    for opening in stack:
        token = tokens[opening]
        errors.append(f"unclosed opening brace at line {token.line}, column {token.column}")
    return matching, errors


def top_level_blocks(tokens: list[Token], matching: dict[int, int]) -> list[Assignment]:
    blocks: list[Assignment] = []
    depth = 0
    for index, token in enumerate(tokens):
        if token.value == "{":
            depth += 1
            continue
        if token.value == "}":
            depth -= 1
            continue
        if (
            depth == 0
            and token.kind == "word"
            and index + 2 < len(tokens)
            and tokens[index + 1].value == "="
            and tokens[index + 2].value == "{"
            and index + 2 in matching
        ):
            blocks.append(
                Assignment(
                    key=token.value,
                    key_index=index,
                    open_index=index + 2,
                    close_index=matching[index + 2],
                    scalar_index=None,
                )
            )
    return blocks


def direct_assignments(
    tokens: list[Token],
    opening: int,
    closing: int,
    matching: dict[int, int],
) -> Iterable[Assignment]:
    """Yield direct ``key = value`` children of a brace block."""

    index = opening + 1
    while index < closing:
        if index + 1 >= closing:
            break
        if tokens[index + 1].value != "=":
            index += 1
            continue
        value_index = index + 2
        if value_index >= closing:
            break
        if tokens[value_index].value == "{":
            child_closing = matching.get(value_index)
            if child_closing is None or child_closing > closing:
                index += 1
                continue
            yield Assignment(tokens[index].value, index, value_index, child_closing, None)
            index = child_closing + 1
        else:
            yield Assignment(tokens[index].value, index, None, None, value_index)
            index = value_index + 1


def token_signature(tokens: list[Token]) -> list[tuple[str, str]]:
    return [(token.kind, token.value) for token in tokens]


def _assignment_scalar(tokens: list[Token], assignment: Assignment) -> str | None:
    if assignment.scalar_index is None:
        return None
    return tokens[assignment.scalar_index].value


def _block_signature(tokens: list[Token], assignment: Assignment) -> list[tuple[str, str]]:
    if assignment.open_index is None or assignment.close_index is None:
        return []
    return token_signature(tokens[assignment.open_index : assignment.close_index + 1])


def is_lock_condition(
    tokens: list[Token], assignment: Assignment, matching: dict[int, int]
) -> bool:
    if assignment.key != "condition" or assignment.open_index is None or assignment.close_index is None:
        return False
    children = list(
        direct_assignments(tokens, assignment.open_index, assignment.close_index, matching)
    )
    tooltip = next((child for child in children if child.key == "tooltip"), None)
    potential = next((child for child in children if child.key == "potential"), None)
    allow = next((child for child in children if child.key == "allow"), None)
    if tooltip is None or potential is None or allow is None:
        return False
    return (
        _assignment_scalar(tokens, tooltip) == LOCK_TOOLTIP
        and potential.open_index is not None
        and allow.open_index is not None
    )


def check_balanced_scripts(mod_root: Path, report: Report) -> None:
    scripts = sorted(mod_root.rglob("*.txt")) if mod_root.exists() else []
    if not scripts:
        report.fail(f"no .txt scripts found under {mod_root}")
        return

    errors: list[str] = []
    for path in scripts:
        try:
            text = read_text(path)
        except (OSError, UnicodeError) as exc:
            errors.append(f"{path}: cannot read ({exc})")
            continue
        tokens, lexical_errors = lex(text)
        _, brace_errors = match_braces(tokens)
        for error in lexical_errors + brace_errors:
            errors.append(f"{path}: {error}")

    if errors:
        report.errors.extend(errors)
    else:
        report.ok(f"balanced braces in {len(scripts)} mod .txt scripts (comments/strings ignored)")


def check_diplomatic_actions(mod_root: Path, game_root: Path, report: Report) -> None:
    mod_path = mod_root / DIP_REL
    vanilla_path = game_root / DIP_REL
    if not mod_path.exists():
        report.fail(f"missing mod diplomatic actions: {mod_path}")
        return
    if not vanilla_path.exists():
        report.fail(f"missing vanilla diplomatic actions: {vanilla_path}")
        return

    try:
        mod_text = read_text(mod_path)
        vanilla_text = read_text(vanilla_path)
    except (OSError, UnicodeError) as exc:
        report.fail(f"cannot read diplomatic actions ({exc})")
        return

    mod_tokens, mod_lex_errors = lex(mod_text)
    vanilla_tokens, vanilla_lex_errors = lex(vanilla_text)
    mod_matching, mod_brace_errors = match_braces(mod_tokens)
    vanilla_matching, vanilla_brace_errors = match_braces(vanilla_tokens)
    for error in mod_lex_errors + mod_brace_errors:
        report.fail(f"{mod_path}: {error}")
    for error in vanilla_lex_errors + vanilla_brace_errors:
        report.fail(f"{vanilla_path}: {error}")
    if mod_lex_errors or mod_brace_errors or vanilla_lex_errors or vanilla_brace_errors:
        return

    mod_blocks = top_level_blocks(mod_tokens, mod_matching)
    vanilla_blocks = top_level_blocks(vanilla_tokens, vanilla_matching)
    for action in LOCK_ACTIONS:
        mod_matches = [block for block in mod_blocks if block.key == action]
        vanilla_matches = [block for block in vanilla_blocks if block.key == action]
        if len(mod_matches) != 1:
            report.fail(f"expected exactly one top-level {action} block in {mod_path}, found {len(mod_matches)}")
        if len(vanilla_matches) != 1:
            report.fail(f"expected exactly one top-level {action} block in {vanilla_path}, found {len(vanilla_matches)}")

    lock_nodes: list[Assignment] = []
    lock_parents: list[str] = []
    for block in mod_blocks:
        if block.open_index is None or block.close_index is None:
            continue
        for child in direct_assignments(mod_tokens, block.open_index, block.close_index, mod_matching):
            if is_lock_condition(mod_tokens, child, mod_matching):
                lock_nodes.append(child)
                lock_parents.append(block.key)

    if len(lock_nodes) != len(LOCK_ACTIONS) or sorted(lock_parents) != sorted(LOCK_ACTIONS):
        report.fail(
            "lock condition count/scope mismatch: "
            f"expected one under {', '.join(LOCK_ACTIONS)}, found {lock_parents}"
        )

    # Remove only the added condition token ranges, then compare every
    # significant token with vanilla.  This catches edits to original action
    # definitions while intentionally ignoring comments and formatting.
    removed: set[int] = set()
    for node in lock_nodes:
        assert node.close_index is not None
        removed.update(range(node.key_index, node.close_index + 1))
    stripped_mod = [
        signature
        for index, signature in enumerate(token_signature(mod_tokens))
        if index not in removed
    ]
    vanilla_signature = token_signature(vanilla_tokens)
    if stripped_mod != vanilla_signature:
        first = next(
            (
                index
                for index, pair in enumerate(stripped_mod)
                if index >= len(vanilla_signature) or pair != vanilla_signature[index]
            ),
            min(len(stripped_mod), len(vanilla_signature)),
        )
        report.fail(
            "mod diplomatic actions differ from vanilla after removing lock conditions "
            f"at significant token index {first}"
        )
    else:
        raw_condition = """
    condition = {
        tooltip = LLM_BRIDGE_LOCKED
        potential = { has_country_flag = llm_diplomacy_locked }
        allow = { NOT = { has_country_flag = llm_diplomacy_locked } }
    }
"""
        if (
            mod_text.count(raw_condition) == len(LOCK_ACTIONS)
            and mod_text.replace(raw_condition, "") == vanilla_text
        ):
            report.ok("diplomatic actions preserve vanilla text after removing the two inserted lock conditions")
        else:
            report.ok("diplomatic actions preserve vanilla significant tokens after removing the two lock conditions")


def _constant(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _data_key(node: ast.AST, key: str) -> bool:
    if not isinstance(node, ast.Subscript) or not isinstance(node.value, ast.Name):
        return False
    if node.value.id != "data":
        return False
    return _constant(node.slice) == key


def _path_join(node: ast.AST, base_name: str, filename: str) -> bool:
    return (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Div)
        and isinstance(node.left, ast.Name)
        and node.left.id == base_name
        and _constant(node.right) == filename
    )


def _method_call(node: ast.AST, owner: str, method: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == owner
    )


def _enabled_append(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "append"
        and _data_key(node.func.value, "enabled_mods")
        and len(node.args) == 1
        and _constant(node.args[0]) == MOD_ENTRY
    )


def _enabled_guard(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.NotIn)
        and _constant(node.left) == MOD_ENTRY
        and len(node.comparators) == 1
        and _data_key(node.comparators[0], "enabled_mods")
    )


def _config_json_write(node: ast.AST) -> bool:
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "write_text"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "config"
        and node.args
    ):
        return False
    value = node.args[0]
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and isinstance(value.func.value, ast.Name)
        and value.func.value.id == "json"
        and value.func.attr == "dumps"
        and bool(value.args)
        and isinstance(value.args[0], ast.Name)
        and value.args[0].id == "data"
    )


def _backup_guard(node: ast.AST) -> bool:
    if not isinstance(node, ast.UnaryOp) or not isinstance(node.op, ast.Not):
        return False
    call = node.operand
    return (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "exists"
        and isinstance(call.func.value, ast.BinOp)
        and _path_join(call.func.value, "BACKUP", "dlc_load.json")
    )


def _backup_copy(node: ast.AST) -> bool:
    return (
        _method_call(node, "shutil", "copy2")
        and len(node.args) >= 2
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "config"
        and _path_join(node.args[1], "BACKUP", "dlc_load.json")
    )


def check_installer(installer: Path, report: Report) -> None:
    if not installer.exists():
        report.fail(f"missing installer: {installer}")
        return
    try:
        source = read_text(installer)
        tree = ast.parse(source, filename=str(installer))
    except (OSError, UnicodeError, SyntaxError) as exc:
        report.fail(f"cannot parse installer {installer}: {exc}")
        return

    if_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.If)]
    preserve_ifs = [node for node in if_nodes if _enabled_guard(node.test)]
    append_calls = [node for node in ast.walk(tree) if _enabled_append(node)]
    enabled_assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
        and (
            any(_data_key(target, "enabled_mods") for target in getattr(node, "targets", []))
            if isinstance(node, ast.Assign)
            else _data_key(getattr(node, "target", ast.Constant(None)), "enabled_mods")
        )
    ]
    if len(preserve_ifs) != 1 or not append_calls:
        report.fail("installer does not statically show an append-if-missing enabled-mod entry")
    elif enabled_assignments:
        report.fail("installer assigns to data['enabled_mods']; existing enabled mods may be replaced")
    elif not any(any(_enabled_append(child) for child in ast.walk(if_node)) for if_node in preserve_ifs):
        report.fail("installer's enabled-mod guard has no matching append in its body")
    else:
        report.ok("installer preserves existing enabled mods by appending only when the bridge entry is absent")

    config_writes = [node for node in ast.walk(tree) if _config_json_write(node)]
    if not config_writes:
        report.fail("installer has no JSON config write sourced from the loaded data object")

    backup_mkdirs = [node for node in ast.walk(tree) if _method_call(node, "BACKUP", "mkdir")]
    backup_ifs = [node for node in if_nodes if _backup_guard(node.test)]
    backup_copies = [node for node in ast.walk(tree) if _backup_copy(node)]
    guarded_copies = [
        node
        for if_node in backup_ifs
        for node in ast.walk(if_node)
        if _backup_copy(node)
    ]
    if not backup_mkdirs:
        report.fail("installer does not create the backup directory")
    if not backup_ifs or not backup_copies:
        report.fail("installer does not statically show a guarded dlc_load.json backup")
    elif not guarded_copies:
        report.fail("dlc_load.json copy is not inside the existing-backup guard")
    elif config_writes and min(node.lineno for node in backup_copies) > min(node.lineno for node in config_writes):
        report.fail("dlc_load.json backup occurs after the config write")
    else:
        report.ok("installer preserves a pre-existing dlc_load.json backup and creates it only when absent")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--game",
        type=Path,
        default=None,
        help="EU4 installation root (defaults to EU4_GAME_ROOT from local.env)",
    )
    parser.add_argument("--mod", type=Path, default=DEFAULT_MOD, help="source mod root")
    parser.add_argument("--installer", type=Path, default=DEFAULT_INSTALLER, help="installer script")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    game = args.game or get_path("EU4_GAME_ROOT")
    assert game is not None
    report = Report()
    check_balanced_scripts(args.mod, report)
    check_diplomatic_actions(args.mod, game, report)
    check_installer(args.installer, report)
    report.print()
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
