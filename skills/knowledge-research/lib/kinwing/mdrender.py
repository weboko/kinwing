"""A small, safe Markdown → HTML renderer for the reader.

Concept explanations and overviews are written by agents that read untrusted web
content, so nothing is passed through as HTML: all text is escaped first, links are
limited to http(s), in-app (#/…) and fragment URLs, and raw HTML in the source shows as
text. Supports headings, paragraphs, emphasis, code, fenced code, blockquotes, nested
lists, tables, rules, links and [[concept-id|label]] wikilinks.
"""

from __future__ import annotations

import html
import re
from typing import Callable

Resolver = Callable[[str], "tuple[str, str] | None"]  # wikilink target -> (href, label)


def _safe_href(url: str) -> str | None:
    url = html.unescape(url.strip())
    if re.match(r"^https?://", url, re.I) or url.startswith("#"):
        return html.escape(url, quote=True)
    return None


def inline(text: str, resolve: Resolver | None = None) -> str:
    codes: list[str] = []

    def keep_code(m):
        codes.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", keep_code, text)
    text = html.escape(text, quote=False)

    def wiki(m):
        target, _, label = m.group(1).partition("|")
        target = html.unescape(target.strip())
        res = resolve(target) if resolve else None
        if res:
            href, title = res
            return f'<a class="wikilink" href="{html.escape(href, quote=True)}">{html.escape(label.strip() or title)}</a>'
        return f'<span class="wikilink missing">{html.escape(label.strip() or target)}</span>'

    text = re.sub(r"\[\[([^\]]{1,200})\]\]", wiki, text)

    def link(m):
        label, url = m.group(1), m.group(2)
        href = _safe_href(url)
        if not href:
            return label
        ext = ' target="_blank" rel="noopener noreferrer"' if href.lower().startswith("http") else ""
        return f'<a href="{href}"{ext}>{label}</a>'

    text = re.sub(r"\[([^\]]{1,300})\]\(([^)\s]{1,800})\)", link, text)
    text = re.sub(r"(?<![\w*])\*\*(?=\S)(.+?)(?<=\S)\*\*(?![\w*])", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w_])__(?=\S)(.+?)(?<=\S)__(?![\w_])", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"(?<![\w_])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![\w_])", r"<em>\1</em>", text)
    text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def render(md: str, resolve: Resolver | None = None, para_attr: bool = True) -> str:
    lines = (md or "").replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i, n, para_no = 0, len(lines), 0

    def attr():
        nonlocal para_no
        para_no += 1
        return f' data-para="{para_no}"' if para_attr else ""

    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = re.match(r"^(`{3,}|~{3,})\s*([\w+-]*)\s*$", line)
        if m:
            fence, buf = m.group(1), []
            i += 1
            while i < n and not lines[i].startswith(fence):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append(f"<pre{attr()}><code>{html.escape(chr(10).join(buf))}</code></pre>")
            continue
        m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if m:
            lvl = min(len(m.group(1)) + 1, 6)  # the page owns <h1>
            out.append(f"<h{lvl}{attr()}>{inline(m.group(2), resolve)}</h{lvl}>")
            i += 1
            continue
        if re.match(r"^\s*([-*_])(\s*\1){2,}\s*$", line):
            out.append("<hr>")
            i += 1
            continue
        if line.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append(f"<blockquote{attr()}>{render(chr(10).join(buf), resolve, False)}</blockquote>")
            continue
        if "|" in line and i + 1 < n and re.match(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$", lines[i + 1]):
            def cells(s):
                s = s.strip()
                s = s[1:] if s.startswith("|") else s
                s = s[:-1] if s.endswith("|") else s
                return [c.strip() for c in s.split("|")]
            head = cells(line)
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(cells(lines[i]))
                i += 1
            th = "".join(f"<th>{inline(c, resolve)}</th>" for c in head)
            trs = "".join("<tr>" + "".join(f"<td>{inline(c, resolve)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f'<div class="table-wrap"{attr()}><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>')
            continue
        if re.match(r"^\s*([-*+]|\d+[.)])\s+", line):
            html_list, i = _list(lines, i, resolve)
            out.append(html_list.replace(">", attr() + ">", 1) if para_attr else html_list)
            continue
        buf = [line.strip()]
        i += 1
        while i < n and lines[i].strip() and not re.match(r"^(#{1,6}\s|>|\s*([-*+]|\d+[.)])\s+|`{3,}|~{3,})", lines[i]):
            buf.append(lines[i].strip())
            i += 1
        out.append(f"<p{attr()}>{inline(' '.join(buf), resolve)}</p>")
    return "\n".join(out)


def _list(lines: list[str], i: int, resolve) -> tuple[str, int]:
    first = lines[i]
    indent = len(first) - len(first.lstrip())
    ordered = bool(re.match(r"^\s*\d+[.)]\s", first))
    tag = "ol" if ordered else "ul"
    items: list[str] = []
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            if i + 1 < n and re.match(r"^\s*([-*+]|\d+[.)])\s+", lines[i + 1]) and \
                    len(lines[i + 1]) - len(lines[i + 1].lstrip()) >= indent:
                i += 1
                continue
            break
        ind = len(line) - len(line.lstrip())
        m = re.match(r"^\s*([-*+]|\d+[.)])\s+(.*)$", line)
        if m and ind == indent:
            items.append(inline(m.group(2), resolve))
            i += 1
        elif m and ind > indent:
            sub, i = _list(lines, i, resolve)
            if items:
                items[-1] += sub
            else:
                items.append(sub)
        elif ind > indent and items:
            items[-1] += " " + inline(line.strip(), resolve)
            i += 1
        else:
            break
    return f"<{tag}>" + "".join(f"<li>{it}</li>" for it in items) + f"</{tag}>", i
