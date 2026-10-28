"""YAML and Markdown-frontmatter I/O without third-party dependencies.

The codex image in ai-box has no PyYAML (and the claude/box images have python3 but no
PyYAML), so kinwing ships its own small YAML subset:

* ``dump`` always uses kinwing's emitter: block style, double-quoted strings whenever a
  plain scalar could be misread (dates, numbers, ``yes``/``no``, ``: ``). Its output is
  standard YAML that any parser (PyYAML, Obsidian, ruamel) reads the same way.
* ``load`` uses PyYAML's ``safe_load`` when it is installed, else the built-in parser.
  The built-in parser handles what the emitter writes plus ordinary hand edits: block maps
  and lists, lists of maps, ``|``/``>`` block scalars, single-line flow ``[a, b]`` /
  ``{k: v}``, quoted scalars and comments. Anchors, tags and multi-document streams are
  not supported.
"""

from __future__ import annotations

import datetime as _dt
import json
import re

try:  # pragma: no cover - exercised only where PyYAML is installed
    import yaml as _pyyaml
except Exception:  # noqa: BLE001
    _pyyaml = None


class YamlError(ValueError):
    pass


# ---------------------------------------------------------------------------- dump

_PLAIN_OK = re.compile(r"^[A-Za-z_/][A-Za-z0-9 _./@()+,'=-]*$")
_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "y", "n", "~"}


def _scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    if (
        s
        and _PLAIN_OK.match(s)
        and s.lower() not in _RESERVED
        and not s.endswith(" ")
        and " #" not in s
    ):
        return s
    return json.dumps(s, ensure_ascii=False)


def _is_scalar(v) -> bool:
    return v is None or isinstance(v, (str, int, float, bool))


def _dump(obj, indent: int, out: list[str]) -> None:
    pad = " " * indent
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = _scalar(str(k))
            if isinstance(v, str) and "\n" in v:
                out.append(f"{pad}{key}: |-")
                for line in v.rstrip("\n").split("\n"):
                    out.append(f"{pad}  {line}" if line else "")
            elif _is_scalar(v):
                out.append(f"{pad}{key}: {_scalar(v)}")
            elif isinstance(v, (list, tuple)) and not v:
                out.append(f"{pad}{key}: []")
            elif isinstance(v, dict) and not v:
                out.append(f"{pad}{key}: {{}}")
            else:
                out.append(f"{pad}{key}:")
                _dump(v, indent + 2, out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            if isinstance(item, str) and "\n" in item:
                out.append(f"{pad}- |-")
                for line in item.rstrip("\n").split("\n"):
                    out.append(f"{pad}  {line}" if line else "")
            elif _is_scalar(item):
                out.append(f"{pad}- {_scalar(item)}")
            elif isinstance(item, dict) and item:
                sub: list[str] = []
                _dump(item, indent + 2, sub)
                # First key goes on the dash line: "- key: value".
                sub[0] = f"{pad}- " + sub[0][indent + 2:]
                out.extend(sub)
            elif isinstance(item, (list, tuple)) and item:
                out.append(f"{pad}-")
                _dump(item, indent + 2, out)
            else:
                out.append(f"{pad}- {'{}' if isinstance(item, dict) else '[]'}")
    else:
        out.append(pad + _scalar(obj))


def dump(obj) -> str:
    out: list[str] = []
    _dump(obj, 0, out)
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------- load

_INT = re.compile(r"^[-+]?\d+$")
_FLOAT = re.compile(r"^[-+]?(\d+\.\d*|\.\d+|\d+(\.\d*)?[eE][-+]?\d+)$")


def _strip_comment(line: str) -> str:
    """Drop a trailing `# comment` that is outside quotes."""
    if "#" not in line:
        return line
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
            elif ch == "\\" and quote == '"':
                continue
        elif ch in "\"'":
            # A quote only opens a string at a value boundary.
            if i == 0 or line[i - 1] in " :-[{,":
                quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line


def _parse_scalar(s: str):
    s = s.strip()
    if s == "" or s == "~" or s.lower() == "null":
        return None
    if s.startswith('"'):
        if not s.endswith('"') or len(s) < 2:
            raise YamlError(f"unterminated string: {s}")
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return json.loads(s.replace("\\'", "'"))
    if s.startswith("'"):
        if not s.endswith("'") or len(s) < 2:
            raise YamlError(f"unterminated string: {s}")
        return s[1:-1].replace("''", "'")
    if s.startswith("[") or s.startswith("{"):
        return _parse_flow(s)
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if _INT.match(s):
        return int(s)
    if _FLOAT.match(s):
        return float(s)
    return s


def _split_flow(inner: str) -> list[str]:
    parts, depth, quote, cur = [], 0, None, []
    for ch in inner:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur))
    return [p.strip() for p in parts]


