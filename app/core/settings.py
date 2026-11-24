"""JSON tabanli ayarlar. Gizli bilgi (token vb.) buraya YAZILMAZ; onlar DPAPI ile ayri saklanir."""
from __future__ import annotations

import copy
import json
import logging
import threading
from pathlib import Path
from typing import Any

from app import paths

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "language": "tr",              # tr | en
    "theme": "dark",               # dark | light
    "accent_theme": "mor",         # mor | kizil | buz | altin | gece: tum arayuz (karakter dahil) bu renge doner
    "download_dir": "",            # bos = Windows Indirilenler klasoru
    "use_category_folders": True,  # Video, Muzik, Arsiv ... alt klasorleri
    "smart_series_folders": True,  # dizi bolumleri: Video/Diziler/<Dizi>/Sezon NN
    "connections": 16,             # dosya basina baglanti (aria2 en fazla 16)
    "max_concurrent": 3,           # ayni anda inen dosya sayisi
    "max_tries": 5,
    "speed_limit_kib": 0,          # 0 = sinirsiz (KiB/s, toplam)
    # Tarayici yakalama
    "capture_enabled": True,
    "capture_min_size_kib": 1024,  # bundan kucuk dosyalari tarayici indirsin (boyut biliniyorsa)
    "capture_exclude_hosts": [],   # ornek: ["example.com"]
    "confirm_extensions": ["exe", "msi", "apk", "bat", "cmd", "ps1", "scr", "vbs", "jar"],
    "notify_on_complete": True,    # Windows bildirimi (tepsi simgesi uzerinden)
    "notify_on_error": True,
    "clipboard_watch": True,       # desteklenen link kopyalaninca "indireyim mi?"
    # Medya (yt-dlp)
    "media_format": "mp4",         # mp4 | mp3
    "media_quality": "best",       # best | 2160 | 1440 | 1080 | 720 | 480 | 360
    "media_audio_kbps": 320,       # 320 | 256 | 192 | 128
    "media_subs": True,            # insan yapimi EN/TR altyazi gom (otomatik altyazi yok)
    "media_embed": True,           # kapak + etiket + bolum gom
    "media_sponsorblock": "mark",  # mark | remove | off
    "ytdlp_autoupdate": True,
    "ytdlp_last_update": 0,
    # Real-Debrid (token burada DEGIL: data/rd_token.bin, DPAPI)
    "rd_mode": "ask",              # RD destekli hoster + magnet/.torrent: auto | ask | off
    # Yerel torrent (aria2)
    "torrent_stop_seeding": True,  # indirme bitince paylasimi durdur (kapali: oran 1.0'a kadar paylas)
    "torrent_upload_limit_kib": 0, # 0 = sinirsiz (KiB/s, toplam)
    "torrent_port": 0,             # 0 = otomatik (6881-6999); degisiklik Kami yeniden acilinca gecerli
    "torrent_port_last": 0,        # otomatikte bir kez secilen port (DHT/guvenlik duvari icin sabit kalsin)
    "torrent_tracker_update": True,# guncel herkese acik izleyici listesini gunde bir indir
    # Asama 6a: uygulama temelleri
    "tray_enabled": True,          # sistem tepsisi simgesi (bildirimler de bunun uzerinden)
    "close_to_tray": True,         # X: kapatma yerine tepsiye gizle
    "autostart": False,            # Windows'la baslama (HKCU Run; tepside baslar)
    "hotkey_enabled": True,
    "hotkey": "ctrl+alt+k",        # genel kisayol: Kami'yi one getir + panodaki linki sor
    "speed_limit_preset_kib": 2048,# arac cubugundaki "hiz siniri" dugmesinin degeri
    "speed_profile": "full",       # baglam hiz profili: full | game | room | night (o an etkin olan)
    "speed_profile_manual": "full",# kullanicinin ELLE sectigi profil; Oda/oyun otomatik profili bunu kalici bozmaz
    "speed_profiles": {"full": 0, "game": 12288, "room": 40960, "night": 4096},
    "pano_shelf_record": True,     # v1.31.2: kopyalanan metin/linkler Pano rafina (parola yoneticisi kopyalari haric)
    "pano_exclude_apps": ["keepass", "bitwarden", "1password", "enpass", "lastpass", "dashlane"],
    "prewarm_player": False,       # v2.5: acilista ~100 MB bos Player WebView2 acmaz; ayardan acilabilir
    "integrity_check": True,       # v1.29: bitince dosya saglam mi (arsiv test, video bas+son cozum, boyut)
    "integrity_redownload": True,  # bozuksa bir kez otomatik yeniden indir
    "schedule_enabled": False,     # zamanlayici: baslangicta tumunu surdur, bitiste duraklat
    "schedule_start": "02:00",
    "schedule_stop": "08:00",
    "defender_mode": "exec_archive",  # off | exec_archive (calistirilabilir + arsiv) | all
    "checksum_verify": True,       # site/link SHA256 verdiyse indirme bitince dogrula
    "update_check": True,          # GitHub Releases'ta yeni surum var mi (gunde bir)
    "update_last": 0,
    "update_channel": "stable",    # stable | beta (GitHub prerelease)
    "auto_backup": True,           # haftada bir otomatik .kamibak yedegi (son 4'u tut)
    "auto_backup_last": 0,
    # Gorsel efektler & animasyonlar (hepsi ayarlardan acilip kapatilabilir)
    "sunak_bg_mode": "obsidian",   # obsidian (GLSL) | spirit_fire (Ruh Atesi GLSL) | particles (klasik parcacik) | off
    "ui_transitions": True,        # View Transitions + komut satirindan halkaya enerji kivilcimi
    "kamify_ambiance": True,       # Kamify kapak rengine uyumlu dinamik arka plan ambiyansi
    "games_tilt": True,            # Kami Games kartlarinda fare takipli 3D egim + krom yansima
    "card_ripple": False,          # Kartlarda hover'da hafif isik dalgasi (ripppl esinli; acilip kapanabilir)
    "advanced_micro_animations": True,  # Gelişmiş mikro-animasyonlar (elastic/lift/particle gather)
    "motion_magnet": False,
    "motion_mesh": False,
    "motion_grain": False,
    "motion_scramble": False,        # A1: metin cozumleme (indirme bitince dosya adi glif glif oturur)
    "motion_skeleton": False,        # A2: iskelet parilti yukleyici (liste dolarken yer tutucu satirlar)
    "motion_gooey": False,           # A3: sivi (gooey) filtre (tek konteyner/toast kabı)
    "motion_shared": False,          # A4: shared-element gecisi (kart gorseli -> Player acilisi)
    "motion_dirpanel": False,        # A5: yonlu panel itme (sag cekmeceler)
    "motion_refract": False,         # A6: cam kirilmasi (medya karti hover)
    "motion_nixie": False,           # A7: parcacik tozu + bitis kivilcimi (Sunak)
    "reader_page_anim": "curl3d",  # Kami Reader sayfa cevirme: curl3d | slide | off
    "sunak_kamify_sync": False,    # Kamify calarken kapak rengini Sunak arka planina hafifce yansit
    "island_music_expand": True,   # Kamify Mini-Ada: ustune gelince kapak rengiyle genisleyen Dinamik Ada (secilebilir)
    "high_contrast": False,        # Okunabilirlik modu (Fikir 9): yuksek kontrast + renk yerine desen/simge; varsayilan kapali
    # Ag: bazi sunucularin IPv6 adresi bu agda cevapsiz (RD: 21 sn x adres). Kapali = aria2 sadece IPv4.
    "aria2_ipv6": False,           # degisiklik Kami yeniden acilinca gecerli
    # Asama 6b: medya ekstralari
    "lyrics_auto": True,           # muzik inince LRCLIB'den soz (.lrc + MP3'e gom); yoksa Genius/AZLyrics linki
    "lyrics_embed": True,
    "lyrics_ai": False,            # 0.8.1: varsayilan KAPALI (sormadan GB'lik UVR+Whisper calistirmasin)
    "acoustid_key": "",            # istege bagli AcoustID uygulama anahtari (acoustid.org/new-application); gizli degil             # soz bulunamazsa UVR vokal + Whisper ile yaziya dok (iki arac kuruluysa)
    "listenbrainz_token": "",      # ListenBrainz scrobbling token'i (dinlenen sarkilari kaydetmek icin; bos = kapali)
    "music_archive": False,        # MusicBrainz etiket + Sanatci/Album klasoru + kapak
    "music_dir": "",               # Muzik kutuphanesi klasoru; bos = Indirilenler\Muzik (Dopamine bu klasoru izler)
    "whisper_auto": False,         # altyazisi olmayan videoya otomatik Whisper altyazi
    "whisper_lang": "auto",        # auto | tr | en
    "whisper_model": "large-v3-turbo",
    "whisper_embed": True,         # uretilen altyaziyi videoya yumusak iz olarak gom
    "uvr_auto": False,             # muzik inince otomatik vokal ayir
    "uvr_model": "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
    "uvr_format": "mp3",           # mp3 | flac | wav
    "social_cookies": True,        # Instagram/X/TikTok oturum cerezlerini eklentiden al (hikaye/ozel)
    "follow_enabled": True,        # kanal/liste takibi
    "follow_interval_min": 60,     # kontrol araligi (dk)
    # Asama 6c: kullanim
    "rules_enabled": True,         # site kurallari (rules.py)
    "site_rules": [],              # bos liste ilk acilista rules.DEFAULT_RULES ile doldurulur
    "rules_seeded": False,
    "auto_extract": False,         # arsiv inince ac (7-Zip varsa her bicim, yoksa sadece zip)
    "auto_extract_delete": False,  # acildiysa arsivi (ve parcalarini) sil
    "music_move": False,           # muzigi muzik klasorune tasi (arsivci kapaliyken)
    "disk_warn": True,             # dosya diske sigmayacaksa indirme baslamadan uyar
    "shutdown_when_done": False,   # kuyruk bitince bilgisayari KAPAT (tek seferlik, 60 sn iptal edilebilir)
    "link_refresh": True,          # suresi dolan RD/bulut linkini yenileyip kaldigi yerden devam
    "phone_enabled": False,        # telefondan gonder (yerel ag, gizli anahtar)
    "phone_port": 47390,
    "history_enabled": True,       # gecmis + arama
    "history_warn": True,          # daha once indirilen linkte uyar
    "ntfy_enabled": False,         # telefona bildirim (ntfy; konu DPAPI'de)
    "ntfy_server": "https://ntfy.sh",
    "ntfy_each": False,            # her indirme bitince
    "ntfy_queue": True,            # kuyruk bitince
    "ntfy_errors": True,           # hata olunca
    "watch_min_mb": 20,            # inerken izle: oynatici acilmadan once bastan inmis olmasi gereken MB
    "watch_player": "kami",        # kami (Kami Player) | screenbox | default
    "iptv_lists": [],              # v1.28: son acilan m3u listeleri (yol ya da URL)
    "studio_automation": True,     # v1.26: Otomasyon klasorune birakilan dosyalari isle
    "uvr_quality": "fast",         # fast (overlap 2 + fp16, ~3x) | balanced | best (overlap 8, gercek zamanli)
    "library_dirs": [],
    "mini_card": True,
    "auto_mirror": True,           # coklu kaynak: SourceForge / Metalink aynalarindan da cek
    "song_hotkey_enabled": True,   # "Bu sarki ne?" genel kisayolu (bilgisayardan cikan sesi dinler)
    "song_hotkey": "ctrl+shift+s",
    "lens_hotkey_enabled": True,
    "lens_hotkey": "ctrl+shift+l",   # Kami Lens: ekrandan alan secip ara
    "rec_replay_enabled": True,      # arka planda son 30 sn tamponu (ddagrab + NVENC, FPS'e etkisi dusuk)
    "rec_replay_seconds": 30,
    "rec_replay_hotkey": "alt+f10",
    "rec_record_hotkey": "alt+f9",
    "rec_fps": 60,
    "rec_mic": True,                 # mikrofon ayri ses izi
    "watch_name": "",                # Kami Oda: odada gorunen ad (bos -> OS kullanici adi)
    "room_id": "",                   # sabit oda anahtari (ilk acilista uretilir)
    "room_worker_url": "",           # sabit adres: https://kami-oda.<hesap>.workers.dev (anahtar DPAPI: room_worker.bin)
    "room_password_hash": "",        # oda sifresi: sha256(sifre) (sifrenin kendisi saklanmaz); bos = sifresiz
    "room_island": True,             # odadayken Mini-Ada'da oda seridi (konusanlar + mikrofon), Discord oyun ici gibi
    "room_always": True,             # sabit adres varsa Kami acikken oda hep acik (Ilayda istedigi zaman girer)
    "room_mute_hotkey": "ctrl+shift+m",   # Kami Oda acikken genel kisayollar
    "room_deaf_hotkey": "ctrl+shift+d",
    "room_ptt_key": "",              # bas-konus genel tusu (bos: yalnizca oda penceresi odaktayken)
    "chain_grab_ghost": False,       # Grab-All bitince Ghost metadata temizle
    "chain_rec_studio": False,       # Ekran kaydi bitince Studio'da ac
    "grab_follow_profiles": [],      # Grab-All takip edilen profiller
    "player_skip_silence": False,    # Player sessizlik atlayici (2x) — player-extra.js plToggleSilenceSkip ile bagli
    "player_rtx_vsr": False,         # Player donanim RTX VSR modu (Sinema HD > RTX VSR secenegi; WebGL kapatir)
    "player_resume_audio": False,    # Player: muzik/ses icin "kaldigi yerden devam" (varsayilan kapali; video hep devam eder)
    # Faz 7: Profil izolasyonu ve Masaustu Mini-Ada
    "active_profile": "kisisel",     # kisisel | icerik | magaza | ozel profil id
    "mini_island": False,            # masaustu mini-ada seridi
    # Kami 2.0 (v2.0.0) yeni ayarlar
    "rec_cursor_zoom": True,         # B5: Ekran kaydedicide tiklama noktasina yayli imlec zoom'u (acilip kapanabilir)
    "studio_safe_zone": False,       # B7: Kami Studio'da TikTok/Reels/Shorts guvenli alan maskesi (acilip kapanabilir)
    "media_dearrow": False,          # C10: DeArrow clickbait baslik & kapak duzeltici (acilip kapanabilir)
    "janitor_enabled": False,        # C9: Hazel 6 tarzi otomatik klasor bekcisi (aktif indirmelere dokunmaz)
    "oracle_relay_url": "",          # Dalga 5: Oracle Cloud (Frankfurt) sifreli Kami Relay adresi
    "oracle_relay_secret": "",       # Dalga 5: Oracle Relay HMAC-SHA256 paylasimli gizli anahtar
    "scrobbler_enabled": False,      # B8: Arka plan sistem sesi sarki gunlugu
    "scrobbler_hotkey": "ctrl+shift+g",  # B8: 10 sn'lik Ctrl+Shift+S'ten farkli kisayol (main.py:1020 okur)
    "whisper_strong_song": True,     # MP3 Whisper Guclu Sarki Modu (UVR5 vokal + condition_on_previous_text=False + esnek VAD)
    "cleaner_weekly_notify": True,   # Cleaner haftalik guvenli onbellek esik bildirimi
    # Dalga 1 (v2.5+): RAM Optimizasyonu & Oyun Kalkani
    "ram_instant_unload": True,      # kapatilan alt modullerin WebView2 bellegini aninda bosalt
    "game_shield_enabled": True,     # oyun acilinca bos pencereleri + Sunak GPU animasyonunu uyut (aktif ise dokunmaz)
    "game_shield_profiles": {
        "cs2.exe": "competitive",
        "league of legends.exe": "competitive",
        "valorant-win64-shipping.exe": "competitive",
    },
    # Dalga 2 (v2.5+): Oynatici, Ses Dengeleme & Discord Rich Presence
    "player_engine": "html5",        # html5 | libmpv (opsiyonel harici/gomulu mpv motoru)
    "player_loudness_norm": False,   # acilip kapanabilir -14 LUFS ses seviyesi dengeleyici
    "player_target_lufs": -14.0,     # hedef ses siddeti (LUFS)
    "discord_rp_enabled": False,     # opsiyonel Discord Rich Presence (oynatilan medya)
    # Kami Beat (Revize R2): kalici kayit gecikmesi (ms). Projede ayri deger girilmemisse her yeni kayda uygulanir.
    "beat_latency_ms": 0.0,          # -500..500; pozitif = kayit klibi o kadar sola (erkene) kaydirilir
}


