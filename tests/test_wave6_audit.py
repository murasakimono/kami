"""Kami Oda AR-GE + Player URL/Kick Senkronizasyon & Arayuz Duzeltmeleri Testleri."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent


def test_media_server_stream_cmd_youtube_2url_and_audio_shift():
    from app.core.media_server import MediaServer, probe

    # probe headers iletilmeli
    mock_res = MagicMock(returncode=0, stdout=b'{"streams":[],"format":{}}')
    with patch("subprocess.run", return_value=mock_res) as mrun:
        probe("ffprobe", "https://example.com/v.mp4", headers="Referer: https://kick.com/\r\n")
        cmd_called = mrun.call_args[0][0]
        assert "-headers" in cmd_called

    srv = MediaServer(lambda: "ffmpeg")
    e_2url = {
        "path": "https://v.googlevideo.com/1",
        "urls": ["https://v.googlevideo.com/1", "https://a.googlevideo.com/2"],
        "headers": "User-Agent: Mozilla/5.0\r\n",
        "kind": "video",
        "mode": "remux",
        "remote": True,
        "info": {"audio": [{"channels": 2}]},
    }
    cmd = srv.stream_cmd(e_2url, start=10.0, audio_index=0, dialog=False, audio_shift_ms=0)
    assert "-c:v" in cmd and "copy" in cmd
    assert "-avoid_negative_ts" in cmd and "make_zero" in cmd
    af = cmd[cmd.index("-af") + 1]
    assert "aresample=async=1:first_pts=0" in af

    cmd_pos = srv.stream_cmd(e_2url, start=0.0, audio_index=0, audio_shift_ms=250)
    assert "adelay=250|250" in cmd_pos[cmd_pos.index("-af") + 1]

    cmd_neg = srv.stream_cmd(e_2url, start=0.0, audio_index=0, audio_shift_ms=-500)
    assert "atrim=start=0.500,asetpts=PTS-STARTPTS" in cmd_neg[cmd_neg.index("-af") + 1]


def test_room_and_player_ui_contracts():
    rcore = (ROOT / "app/ui/web/room-core.js").read_text(encoding="utf-8")
    assert '"balanced"' in rcore
    assert "x-google-min-bitrate=300" in rcore

    rjs = (ROOT / "app/ui/web/room.js").read_text(encoding="utf-8")
    assert "pl_stop" in rjs
    assert "sGate" in rjs and "highpass" in rjs
    assert "mini_island" in rjs and "shareDlg" in rjs

    rcss = (ROOT / "app/ui/web/room.css").read_text(encoding="utf-8")
    assert ".hasvid .rm-rxbar" in rcss
    assert ".rm-share-dlg" in rcss

    rhtml = (ROOT / "app/ui/web/room.html").read_text(encoding="utf-8")
    assert 'id="sGate"' in rhtml and 'id="shareDlg"' in rhtml

    plib = (ROOT / "app/ui/web/player-lib.js").read_text(encoding="utf-8")
    assert 'min="-1500"' in plib and 'data-act="delay0"' in plib

    pjs = (ROOT / "app/ui/web/player.js").read_text(encoding="utf-8")
    assert 'q.set("as"' in pjs

    wpjs = (ROOT / "app/ui/web/player-watch.js").read_text(encoding="utf-8")
    assert "pl_stop" in wpjs