def _parse_flow(s: str):
    s = s.strip()
    if s.startswith("["):
        if not s.endswith("]"):
            raise YamlError(f"unterminated flow list: {s}")
        return [_parse_scalar(p) for p in _split_flow(s[1:-1])]
    if not s.endswith("}"):
        raise YamlError(f"unterminated flow map: {s}")
    out = {}
    for p in _split_flow(s[1:-1]):
        k, _, v = p.partition(":")
        out[_parse_scalar(k)] = _parse_scalar(v)
    return out


def _split_key(text: str):
    """'key: value' -> (key, value) or None when the line is not a mapping entry."""
    if text.startswith('"') or text.startswith("'"):
        q = text[0]
        end = text.find(q, 1)
        while q == '"' and end > 0 and text[end - 1] == "\\":
            end = text.find(q, end + 1)
        if end < 0:
            return None
        rest = text[end + 1:]
        if not rest.startswith(":"):
            return None
        return _parse_scalar(text[: end + 1]), rest[1:].strip()
    m = re.match(r"^([^:#\[\]{},][^:]*?):(\s+|$)(.*)$", text)
    if not m:
        return None
    return m.group(1).strip(), m.group(3)


class _Lines:
    def __init__(self, text: str):
        self.raw = text.replace("\t", "    ").split("\n")
        self.i = 0

    def peek(self):
        """Next meaningful line as (indent, text) without consuming, or None."""
        j = self.i
        while j < len(self.raw):
            line = _strip_comment(self.raw[j])
            if line.strip():
                return len(line) - len(line.lstrip(" ")), line.strip()
            j += 1
        return None

    def next(self):
        while self.i < len(self.raw):
            line = _strip_comment(self.raw[self.i])
            self.i += 1
            if line.strip():
                return len(line) - len(line.lstrip(" ")), line.strip()
        return None

    def block_scalar(self, parent_indent: int, style: str) -> str:
        lines, base = [], None
        while self.i < len(self.raw):
            line = self.raw[self.i]
            if line.strip():
                ind = len(line) - len(line.lstrip(" "))
                if ind <= parent_indent:
                    break
                if base is None:
                    base = ind
                lines.append(line[base:] if len(line) >= base else line.lstrip(" "))
            else:
                lines.append("")
            self.i += 1
        while lines and not lines[-1]:
            lines.pop()
        if style.startswith(">"):
            text = " ".join(l if l else "\n" for l in lines).replace(" \n ", "\n")
        else:
            text = "\n".join(lines)
        keep = style.endswith("+") or (not style.endswith("-") and style in ("|", ">"))
        return text + ("\n" if keep and text else "")


def _parse_block(ls: _Lines, indent: int):
    first = ls.peek()
    if first is None:
        return None
    ind, text = first
    if text == "-" or text.startswith("- "):
        return _parse_list(ls, ind)
    return _parse_map(ls, ind)


