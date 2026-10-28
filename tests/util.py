"""Shared test helpers: an isolated knowledge home per test, in-process CLI calls,
and generated fixture documents (PDF, EPUB, HTML) so no test needs the network."""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "skills" / "knowledge-research" / "lib"
KW_BIN = ROOT / "skills" / "knowledge-research" / "bin" / "kw"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(LIB))

# Local test servers must not go through any HTTP proxy configured in the environment.
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"

from kinwing import cli, store  # noqa: E402
from kinwing.kb import KB  # noqa: E402


class KwTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kwtest-"))
        self.home = self.tmp / "home"
        self.www = self.tmp / "www"
        self.www.mkdir()
        self._env = {k: os.environ.get(k) for k in ("KW_HOME", "WWW_ROOT", "KW_EXPORT_DIR", "KW_RUN")}
        os.environ["KW_HOME"] = str(self.home)
        os.environ["WWW_ROOT"] = str(self.www)
        os.environ.pop("KW_EXPORT_DIR", None)
        os.environ.pop("KW_RUN", None)
        self.p = store.Paths()
        store.ensure_layout(self.p, git=False)
        self.kb = KB(self.p)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kw(self, *args, ok=True):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main([str(a) for a in args])
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
        if ok and code != 0:
            self.fail(f"kw {' '.join(map(str, args))} exited {code}: {err.getvalue()}{out.getvalue()}")
        return code, out.getvalue() + err.getvalue()

    def topic(self, tid="t1", **kw):
        return self.kb.create_topic(kw.pop("title", "Test topic"), tid=tid, **kw)

    def write(self, name: str, text: str) -> Path:
        p = self.tmp / name
        p.write_text(text, encoding="utf-8")
        return p

    def source_from_text(self, text: str, topic="t1", name="doc.md", **kw):
        from kinwing import ingest

        return ingest.add_source(self.kb, topic, file=str(self.write(name, text)), **kw)


DOC = """# Memory models

FSRS models memory with three components: difficulty, stability and retrievability.

Stability is the time, in days, for retrievability to fall from 100% to 90%.

SM-2 uses an ease factor that starts at 2.5 for every card.
"""


def make_pdf(path: Path, lines: list[str]) -> Path:
    """A minimal valid one-page PDF with the given text lines (Helvetica)."""
    content = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(
        "(" + l.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") '" for l in lines) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        "<< /Title (Test PDF) /Author (Test Author) >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info 6 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)
    return path


def make_epub(path: Path, title: str, chapters: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" '
                   'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                   '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                   '</rootfiles></container>')
        items = "".join(f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>' for i in range(len(chapters)))
        spine = "".join(f'<itemref idref="c{i}"/>' for i in range(len(chapters)))
        z.writestr("OEBPS/content.opf", f'<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
                   f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{title}</dc:title>'
                   f'<dc:creator>Jane Author</dc:creator></metadata><manifest>{items}</manifest><spine>{spine}</spine></package>')
        for i, ch in enumerate(chapters):
            z.writestr(f"OEBPS/c{i}.xhtml", f"<html><body><h1>Chapter {i + 1}</h1><p>{ch}</p></body></html>")
    return path


class StaticServer:
    """Serve a directory over http://127.0.0.1:<port> in a thread (for fetch tests)."""

    def __init__(self, root: Path):
        handler = type("H", (SimpleHTTPRequestHandler,), {"log_message": lambda *a: None})
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), lambda *a, **k: handler(*a, directory=str(root), **k))
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()