class Settings:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or paths.SETTINGS_PATH
        self._lock = threading.RLock()
        self._data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self._listeners: list = []
        self.load()

    def load(self) -> None:
        with self._lock:
            if self.path.exists():
                try:
                    stored = json.loads(self.path.read_text(encoding="utf-8-sig"))
                    if isinstance(stored, dict):
                        for k, v in stored.items():
                            if k in DEFAULTS:
                                if k == "reader_page_anim" and isinstance(v, bool):
                                    v = "curl3d" if v else "off"
                                elif k == "speed_profiles" and isinstance(v, dict):
                                    merged = dict(DEFAULTS["speed_profiles"])
                                    for pk, pv in v.items():
                                        try:
                                            merged[str(pk)] = max(0, int(pv))
                                        except Exception:
                                            pass
                                    if merged.get("room") == 8192:   # 2.5.7: eski varsayilan 8 MB/s -> 40 MB/s (1 Gbit hatta gereksiz kisiyordu)
                                        merged["room"] = 40960
                                    v = merged
                                try:
                                    self._data[k] = _coerce(k, v)
                                except (ValueError, TypeError):
                                    log.warning("Bozuk ayar degeri varsayilana dondu: %s", k)
                except Exception:
                    log.exception("Ayarlar okunamadi, varsayilanlar kullaniliyor")
                    try:   # v2.5.3: bozuk dosyayi yedekle; ilk set() kullanicinin ayarlarini sessizce silmesin
                        import shutil
                        import time as _t
                        shutil.copy2(self.path, self.path.with_name(f"settings.bozuk-{int(_t.time())}.json"))
                    except OSError:
                        pass

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if key in self._data:
                return copy.deepcopy(self._data[key])
            return default

    def all(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(f"Bilinmeyen ayar: {key}")
        value = _coerce(key, value)
        with self._lock:
            self._data[key] = value
            self.save()
        for cb in list(self._listeners):
            try:
                cb(key, value)
            except Exception:
                log.exception("Ayar dinleyicisi hata verdi")

    def on_change(self, cb) -> None:
        self._listeners.append(cb)


def _coerce(key: str, value: Any) -> Any:
    default = DEFAULTS[key]
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, int):
        v = int(value)
        if key == "connections":
            v = max(1, min(16, v))
        elif key == "max_concurrent":
            v = max(1, min(20, v))
        elif key == "torrent_port" and not (v == 0 or 1024 <= v <= 65535):
            raise ValueError("torrent_port")
        elif key == "follow_interval_min":
            v = max(10, min(24 * 60, v))
        elif key == "phone_port" and not (1024 <= v <= 65535):
            raise ValueError("phone_port")
        elif key == "watch_min_mb":
            v = max(2, min(500, v))
        elif v < 0:
            v = 0
        return v
    if key == "site_rules":
        from app.core.rules import clean_rule
        if not isinstance(value, list):
            raise ValueError("site_rules")
        return [clean_rule(r) for r in value if isinstance(r, dict)][:50]
    if isinstance(default, dict):
        if not isinstance(value, dict):
            raise ValueError(key)
        if key == "speed_profiles":
            merged = dict(default)
            for pk, pv in value.items():
                merged[str(pk)] = max(0, int(pv))
            return merged
        if key == "game_shield_profiles":
            merged = dict(default)
            for gk, gv in value.items():
                k_clean = str(gk or "").strip().lower()
                if not k_clean:
                    continue
                v_clean = str(gv or "story").strip().lower()
                if v_clean not in ("competitive", "story", "off"):
                    v_clean = "story"
                merged[k_clean] = v_clean
            return merged
        return dict(value)
    if key == "reader_page_anim":
        if isinstance(value, bool):
            return "curl3d" if value else "off"
        sv = str(value).strip().lower()
        if sv not in ("curl3d", "slide", "off"):
            raise ValueError("reader_page_anim")
        return sv
    if key in ("speed_profile", "speed_profile_manual") and str(value) not in ("full", "game", "room", "night"):
        raise ValueError(key)
    if isinstance(default, list):
        if isinstance(value, str):
            value = [x.strip() for x in value.replace("\n", ",").split(",")]
        return [str(x).strip().lower() for x in value if str(x).strip()]
    if key == "rd_mode" and str(value) not in ("auto", "ask", "off"):
        raise ValueError("rd_mode")
    if key == "defender_mode" and str(value) not in ("off", "exec_archive", "all"):
        raise ValueError("defender_mode")
    if key == "whisper_lang" and str(value) not in ("auto", "tr", "en"):
        raise ValueError("whisper_lang")
    if key == "uvr_format" and str(value) not in ("mp3", "flac", "wav"):
        raise ValueError("uvr_format")
    if key == "watch_player" and str(value) not in ("kami", "screenbox", "default"):
        raise ValueError("watch_player")
    if key == "player_engine" and str(value) not in ("html5", "libmpv"):
        raise ValueError("player_engine")
    if key == "player_target_lufs":
        return max(-30.0, min(-5.0, float(value)))
    if key == "beat_latency_ms":
        if isinstance(value, bool):
            raise ValueError("beat_latency_ms")
        v = float(value)
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError("beat_latency_ms")
        return round(max(-500.0, min(500.0, v)), 3)
    if key == "ntfy_server" and not str(value).startswith(("https://", "http://")):
        raise ValueError("ntfy_server")
    if key in ("schedule_start", "schedule_stop"):
        from app.core.extras import _hm
        _hm(value)   # gecersizse ValueError
        h, m = str(value).strip().split(":")
        return f"{int(h):02d}:{m}"
    if key == "hotkey":
        from app.core.desktop import parse_hotkey
        parse_hotkey(str(value))
        return str(value).strip().lower().replace(" ", "")
    return str(value)