def _parse_value(ls: _Lines, rest: str, indent: int):
    """Value after 'key:' or '- ' at `indent` (the indent of the key or dash)."""
    rest = rest.strip()
    if rest in ("|", "|-", "|+", ">", ">-", ">+"):
        return ls.block_scalar(indent, rest)
    if rest:
        if (rest.startswith("[") and not rest.endswith("]")) or (
            rest.startswith("{") and not rest.endswith("}")
        ):
            # A flow collection that spans lines: join until it closes.
            buf = rest
            while True:
                nxt = ls.next()
                if nxt is None:
                    raise YamlError(f"unterminated flow collection: {rest}")
                buf += " " + nxt[1]
                if buf.count("[") <= buf.count("]") and buf.count("{") <= buf.count("}"):
                    break
            return _parse_flow(buf)
        return _parse_scalar(rest)
    nxt = ls.peek()
    if nxt is None:
        return None
    nind, ntext = nxt
    if nind > indent:
        return _parse_block(ls, nind)
    if nind == indent and (ntext == "-" or ntext.startswith("- ")):
        return _parse_list(ls, nind)  # "key:\n- item" (list at the key's indent)
    return None


def _parse_map(ls: _Lines, indent: int) -> dict:
    out: dict = {}
    while True:
        nxt = ls.peek()
        if nxt is None:
            return out
        ind, text = nxt
        if ind < indent:
            return out
        if ind > indent:
            raise YamlError(f"unexpected indentation at: {text}")
        if text == "-" or text.startswith("- "):
            return out
        ls.next()
        kv = _split_key(text)
        if kv is None:
            raise YamlError(f"expected 'key: value', got: {text}")
        key, rest = kv
        out[key] = _parse_value(ls, rest, indent)


def _parse_list(ls: _Lines, indent: int) -> list:
    out: list = []
    while True:
        nxt = ls.peek()
        if nxt is None:
            return out
        ind, text = nxt
        if ind != indent or not (text == "-" or text.startswith("- ")):
            if ind > indent:
                raise YamlError(f"unexpected indentation at: {text}")
            return out
        ls.next()
        rest = text[1:].strip()
        kv = None
        if rest and not rest.startswith(("[", "{", "|", ">")):
            kv = _split_key(rest)
        if kv is not None:
            # "- key: value" starts a map; its other keys sit at indent + 2.
            key, val = kv
            item = {key: _parse_value(ls, val, indent + 2)}
            more = ls.peek()
            if more is not None and more[0] == indent + 2 and not more[1].startswith("- "):
                item.update(_parse_map(ls, indent + 2))
            out.append(item)
        else:
            out.append(_parse_value(ls, rest, indent))


def _normalize(obj):
    """Dates and datetimes (PyYAML parses unquoted ones) become ISO strings."""
    if isinstance(obj, dict):
        return {str(k): _normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    if isinstance(obj, _dt.datetime):
        if obj.tzinfo is not None:
            obj = obj.astimezone(_dt.timezone.utc).replace(tzinfo=None)
        return obj.isoformat(timespec="seconds") + "Z"
    if isinstance(obj, _dt.date):
        return obj.isoformat()
    return obj


def load_builtin(text: str):
    ls = _Lines(text)
    if ls.peek() is None:
        return {}
    val = _parse_block(ls, 0)
    if ls.peek() is not None:
        raise YamlError(f"could not parse line: {ls.peek()[1]}")
    return val


def load(text: str):
    if _pyyaml is not None:
        try:
            val = _pyyaml.safe_load(text)
        except _pyyaml.YAMLError as e:  # pragma: no cover
            raise YamlError(str(e)) from e
        return _normalize(val if val is not None else {})
    return load_builtin(text)


# ---------------------------------------------------------------------------- frontmatter


def split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return {}, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            meta = load("\n".join(lines[1:i])) or {}
            if not isinstance(meta, dict):
                raise YamlError("frontmatter is not a mapping")
            body = "\n".join(lines[i + 1:])
            return meta, body.lstrip("\n")
    raise YamlError("frontmatter has no closing '---'")


def join_frontmatter(meta: dict, body: str) -> str:
    body = (body or "").strip("\n")
    return "---\n" + dump(meta) + "---\n" + (f"\n{body}\n" if body else "")
