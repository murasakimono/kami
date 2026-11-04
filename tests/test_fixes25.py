"""05.11 duzeltmeleri (defter arsiv 25-26): telefon /send, soz sirasi + yapistir, arsivci tahmini, toplu link, AI onarim."""
import json
import os

from app.core import automate, lyrics, musicarchive, phone


# ---------- telefon ----------
def _srv(added=1):
    got = []

    def on_text(t):
        got.append(t)
        return {"added": added, "names": t.splitlines()}
    return phone.PhoneServer(0, lambda: "anahtar123", on_text), got


def test_phone_find_links_everywhere():
    yt = "https://youtu.be/dQw4w9WgXcQ?si=abc"
    assert phone.find_links({"text": "Rick Astley - Never"}) == []
    assert phone.find_links({"text": "izle", "extra": {"url": yt}}) == [yt]
    assert phone.find_links({"items": [{"link": "https://www.youtube.com/shorts/abc123"}]}) == \
        ["https://www.youtube.com/shorts/abc123"]
    assert phone.find_links({"key": "https://gizli.example"}) == []   # anahtar alani taranmaz
    assert phone.find_links("x", raw="bak: https://a.b/c.zip.") == ["https://a.b/c.zip"]


def test_phone_send_variants_and_messages():
    srv, got = _srv()
    yt = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    code, r = srv.handle_send(json.dumps({"text": {"url": yt}}), "application/json", "anahtar123", "192.168.1.5")
    assert code == 200 and r["ok"] and r["message"].startswith("✓ Kuyruğa eklendi: ") and got == [yt]
    code, r = srv.handle_send(f"text={yt}&x=1", "application/x-www-form-urlencoded", "anahtar123", "1")
    assert r["ok"]
    code, r = srv.handle_send(yt, "text/plain", "anahtar123", "1")           # duz metin
    assert r["ok"]
    code, r = srv.handle_send(json.dumps([yt]), "", "anahtar123", "1")        # dizi, Content-Type yok
    assert r["ok"]
    code, r = srv.handle_send(json.dumps({"text": "Sadece başlık"}), "application/json", "anahtar123", "1")
    assert not r["ok"] and r["error"] == "no_link" and "Link bulunamadı" in r["message"] and "URL" in r["message"]
    assert srv.last["error"] == "no_link"
    code, r = srv.handle_send(json.dumps({"text": yt}), "application/json", "yanlis", "1")
    assert code == 401 and "X-Kami-Key" in r["message"]
    code, r = srv.handle_send(json.dumps({"text": yt, "key": "anahtar123"}), "application/json", "", "1")
    assert r["ok"]                                                            # tarayici: govdede anahtar


def test_phone_describe_hides_key():
    d = phone.describe({"key": "anahtar123", "text": "x" * 200}, "application/json", 240)
    assert "anahtar123" not in d and "***" in d and "alanlar=" in d


# ---------- soz ----------
def test_lyrics_write_paste_and_srt(tmp_path):
    f = tmp_path / "Sanatci - Sarki.mp3"
    f.write_bytes(b"")
    r = lyrics.write_lyrics(str(f), "satir 1\nsatir 2", "Sanatci", "Sarki", embed=False)
    assert r["lyrics"] == "plain" and r["txt"].endswith(".txt") and "satir 2" in open(r["txt"], encoding="utf-8").read()
    r = lyrics.paste(str(f), "[00:01.00]bir\n[00:02.50]iki", embed=False)
    assert r["lyrics"] == "synced" and open(r["lrc"], encoding="utf-8").read().startswith("[ar:Sanatci]")
    lrc = lyrics.srt_to_lrc("1\n00:01:02,500 --> 00:01:04,000\nmerhaba\n\n2\n00:00:03,000 --> 00:00:04,000\nselam\n")
    assert lrc == "[01:02.50]merhaba\n[00:03.00]selam"
    r = lyrics.write_lyrics(str(f), lrc, ai=True, embed=False)
    body = open(r["lrc"], encoding="utf-8").read()
    assert r["lyrics"] == "ai" and "hatalı olabilir" in body


def test_lyrics_plain_from_lrclib(tmp_path, monkeypatch):
    f = tmp_path / "A - B.mp3"
    f.write_bytes(b"")
    monkeypatch.setattr(lyrics, "lrclib_find", lambda *a, **k: {"synced": "", "plain": "tam soz", "instrumental": False})
    r = lyrics.fetch_for_file(str(f), embed=False)
    assert r["lyrics"] == "plain" and os.path.isfile(r["txt"])


# ---------- arsivci ----------
def test_guess_music_prefers_title_over_channel_tag(tmp_path, monkeypatch):
    f = tmp_path / "x.mp3"
    f.write_bytes(b"")
    from app.core import media_meta
    monkeypatch.setattr(media_meta, "read_tags", lambda p: {"artist": "madebykestek", "duration": 0.0, "album": "",
        "title": "Allame - EJDERHA | AI Music Video (Fan Made) | madebykestek"})
    g = musicarchive.guess_music(str(f), "", {"title": "Allame - EJDERHA | AI Music Video (Fan Made) | madebykestek",
                                              "channel": "madebykestek"})
    assert (g["artist"], g["title"]) == ("Allame", "EJDERHA")
    g = musicarchive.guess_music(str(f), "", {"artist": "Kum, Sansar Salvo", "track": "Kırmızı Reçete",
                                              "title": "whatever", "channel": "Kum - Topic"})
    assert (g["artist"], g["title"]) == ("Kum", "Kırmızı Reçete")


def test_archive_youtube_fallback(tmp_path, monkeypatch):
    f = tmp_path / "MRF - Yansın (Official Video).mp3"
    f.write_bytes(b"")
    monkeypatch.setattr(musicarchive, "lookup", lambda *a, **k: None)
    monkeypatch.setattr(musicarchive.media_meta, "write_mp3_tags", lambda *a, **k: True)
    r = musicarchive.archive(str(f), str(tmp_path / "M"), yt={"title": f.stem, "channel": "MRF", "year": "2024"})
    assert r["archive"] == "ok" and r["source"] == "youtube"
    assert r["path"].endswith(os.path.join("MRF", "Tekliler", "Yansın.mp3"))


# ---------- toplu link ----------
def test_bulk_page_links_hide_resources():
    html = ('<link href="/s/a.css"><script src="/x.js"></script><a href="/favicon.ico">i</a>'
            '<a href="/dl/film.mp4">v</a><a href="https://cdn.x/arsiv.zip">z</a><a href="#top">t</a>'
            '<a href="https://www.youtube.com/generate_204">g</a>')
    links = automate.page_anchor_links(html, "https://site.test/sayfa")
    shown = [u for u in links if not automate.is_resource(u)]
    assert shown == ["https://site.test/dl/film.mp4", "https://cdn.x/arsiv.zip"]


# ---------- AI arac onarimi ----------
def test_ai_needs_repair_stamp(tmp_path, monkeypatch):
    from app.core import aitools
    monkeypatch.setattr(aitools.paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(aitools, "installed", lambda n: True)
    assert aitools.needs_repair("whisper")                  # damga yok: eski kurulum -> onar
    aitools.models_dir("whisper")
    aitools._stamp_path("whisper").write_text(aitools._spec("whisper"), encoding="utf-8")
    assert not aitools.needs_repair("whisper")
    assert "av>=11,<19" in aitools._spec("whisper") and "audioread>=3" in aitools._spec("uvr")
    assert aitools.JOBS["lyrics"] == ("uvr", "whisper")
