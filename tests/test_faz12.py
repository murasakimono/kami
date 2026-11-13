"""Faz 12 testleri: sahne algilama, ReplayGain 2.0, beatgrid, kelime-senkronlu karaoke, audio FX & nota analizi."""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from app.core import audio_toolbox, kami_beat, scene_detect


def _make_sine_wav(path: Path, freq: float = 220.0, sec: float = 1.5, sr: int = 8000) -> None:
    n = int(sr * sec)
    frames = bytearray()
    for i in range(n):
        val = int(12000 * math.sin(2 * math.pi * freq * i / sr))
        frames.extend(struct.pack("<h", val))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(frames))


def test_word_sync_lyrics_and_beatgrid(tmp_path: Path):
    lrc = "[00:01.00]Gece sessiz sokaklar\n[00:04.00]Yagmur duser cama"
    synced = kami_beat.word_sync_lyrics(lrc, duration=8.0)
    assert len(synced) == 2
    assert [w["word"] for w in synced[0]["words"]] == ["Gece", "sessiz", "sokaklar"]
    assert synced[0]["words"][0]["start"] == 1.0
    assert synced[0]["words"][-1]["end"] == 4.0

    wav = tmp_path / "tone.wav"
    _make_sine_wav(wav, freq=220.0, sec=1.2)
    grid = kami_beat.build_beatgrid(str(wav), duration=10.0)
    assert grid["ok"] is True
    assert grid["bpm"] > 0
    assert len(grid["beats"]) >= 4
    assert len(grid["downbeats"]) >= 1
    assert len(grid["chords"]) == len(grid["downbeats"])


def test_audio_toolbox_fx_and_notes(tmp_path: Path):
    wav = tmp_path / "voice.wav"
    _make_sine_wav(wav, freq=220.0, sec=1.2)

    fx = audio_toolbox.apply_audio_fx(wav, tmp_path / "voice_fx.wav", preset="vocal_studio", reverb=0.15)
    if scene_detect._ffmpeg():
        assert fx["ok"] is True
        assert Path(fx["path"]).is_file()

        notes = audio_toolbox.audio_to_notes(wav)
        assert notes["ok"] is True
        assert len(notes["notes"]) >= 1
        # 220 Hz = A3 (MIDI 57)
        assert any(55 <= n["midi"] <= 59 for n in notes["notes"])

        rg = scene_detect.measure_replaygain(wav)
        assert rg["ok"] is True
        assert "gain_db" in rg and "linear_gain" in rg


def test_player_pro_js_contains_worklet_and_shaders():
    js = Path("app/ui/web/player-pro.js").read_text(encoding="utf-8")
    assert "AudioWorkletProcessor" in js
    assert "KamiDspProcessor" in js
    assert "KrigBilateral" in js
    assert "SSimSuperRes" in js
    assert "KamiPlayerPro" in js
