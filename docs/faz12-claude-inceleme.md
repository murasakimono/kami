# Faz 12 — Claude İnceleme Özeti (`1.20.0-dev`)

## Kapsam (Çakışmasız Faz 12)
Mevcut `player-extra.js` (CAS+Deband shader), `player-music.js` (satır bazlı karaoke) ve `kami_beat.py` (BPM/tonalite/mashup) üzerine şu yeni özellikler eklendi:

1. **12.1 Sahne Haritası & `libplacebo`-Sınıfı WebGL2 Shader (`app/core/scene_detect.py`, `app/ui/web/player-pro.js`):**
   - `detect_scenes()`: `PySceneDetect` varsa onu, yoksa FFmpeg `select='gt(scene,...)',showinfo` filtresiyle sahne geçişlerini çıkarır.
   - `player-pro.js`: `KrigBilateral` (kenar korumalı keskinleştirme), `SSimSuperRes` (lokal kontrast/mikro detay) ve `Adaptive Deband + Film Grain` GLSL profilleri.

2. **12.2 WebAudio `AudioWorklet` Canlı DSP & ReplayGain 2.0 (`app/core/scene_detect.py`, `app/ui/web/player-pro.js`):**
   - `measure_replaygain()`: FFmpeg `ebur128=peak=true` ile EBU R128 entegre LUFS + true-peak ölçümü ve kırpma korumalı lineer kazanç hesabı.
   - `player-pro.js`: Inline `Blob` üzerinden `KamiDspProcessor` (`AudioWorkletProcessor`) + 2.8 kHz diyalog netleştirme filtresi (`setDialogueClarity`) + perde kaydırma (`setPitchSemitones`).

3. **12.3 Kelime-Senkronlu Karaoke, Beatgrid & Görselleştirici (`app/core/kami_beat.py`, `app/ui/web/player-pro.js`):**
   - `build_beatgrid()`: BPM, tonalite, beat/downbeat zaman damgaları ve ölçülük akor haritası.
   - `word_sync_lyrics()`: LRC satırlarını kelime bazlı zaman damgalarına böler.
   - `startAudioVisualizer()`: `AnalyserNode` FFT verisiyle gerçek zamanlı spektrum çizer.

4. **12.4 `Kami Ses Kutusu` & 16-Adımlı Tarayıcı DAW (`app/core/audio_toolbox.py`, `app/ui/web/player-pro.js`):**
   - `apply_audio_fx()`: `pedalboard` varsa onu, yoksa FFmpeg `acompressor` + `aecho` + EQ zincirini uygular.
   - `audio_to_notes()`: `basic_pitch` varsa MIDI üretir, yoksa FFmpeg otokorelasyon ile nota/MIDI olayları çıkarır.
   - `synthesize_tts()`: `piper` CLI varsa onu, yoksa Windows SAPI (`System.Speech`) üzerinden çevrimdışı WAV üretir.
   - `player-pro.js`: `triggerDrum` / `startDaw` / `stopDaw` ile 16 adımlı WebAudio davul makinesi & bas synth.

5. **API & HTML (`app/ui/api.py`, `app/ui/web/player.html`):**
   - `player_detect_scenes`, `player_replaygain`, `beat_grid`, `lyrics_word_sync`, `audio_fx_apply`, `audio_to_midi`, `tts_speak` eklendi; `player-pro.js` `player.html` içine bağlandı.

## Doğrulama
- `pytest tests/test_faz7.py .. tests/test_faz12.py -v --basetemp=.pytest_tmp`: **23/23 passed**.
- Release notu: Kullanıcı talebi üzerine bu aşamada release alınmadı.
