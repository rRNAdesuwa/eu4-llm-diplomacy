"""Exact, pinned configuration snapshot. No filesystem access at import time.

Only the new runtime contract supplies the real path/pin. Offline tests supply
fictional owned paths. This module never imports the frozen configuration code.
"""
from pathlib import Path
import hashlib
import io
import os
import re
import stat

KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
REDACTED = "Configuration snapshot refused (redacted)"


def require(ok):
    if not ok:
        raise ValueError(REDACTED)


def validate_text(text):
    # Exact read_local_env 55a3 grammar; values are neither interpreted nor logged.
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        require(bool(separator) and KEY.fullmatch(key.strip()) is not None)


class VirtualText(io.StringIO):
    """Read-only, universal-newline virtual stream; no further physical reads."""
    def __init__(self, text, path, event):
        super().__init__(text, newline=None)
        self.name = str(path)
        self.event = event

    @property
    def encoding(self):
        return "utf-8-sig"

    @property
    def errors(self):
        return "strict"

    def writable(self):
        return False

    def write(self, *args):
        raise io.UnsupportedOperation("Read-only configuration snapshot")

    def writelines(self, *args):
        raise io.UnsupportedOperation("Read-only configuration snapshot")

    def truncate(self, *args):
        raise io.UnsupportedOperation("Read-only configuration snapshot")

    def close(self):
        super().close()
        self.event["virtual_closed"] = self.closed

    def __exit__(self, kind, value, tb):
        self.close()
        self.event["virtual_normal_exit"] = kind is None
        return False


class TextConfigAdapter:
    def __init__(self, meter, path, expected, binary_open):
        # No stat/resolve/open here: source preparation and pure imports are inert.
        self.meter, self.path, self.expected, self.binary_open = meter, Path(path), dict(expected), binary_open
        require(self.path.is_absolute() and self.path.name == "local.env")
        require(set(expected) == {"bytes", "sha256"})
        require(type(expected["bytes"]) is int and 0 <= expected["bytes"] <= 65536)
        require(type(expected["sha256"]) is str and re.fullmatch("[0-9a-f]{64}", expected["sha256"]) is not None)
        self.key = os.path.normcase(os.path.abspath(os.fspath(self.path)))
        self.events = []
        self.snapshot_attempts = 0
        self.opened = 0

    def is_config(self, file):
        if isinstance(file, int):
            return False
        p = Path(file)
        return (p.name.casefold() == "local.env" or os.path.normcase(os.path.abspath(os.fspath(p))) == self.key
                or os.path.normcase(str(p.resolve())) == self.key)

    def open(self, file, mode="r", *args, **kwargs):
        # No content, decoded value, offending line, or raw exception is recorded.
        event = {"path": str(self.path), "accepted": False, "opened": False,
                 "binary_closed": False, "virtual_closed": False,
                 "requested": 0, "returned": 0, "error": None}
        self.events.append(event)
        stream = None
        try:
            p = Path(file)
            require(p.is_absolute() and ".." not in p.parts)
            require(os.path.normcase(os.fspath(p)) == self.key)
            require(os.path.normcase(str(p.resolve())) == self.key)
            defaults = {"buffering": -1, "encoding": None, "errors": None, "newline": None}
            require(mode in ("r", "rt") and len(args) <= 4 and set(kwargs) <= set(defaults))
            supplied = dict(zip(defaults, args))
            require(not (set(supplied) & set(kwargs)))
            supplied.update(kwargs)
            options = {**defaults, **supplied}
            require(type(options["buffering"]) is int and options["buffering"] == -1)
            require(options["encoding"] == "utf-8-sig")
            require(options["errors"] is None or options["errors"] == "strict")
            require(options["newline"] is None)
            self.snapshot_attempts += 1
            require(self.snapshot_attempts <= 16)
            stream = self.binary_open(self.path, "rb")
            self.opened += 1
            event["opened"] = True
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_size == self.expected["bytes"] and info.st_size <= 65536)
            size = info.st_size
            event["requested"] = size + 1
            self.meter.before(self.key, "ordinary", size, stream, size + 1)
            try:
                raw = stream.read(size + 1)
            except BaseException:
                self.meter.entry(self.key, "ordinary")["read_errors"] += 1
                raise
            self.meter.charge(self.key, "ordinary", raw, size + 1)
            event["returned"] = len(raw)
            actual = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            event["raw_pin"] = actual
            require(actual == self.expected)
            stream.close()
            event["binary_closed"] = stream.closed
            text = raw.decode("utf-8-sig", errors="strict")
            validate_text(text)
            result = VirtualText(text, self.path, event)
            event["accepted"] = True
            return result
        except BaseException:
            event["error"] = REDACTED
            raise ValueError(REDACTED) from None
        finally:
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                    event["binary_closed"] = stream.closed
                except BaseException:
                    event["error"] = REDACTED
                    raise ValueError(REDACTED) from None

    def summary(self):
        return {"schema": "EU4-EXACT-CONFIG-SNAPSHOT/1", "path": str(self.path),
                "expected_pin": self.expected, "maximum_bytes": 65536,
                "maximum_snapshots": 16, "snapshot_attempts": self.snapshot_attempts,
                "opened_snapshots": self.opened, "events": self.events,
                "physical_category": "ordinary", "virtual_reads_add_physical_bytes": False,
                "configuration_values_logged": False, "real_path_override_argument": False}


def meter_class(base, contract, reference, binary_open):
    """Runtime path is contract.ROOT/local.env, never a caller-supplied path."""
    require(reference["path"] == "local.env")
    expected = {k: reference[k] for k in ("bytes", "sha256")}
    class ConfigMeter(base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.text_config = TextConfigAdapter(self, contract.ROOT / "local.env", expected, binary_open)

        def open(self, file, mode="r", *args, **kwargs):
            text_read = "b" not in mode and ("r" in mode or "+" in mode)
            if not isinstance(file, int) and (self.text_config.is_config(file) or text_read):
                return self.text_config.open(file, mode, *args, **kwargs)
            return super().open(file, mode, *args, **kwargs)
    return ConfigMeter
