"""Native host relay: gercek surec, gercek cerceveleme (4 bayt uzunluk + JSON), sahte kopruye karsi."""
from __future__ import annotations

import json
import struct
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "native_host"))
import host  # noqa: E402
import install  # noqa: E402


def frame(obj) -> bytes:
    data = json.dumps(obj).encode()
    return struct.pack("<I", len(data)) + data


def unframe_all(raw: bytes) -> list:
    out, i = [], 0
    while i < len(raw):
        (n,) = struct.unpack("<I", raw[i:i + 4])
        out.append(json.loads(raw[i + 4:i + 4 + n]))
        i += 4 + n
    return out


@pytest.fixture
def fake_bridge(tmp_path):
    got = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            got.append((self.path, self.headers.get("X-Kami-Token"), body))
            data = json.dumps({"ok": True, "path": self.path}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    info = tmp_path / "bridge.json"
    info.write_text(json.dumps({"port": srv.server_address[1], "token": "gizli"}))
    yield info, got
    srv.shutdown()


def test_forward(fake_bridge, tmp_path):
    info, got = fake_bridge
    assert host.forward({"type": "add", "url": "http://a/b"}, info) == {"ok": True, "path": "/v1/add"}
    assert got[-1] == ("/v1/add", "gizli", {"url": "http://a/b"})
    assert host.forward({"type": "nope"}, info)["error"] == "unknown_type"
    assert host.forward({"type": "ping"}, tmp_path / "yok.json")["error"] == "offline"


def test_real_process_framing(fake_bridge, monkeypatch):
    """host.py'yi tarayicinin yaptigi gibi alt surec olarak calistir; iki mesaj gonder (connectNative modu)."""
    info, got = fake_bridge
    code = (
        "import sys, pathlib; sys.path.insert(0, r'%s'); import host; "
        "host.BRIDGE_INFO = pathlib.Path(r'%s'); sys.exit(host.main())" % (ROOT / "native_host", info)
    )
    p = subprocess.run([sys.executable, "-c", code],
                       input=frame({"type": "ping"}) + frame({"type": "add", "url": "https://x/ü.zip"}),
                       capture_output=True, timeout=20)
    assert p.returncode == 0, p.stderr
    replies = unframe_all(p.stdout)
    assert [r["path"] for r in replies] == ["/v1/ping", "/v1/add"]
    assert got[-1][2]["url"] == "https://x/ü.zip"


def test_extension_id_matches_manifest():
    ext_id = install.extension_id()
    assert len(ext_id) == 32 and set(ext_id) <= set("abcdefghijklmnop")
