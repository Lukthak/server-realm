import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import ctypes
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

# Cuando el .exe se relanza con --realm, ejecuta el juego directamente
if "--realm" in sys.argv:
    sys.argv.remove("--realm")
    from realm import main as _realm_main  # type: ignore
    _realm_main()
    sys.exit(0)

if sys.platform == "win32":
    import winreg


def _radiohaven_dir() -> Path:
    """Carpeta persistente en Documentos del usuario: ~/Documents/RadioHeaven"""
    docs = Path.home() / "Documents"
    d = docs / "RadioHeaven"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ffplay_candidates() -> list[Path]:
    candidates: list[Path] = []

    # Primero buscar en ~/Documents/RadioHeaven/ffmpeg/
    candidates.append(_radiohaven_dir() / "ffmpeg" / "ffplay.exe")

    if getattr(sys, "frozen", False):
        app_dir = Path(sys.executable).resolve().parent
        candidates.extend([app_dir / "ffplay.exe", app_dir / "ffmpeg" / "ffplay.exe"])
        if hasattr(sys, "_MEIPASS"):
            meipass = Path(getattr(sys, "_MEIPASS"))
            candidates.extend([meipass / "ffplay.exe", meipass / "ffmpeg" / "ffplay.exe"])
    else:
        app_dir = Path(__file__).resolve().parent
        candidates.extend([app_dir / "ffplay.exe", app_dir / "ffmpeg" / "ffplay.exe"])
        # ffplay junto al workspace (carpeta hermana de Radio/)
        candidates.append(app_dir.parent / "ffmpeg" / "ffplay.exe")

    system_ffplay = shutil.which("ffplay")
    if system_ffplay:
        candidates.append(Path(system_ffplay))

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)

    return unique


def _find_ffplay() -> Path | None:
    return next((candidate for candidate in _ffplay_candidates() if candidate.exists()), None)


# URL del build LGPL mínimo de ffmpeg para Windows 64-bit
_FFPLAY_ZIP_URL = (
    "https://github.com/BtbN/ffmpeg-builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-lgpl.zip"
)


def _auto_download_ffplay(on_progress, on_done) -> None:
    """Descarga ffplay.exe en Documents/RadioHeaven/ffmpeg/ sin preguntar.
    on_progress(pct, label) se llama desde el hilo de descarga via root.after.
    on_done(path_or_none) se llama al terminar.
    """
    dest = _radiohaven_dir() / "ffmpeg" / "ffplay.exe"
    dest.parent.mkdir(parents=True, exist_ok=True)

    result: list = [None]
    errors: list = []

    def _worker() -> None:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            def _progress(count, block, total):
                if total > 0:
                    pct = min(100, count * block * 100 // total)
                    mb_done = count * block / 1_048_576
                    mb_total = total / 1_048_576
                    on_progress(pct, f"Descargando ffplay... {mb_done:.0f}/{mb_total:.0f} MB")

            urllib.request.urlretrieve(_FFPLAY_ZIP_URL, tmp_path, _progress)
            on_progress(100, "Extrayendo ffplay.exe...")

            with zipfile.ZipFile(tmp_path) as zf:
                for name in zf.namelist():
                    if name.endswith("/ffplay.exe") or name == "ffplay.exe":
                        dest.write_bytes(zf.read(name))
                        result[0] = dest
                        break

            if result[0] is None:
                errors.append("ffplay.exe no encontrado en el .zip.")
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            on_done(result[0] if not errors else None)

    threading.Thread(target=_worker, daemon=True).start()


DEFAULT_STATIONS = {
    "Aspen 102.3": "https://playerservices.streamtheworld.com/api/livestream-redirect/ASPEN.mp3",
    "Nacional Clasica 96.7": "http://sa.mp3.icecast.magma.edge-access.net:7200/sc_rad37",
    "FM Kahoku": "http://radio.kahoku.net:8000/",
    "Yumi Co Radio": "https://yumicoradio.net/stream",
    "Japan City Pop": "https://play.streamafrica.net/japancitypop",
}


class RadioApp:
    def __init__(self, root: tk.Tk, ffplay_path: "Path | None" = None) -> None:
        self.root = root
        self.root.title("Radio Heaven")
        self.root.geometry("350x350")
        self.root.resizable(False, False)
        self.root.configure(bg="#6f1d1b")
        self._icon_image: tk.PhotoImage | None = None
        self._set_window_icon()
        self.ffplay_path = ffplay_path if ffplay_path is not None else _find_ffplay()
        self.ffplay_process: subprocess.Popen | None = None
        self.vlc_error_message = ""
        if self.ffplay_path is None:
            self.vlc_error_message = self._vlc_failure_message()

        self.use_registry_store = bool(getattr(sys, "frozen", False) and sys.platform == "win32")
        self.stations_file = Path(__file__).resolve().parent / "stations.json"
        self.stations = self._load_stations()
        self.current_station_name: str | None = None
        self.current_stream_url: str | None = None
        self.is_paused = False
        self.stats_job: str | None = None
        self.stream_started = threading.Event()
        self.stream_probe_stop = threading.Event()
        self.stream_probe_thread: threading.Thread | None = None
        self.prev_read_bytes: int | None = None
        self.prev_stats_time: float | None = None
        self.smoothed_speed_kb = 0.0
        self.last_stream_title = ""
        self.meta_thread: threading.Thread | None = None
        self.meta_stop = threading.Event()
        self.meta_lock = threading.Lock()
        self.selected_station_var = tk.StringVar(value="Selecciona una radio")
        self.station_anim_job: str | None = None
        self.station_anim_step = 0
        self.station_colors = (
            "#ff3b3b",
            "#ff8a00",
            "#ffd000",
            "#71d64f",
            "#28c6ff",
            "#4b7dff",
            "#b05cff",
            "#ff4fd8",
        )

        self.status_var = tk.StringVar(value="Listo")
        self.speed_var = tk.StringVar(value="Offline")
        self.song_var = tk.StringVar(value="")
        self._sleep_blocked = False
        self._realm_process: subprocess.Popen | None = None
        self._realm_ip: str = "159.223.107.32"

        self._build_ui()

    def _vlc_available(self) -> bool:
        return self.ffplay_path is not None

    def _ffplay_running(self) -> bool:
        return self.ffplay_process is not None and self.ffplay_process.poll() is None

    def _stop_ffplay(self) -> None:
        if not self._ffplay_running():
            self.ffplay_process = None
            return

        assert self.ffplay_process is not None
        self.ffplay_process.terminate()
        try:
            self.ffplay_process.wait(timeout=1.2)
        except subprocess.TimeoutExpired:
            self.ffplay_process.kill()
            self.ffplay_process.wait(timeout=1.2)
        finally:
            self.ffplay_process = None

    def _start_ffplay(self, stream_url: str) -> bool:
        if self.ffplay_path is None:
            return False

        command = [
            str(self.ffplay_path),
            "-nodisp",
            "-autoexit",
            "-loglevel",
            "quiet",
            "-vn",
            stream_url,
        ]

        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        self.ffplay_process = subprocess.Popen(command, **kwargs)
        time.sleep(0.35)
        if self.ffplay_process.poll() is not None:
            self.ffplay_process = None
            return False

        return True

    def _vlc_failure_message(self) -> str:
        searched = "\n".join(str(path) for path in _ffplay_candidates())
        return (
            "No se encontro ffplay para reproducir audio.\n\n"
            "Incluye la carpeta ffmpeg junto al ejecutable.\n"
            "Debe existir ffmpeg/ffplay.exe.\n\n"
            f"Rutas revisadas:\n{searched}"
        )

    def _set_window_icon(self) -> None:
        base = Path(__file__).resolve().parent
        icon_candidates = (
            base / "ICONO.png",
            base / "icono.png",
            base / "__pycache__" / "ICONO.png",
        )

        icon_path = next((path for path in icon_candidates if path.exists()), None)
        if icon_path is None:
            return

        try:
            self._icon_image = tk.PhotoImage(file=str(icon_path))
            icon_for_title = self._icon_image
            width = max(1, self._icon_image.width())
            height = max(1, self._icon_image.height())
            scale = max(1, width // 32, height // 32)
            if scale > 1:
                icon_for_title = self._icon_image.subsample(scale, scale)

            self.root.iconphoto(True, icon_for_title)
            self._icon_image = icon_for_title
        except Exception:  # noqa: BLE001
            self._icon_image = None

    def _build_ui(self) -> None:
        main = tk.Frame(self.root, bg="#6f1d1b", padx=12, pady=12)
        main.pack(fill="both", expand=True)

        top_row = tk.Frame(main, bg="#6f1d1b")
        top_row.pack(fill="x")

        tk.Label(
            top_row,
            text="Emisoras guardadas",
            font=("Segoe UI", 11, "bold"),
            bg="#6f1d1b",
            fg="#f7e7a9",
        ).pack(side="left", anchor="w")

        self.station_title_label = tk.Label(
            top_row,
            textvariable=self.selected_station_var,
            font=("Segoe UI", 10, "bold"),
            bg="#6f1d1b",
            fg="#ff3b3b",
            anchor="e",
        )
        self.station_title_label.pack(side="right", anchor="e", padx=(8, 0))

        list_frame = tk.Frame(main, bg="#6f1d1b", bd=2, relief="solid")
        list_frame.pack(fill="both", expand=True, pady=(6, 10))

        self.listbox = tk.Listbox(
            list_frame,
            activestyle="dotbox",
            font=("Segoe UI", 10),
            height=12,
            bg="#d4af37",
            fg="#4a0f12",
            selectbackground="#6f1d1b",
            selectforeground="#f7e7a9",
            highlightthickness=0,
            bd=0,
        )
        self.listbox.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=scrollbar.set)

        for name in self.stations:
            self.listbox.insert("end", name)

        controls = tk.Frame(main, bg="#6f1d1b")
        controls.pack(pady=(0, 10))

        self.play_pause_btn = ttk.Button(controls, text="▶", width=3, command=self.toggle_play_pause)
        self.play_pause_btn.pack(side="left")
        ttk.Button(controls, text="+", width=3, command=self.add_station).pack(side="left", padx=6)
        ttk.Button(controls, text="-", width=3, command=self.remove_station).pack(side="left")

        bottom_row = tk.Frame(main, bg="#6f1d1b")
        bottom_row.pack(fill="x", pady=(2, 0))
        tk.Label(
            bottom_row,
            textvariable=self.speed_var,
            font=("Segoe UI", 9, "bold"),
            bg="#6f1d1b",
            fg="#f7e7a9",
        ).pack(side="left")
        realm_lbl = tk.Label(
            bottom_row,
            text="REALM",
            font=("Segoe UI", 9, "bold"),
            bg="#6f1d1b",
            fg="#f7e7a9",
            cursor="hand2",
        )
        realm_lbl.pack(side="right")
        realm_lbl.bind("<Button-1>", lambda _e: self._launch_realm())

        self.listbox.bind("<Double-1>", lambda _event: self.toggle_play_pause())
        self.listbox.bind("<<ListboxSelect>>", self.on_station_selected)
        self.listbox.bind("<Up>", self._block_arrow_keys)
        self.listbox.bind("<Down>", self._block_arrow_keys)
        self.listbox.bind("<Left>", self._block_arrow_keys)
        self.listbox.bind("<Right>", self._block_arrow_keys)
        self.root.bind_all("<Up>", self._block_arrow_keys)
        self.root.bind_all("<Down>", self._block_arrow_keys)
        self.root.bind_all("<Left>", self._block_arrow_keys)
        self.root.bind_all("<Right>", self._block_arrow_keys)
        self.root.bind("<F12>", lambda _e: self._change_realm_ip())
        self._animate_station_title()
        self._schedule_speed_update()

    def _block_arrow_keys(self, _event: tk.Event) -> str:
        return "break"

    def _load_stations(self) -> dict[str, str]:
        if self.use_registry_store:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\RadioHeaven") as key:
                    payload, _ = winreg.QueryValueEx(key, "stations_json")
                data = json.loads(payload)
            except Exception:  # noqa: BLE001
                return dict(DEFAULT_STATIONS)

            if not isinstance(data, dict):
                return dict(DEFAULT_STATIONS)

            loaded: dict[str, str] = {}
            for name, url in data.items():
                if isinstance(name, str) and isinstance(url, str):
                    clean_name = name.strip()
                    clean_url, _ = self._normalize_url(url)
                    if clean_name and clean_url.startswith(("http://", "https://")):
                        loaded[clean_name] = clean_url

            return loaded or dict(DEFAULT_STATIONS)

        if not self.stations_file.exists():
            return dict(DEFAULT_STATIONS)

        try:
            data = json.loads(self.stations_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return dict(DEFAULT_STATIONS)

        if not isinstance(data, dict):
            return dict(DEFAULT_STATIONS)

        loaded: dict[str, str] = {}
        for name, url in data.items():
            if isinstance(name, str) and isinstance(url, str):
                clean_name = name.strip()
                clean_url, _ = self._normalize_url(url)
                if clean_name and clean_url.startswith(("http://", "https://")):
                    loaded[clean_name] = clean_url

        return loaded or dict(DEFAULT_STATIONS)

    def _save_stations(self) -> None:
        if self.use_registry_store:
            try:
                payload = json.dumps(self.stations, ensure_ascii=False)
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\RadioHeaven") as key:
                    winreg.SetValueEx(key, "stations_json", 0, winreg.REG_SZ, payload)
            except Exception:  # noqa: BLE001
                self.status_var.set("Error al guardar emisoras")
            return

        try:
            payload = json.dumps(self.stations, ensure_ascii=False, indent=2)
            self.stations_file.write_text(payload, encoding="utf-8")
        except Exception:  # noqa: BLE001
            self.status_var.set("Error al guardar emisoras")

    def _animate_station_title(self) -> None:
        color = self.station_colors[self.station_anim_step % len(self.station_colors)]
        self.station_title_label.configure(fg=color)

        wave = self.station_anim_step % 20
        if wave > 10:
            wave = 20 - wave
        x_pad = 2 + wave
        self.station_title_label.pack_configure(padx=(x_pad, 0))

        self.station_anim_step += 1
        self.station_anim_job = self.root.after(95, self._animate_station_title)

    def _update_play_pause_button(self) -> None:
        self.play_pause_btn.config(text="▶" if self.is_paused else "⏸")

    def _format_speed(self, kb_per_second: float) -> str:
        return f"{kb_per_second:.1f}"

    def _set_speed_smooth(self, target_kb: float, factor: float = 0.28) -> None:
        self.smoothed_speed_kb += (target_kb - self.smoothed_speed_kb) * factor
        if self.smoothed_speed_kb < 0.05:
            self.smoothed_speed_kb = 0.0
        self.speed_var.set(self._format_speed(self.smoothed_speed_kb))

    def _schedule_speed_update(self) -> None:
        self._update_stream_speed()
        self._update_song_title()
        self.stats_job = self.root.after(350, self._schedule_speed_update)

    def _set_sleep_prevention(self, enabled: bool) -> None:
        if sys.platform != "win32":
            return

        if enabled == self._sleep_blocked:
            return

        es_continuous = 0x80000000
        es_system_required = 0x00000001
        es_display_required = 0x00000002

        if enabled:
            ctypes.windll.kernel32.SetThreadExecutionState(
                es_continuous | es_system_required | es_display_required
            )
            self._sleep_blocked = True
            return

        ctypes.windll.kernel32.SetThreadExecutionState(es_continuous)
        self._sleep_blocked = False

    def _update_song_title(self) -> None:
        if not self._vlc_available():
            self.song_var.set("")
            return

        if self.current_station_name is None or self.is_paused or not self._ffplay_running():
            self.song_var.set("")
            return

        with self.meta_lock:
            title = self.last_stream_title
        self.song_var.set(title if title else "Online")

    def _recv_exact(self, sock: socket.socket, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            chunk = sock.recv(size - len(data))
            if not chunk:
                break
            data.extend(chunk)
        return bytes(data)

    def _read_with_buffer(self, sock: socket.socket, buffered: bytearray, size: int) -> bytes:
        while len(buffered) < size:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buffered.extend(chunk)

        if size <= 0:
            return b""

        out = bytes(buffered[:size])
        del buffered[:size]
        return out

    def _fetch_stream_title_once(self, stream_url: str, redirects_left: int = 3) -> str:
        parsed = urlparse(stream_url)
        if not parsed.hostname or parsed.scheme not in ("http", "https"):
            return ""

        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        headers = (
            f"GET {path} HTTP/1.0\r\n"
            f"Host: {host}\r\n"
            "Icy-MetaData: 1\r\n"
            "Connection: close\r\n"
            "User-Agent: RadioHeaven/1.0\r\n\r\n"
        ).encode("ascii", errors="ignore")

        with socket.create_connection((host, port), timeout=6) as conn:
            conn.settimeout(6)
            if parsed.scheme == "https":
                context = ssl.create_default_context()
                sock = context.wrap_socket(conn, server_hostname=host)
            else:
                sock = conn

            sock.sendall(headers)

            raw_headers = bytearray()
            while b"\r\n\r\n" not in raw_headers and len(raw_headers) < 32768:
                chunk = sock.recv(1024)
                if not chunk:
                    return ""
                raw_headers.extend(chunk)

            header_part, body_start = bytes(raw_headers).split(b"\r\n\r\n", maxsplit=1)
            header_text = header_part.decode("latin-1", errors="ignore")

            status_line = ""
            header_map: dict[str, str] = {}
            header_lines = header_text.split("\r\n")
            if header_lines:
                status_line = header_lines[0].strip()
            for line in header_lines[1:]:
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                header_map[key.strip().lower()] = value.strip()

            if status_line.startswith("HTTP/"):
                parts = status_line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    code = int(parts[1])
                    if code in (301, 302, 303, 307, 308) and redirects_left > 0:
                        location = header_map.get("location", "")
                        if location:
                            next_url = urljoin(stream_url, location)
                            return self._fetch_stream_title_once(next_url, redirects_left - 1)

            metaint = 0
            metaint_raw = header_map.get("icy-metaint", "")
            if metaint_raw:
                try:
                    metaint = int(metaint_raw)
                except ValueError:
                    metaint = 0

            if metaint <= 0:
                return ""

            buffered = bytearray(body_start)
            audio_block = self._read_with_buffer(sock, buffered, metaint)
            if len(audio_block) < metaint:
                return ""

            length_byte = self._read_with_buffer(sock, buffered, 1)
            if not length_byte:
                return ""

            metadata_length = length_byte[0] * 16
            if metadata_length <= 0:
                return ""

            metadata = self._read_with_buffer(sock, buffered, metadata_length)
            if len(metadata) < metadata_length:
                return ""

        text = metadata.decode("latin-1", errors="ignore")
        match = re.search(r"StreamTitle='([^']*)';", text)
        if not match:
            return ""

        title = match.group(1).strip()
        return title

    def _metadata_worker(self, stream_url: str) -> None:
        while not self.meta_stop.is_set():
            title = ""
            try:
                title = self._fetch_stream_title_once(stream_url)
            except Exception:  # noqa: BLE001
                title = ""

            if title:
                with self.meta_lock:
                    self.last_stream_title = title
                self.stream_started.set()

            for _ in range(20):
                if self.meta_stop.is_set():
                    return
                time.sleep(0.5)

    def _stop_metadata_worker(self) -> None:
        self.meta_stop.set()
        if self.meta_thread is not None and self.meta_thread.is_alive():
            self.meta_thread.join(timeout=0.3)
        self.meta_thread = None

    def _start_metadata_worker(self, stream_url: str) -> None:
        self._stop_metadata_worker()
        with self.meta_lock:
            self.last_stream_title = ""
        self.meta_stop = threading.Event()
        self.meta_thread = threading.Thread(
            target=self._metadata_worker,
            args=(stream_url,),
            daemon=True,
        )
        self.meta_thread.start()

    def _probe_stream_started_once(self, stream_url: str, redirects_left: int = 3) -> bool:
        parsed = urlparse(stream_url)
        if not parsed.hostname or parsed.scheme not in ("http", "https"):
            return False

        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        headers = (
            f"GET {path} HTTP/1.0\r\n"
            f"Host: {host}\r\n"
            "Connection: close\r\n"
            "User-Agent: RadioHeaven/1.0\r\n\r\n"
        ).encode("ascii", errors="ignore")

        with socket.create_connection((host, port), timeout=6) as conn:
            conn.settimeout(6)
            if parsed.scheme == "https":
                context = ssl.create_default_context()
                sock = context.wrap_socket(conn, server_hostname=host)
            else:
                sock = conn

            sock.sendall(headers)

            raw_headers = bytearray()
            while b"\r\n\r\n" not in raw_headers and len(raw_headers) < 32768:
                chunk = sock.recv(1024)
                if not chunk:
                    return False
                raw_headers.extend(chunk)

            header_part, body_start = bytes(raw_headers).split(b"\r\n\r\n", maxsplit=1)
            header_text = header_part.decode("latin-1", errors="ignore")

            status_line = ""
            location = ""
            header_lines = header_text.split("\r\n")
            if header_lines:
                status_line = header_lines[0].strip()

            for line in header_lines[1:]:
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                if key.strip().lower() == "location":
                    location = value.strip()

            if status_line.startswith("HTTP/"):
                parts = status_line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    code = int(parts[1])
                    if code in (301, 302, 303, 307, 308) and redirects_left > 0 and location:
                        next_url = urljoin(stream_url, location)
                        return self._probe_stream_started_once(next_url, redirects_left - 1)

            if body_start:
                return True

            first_byte = sock.recv(1)
            return bool(first_byte)

    def _stream_probe_worker(self, stream_url: str) -> None:
        while not self.stream_probe_stop.is_set() and not self.stream_started.is_set():
            started = False
            try:
                started = self._probe_stream_started_once(stream_url)
            except Exception:  # noqa: BLE001
                started = False

            if started:
                self.stream_started.set()
                return

            for _ in range(5):
                if self.stream_probe_stop.is_set() or self.stream_started.is_set():
                    return
                time.sleep(0.2)

    def _stop_stream_probe(self) -> None:
        self.stream_probe_stop.set()
        if self.stream_probe_thread is not None and self.stream_probe_thread.is_alive():
            self.stream_probe_thread.join(timeout=0.3)
        self.stream_probe_thread = None

    def _start_stream_probe(self, stream_url: str) -> None:
        self._stop_stream_probe()
        self.stream_started.clear()
        self.stream_probe_stop = threading.Event()
        self.stream_probe_thread = threading.Thread(
            target=self._stream_probe_worker,
            args=(stream_url,),
            daemon=True,
        )
        self.stream_probe_thread.start()

    def _update_stream_speed(self) -> None:
        if not self._vlc_available():
            self.stream_started.clear()
            self.prev_read_bytes = None
            self.prev_stats_time = None
            self.speed_var.set("Offline")
            return

        if self.current_station_name is None:
            self.stream_started.clear()
            self.prev_read_bytes = None
            self.prev_stats_time = None
            self.speed_var.set("Offline")
            return

        if self.is_paused:
            self.stream_started.clear()
            self.prev_read_bytes = None
            self.prev_stats_time = None
            self.speed_var.set("Pausado")
            return

        if not self._ffplay_running():
            self.stream_started.clear()
            self.prev_read_bytes = None
            self.prev_stats_time = None
            self.speed_var.set("Offline")
            return

        if self.stream_started.is_set():
            self.speed_var.set("LIVE")
            return

        self.speed_var.set("Cargando...")

    def _check_host_reachable(self, url: str) -> tuple[bool, str]:
        parsed = urlparse(url)
        if not parsed.hostname:
            return False, "No se pudo detectar el host de la URL."

        if parsed.scheme == "https":
            port = parsed.port or 443
        else:
            port = parsed.port or 80

        try:
            with socket.create_connection((parsed.hostname, port), timeout=5):
                return True, ""
        except OSError as error:
            return False, f"No hay conexion con {parsed.hostname}:{port}. {error}"

    def _normalize_url(self, raw_url: str) -> tuple[str, bool]:
        cleaned = raw_url.strip().replace(" ", "")
        corrected = False

        fixes = (
            ("http://playhttps://", "https://"),
            ("https://playhttps://", "https://"),
            ("http://playhttp://", "http://"),
            ("https://playhttp://", "http://"),
            ("playhttps://", "https://"),
            ("playhttp://", "http://"),
        )

        lowered = cleaned.lower()
        for prefix, replacement in fixes:
            if lowered.startswith(prefix):
                cleaned = replacement + cleaned[len(prefix):]
                corrected = True
                break

        if cleaned.lower().startswith("www."):
            cleaned = f"https://{cleaned}"
            corrected = True

        return cleaned, corrected

    def _play_url(self, url: str, label: str) -> bool:
        if not self._vlc_available():
            messagebox.showerror(
                "Audio no disponible",
                self.vlc_error_message or "No se encontro ffplay para reproducir audio.",
            )
            return False

        cleaned, _ = self._normalize_url(url)
        if not cleaned.startswith(("http://", "https://")):
            messagebox.showerror("URL invalida", "El link debe comenzar con http:// o https://")
            return False

        reachable, reason = self._check_host_reachable(cleaned)
        if not reachable:
            self.status_var.set("Error de red/host")
            messagebox.showerror(
                "Host sin conexion",
                f"No se pudo abrir el servidor de la radio.\n\n{reason}\n\n"
                "Prueba otra emisora o revisa firewall/VPN/antivirus.",
            )
            return False

        try:
            # Al detener antes de cambiar emisora evitamos interrupciones ruidosas en consola.
            self._stop_ffplay()
            started = self._start_ffplay(cleaned)
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("Error", f"No se pudo iniciar la reproduccion.\n{error}")
            return False

        if not started:
            messagebox.showerror(
                "Error de audio",
                "No se pudo iniciar la reproduccion con ffplay.",
            )
            return False

        self.current_station_name = label
        self.current_stream_url = cleaned
        self.is_paused = False
        self.stream_started.clear()
        self.prev_read_bytes = None
        self.prev_stats_time = None
        self.smoothed_speed_kb = 0.0
        self.speed_var.set("Cargando...")
        self._update_play_pause_button()
        self.status_var.set(f"Reproduciendo: {label}")
        self.song_var.set("Online")
        self._start_stream_probe(cleaned)
        self._start_metadata_worker(cleaned)
        self._set_sleep_prevention(True)
        return True

    def _resume_current(self) -> None:
        if not self._vlc_available():
            return

        if self.current_station_name is None or not self.current_stream_url:
            return

        if not self._start_ffplay(self.current_stream_url):
            self.status_var.set("Error al reanudar")
            return

        self.prev_read_bytes = None
        self.prev_stats_time = None
        self.smoothed_speed_kb = 0.0
        self.stream_started.clear()
        self.speed_var.set("Cargando...")
        self.is_paused = False
        self._update_play_pause_button()
        self.status_var.set(f"Reproduciendo: {self.current_station_name}")
        self.song_var.set("Online")
        self._start_stream_probe(self.current_stream_url)
        self._start_metadata_worker(self.current_stream_url)
        self._set_sleep_prevention(True)

    def _change_realm_ip(self) -> None:
        new_ip = simpledialog.askstring(
            "REALM - Servidor",
            "IP del servidor REALM:",
            initialvalue=self._realm_ip,
            parent=self.root,
        )
        if new_ip is not None:
            self._realm_ip = new_ip.strip()

    def _launch_realm(self) -> None:
        self.root.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() + 4
        titlebar_h = self.root.winfo_rooty() - self.root.winfo_y()
        y = self.root.winfo_y() - titlebar_h
        env = os.environ.copy()
        env["SDL_VIDEO_WINDOW_POS"] = f"{x},{y}"
        env["REALM_SERVER_IP"] = self._realm_ip
        no_window = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        if getattr(sys, "frozen", False):
            self._realm_process = subprocess.Popen([sys.executable, "--realm"], env=env)
        else:
            base = Path(__file__).resolve().parent.parent
            realm_path = base / "REALM" / "realm.py"
            if not realm_path.exists():
                messagebox.showerror("REALM", f"No se encontró realm.py en:\n{realm_path}")
                return
            self._realm_process = subprocess.Popen([sys.executable, str(realm_path)], env=env, **no_window)

    def _pause_current(self) -> None:
        if not self._vlc_available():
            return

        self._stop_ffplay()
        self.is_paused = True
        self.stream_started.clear()
        self.speed_var.set("Pausado")
        self._update_play_pause_button()
        if self.current_station_name:
            self.status_var.set(f"Pausado: {self.current_station_name}")
        else:
            self.status_var.set("Pausado")
        self.song_var.set("")
        self._stop_stream_probe()
        self._stop_metadata_worker()
        self._set_sleep_prevention(False)

    def _play_station(self, name: str) -> None:
        self.selected_station_var.set(name)
        self._play_url(self.stations[name], name)

    def toggle_play_pause(self) -> None:
        selected = self.listbox.curselection()
        if not selected:
            messagebox.showinfo("Sin seleccion", "Selecciona una emisora de la lista.")
            return

        name = self.listbox.get(selected[0])
        if self.current_station_name != name:
            self._play_station(name)
            return

        if self.is_paused:
            self._resume_current()
            return

        self._pause_current()

    def on_station_selected(self, _event: tk.Event) -> None:
        selected = self.listbox.curselection()
        if not selected:
            return

        selected_name = self.listbox.get(selected[0])
        self.selected_station_var.set(selected_name)
        if selected_name != self.current_station_name:
            self._play_station(selected_name)

    def stop_playback(self) -> None:
        if self._vlc_available():
            self._stop_ffplay()
        self.is_paused = True
        self.stream_started.clear()
        self.prev_read_bytes = None
        self.prev_stats_time = None
        self.speed_var.set("Offline")
        self._update_play_pause_button()
        self.status_var.set("Detenido")
        self.song_var.set("")
        self.current_stream_url = None
        self._stop_stream_probe()
        self._stop_metadata_worker()
        self._set_sleep_prevention(False)

    def add_station(self) -> None:
        name = simpledialog.askstring("Nombre", "Nombre de la emisora:", parent=self.root)
        if not name:
            return

        url = simpledialog.askstring("Link", "URL del stream:", parent=self.root)
        if not url:
            return

        clean_name = name.strip()
        clean_url, _ = self._normalize_url(url)
        if not clean_name or not clean_url:
            messagebox.showerror("Dato invalido", "Nombre y URL son obligatorios.")
            return

        if not clean_url.startswith(("http://", "https://")):
            messagebox.showerror("URL invalida", "La URL de la emisora debe comenzar con http:// o https://")
            return

        self.stations[clean_name] = clean_url
        if clean_name not in self.listbox.get(0, "end"):
            self.listbox.insert("end", clean_name)
        self._save_stations()
        self.status_var.set(f"Agregada: {clean_name}")

    def remove_station(self) -> None:
        selected = self.listbox.curselection()
        if not selected:
            messagebox.showinfo("Sin seleccion", "Selecciona una emisora para eliminar.")
            return

        index = selected[0]
        station_name = self.listbox.get(index)
        confirmed = messagebox.askyesno(
            "Confirmar eliminacion",
            f"(!) Vas a eliminar la emisora:\n\n{station_name}\n\nDeseas continuar?",
            parent=self.root,
        )
        if not confirmed:
            return

        self.listbox.delete(index)
        self.stations.pop(station_name, None)
        self._save_stations()

        if self.current_station_name == station_name:
            self.stop_playback()
            self.current_station_name = None
            self.selected_station_var.set("Selecciona una radio")

        self.status_var.set(f"Eliminada: {station_name}")


def _set_app_icon(win: tk.Tk) -> None:
    """Aplica ICONO.png como icono de ventana."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, "_MEIPASS", str(base)))
        icon_candidates = (meipass / "ICONO.png", base / "ICONO.png")
    else:
        base = Path(__file__).resolve().parent
        icon_candidates = (base / "ICONO.png", base / "icono.png")

    icon_path = next((p for p in icon_candidates if p.exists()), None)
    if icon_path is None:
        return
    try:
        img = tk.PhotoImage(file=str(icon_path))
        w, h = max(1, img.width()), max(1, img.height())
        scale = max(1, w // 32, h // 32)
        if scale > 1:
            img = img.subsample(scale, scale)
        win.iconphoto(True, img)
        win._icon_ref = img  # evitar garbage collection
    except Exception:  # noqa: BLE001
        pass


def _show_download_splash() -> "Path | None":
    """Muestra un mini popup de descarga y retorna el path a ffplay o None."""
    splash = tk.Tk()
    splash.title("Radio Heaven")
    splash.resizable(False, False)
    splash.configure(bg="#6f1d1b")
    splash.geometry("260x56")
    _set_app_icon(splash)
    splash.eval("tk::PlaceWindow . center")

    lbl_var = tk.StringVar(value="Descargando ffplay...")
    tk.Label(splash, textvariable=lbl_var, bg="#6f1d1b", fg="#f7e7a9",
             font=("Segoe UI", 9)).pack(pady=(10, 4))
    bar = ttk.Progressbar(splash, length=220, mode="determinate")
    bar.pack()

    result: list = [None]

    def _on_progress(pct, label):
        splash.after(0, lambda p=pct, l=label: (
            bar.configure(value=p),
            lbl_var.set(l),
        ))

    def _on_done(path):
        result[0] = path
        splash.after(0, splash.destroy)

    _auto_download_ffplay(_on_progress, _on_done)
    splash.mainloop()
    return result[0]


def main() -> None:
    ffplay = _find_ffplay()
    if ffplay is None:
        ffplay = _show_download_splash()

    root = tk.Tk()
    app = RadioApp(root, ffplay_path=ffplay)

    def on_close() -> None:
        if app.stats_job is not None:
            root.after_cancel(app.stats_job)
            app.stats_job = None
        if app.station_anim_job is not None:
            root.after_cancel(app.station_anim_job)
            app.station_anim_job = None
        app.stop_playback()
        app._set_sleep_prevention(False)
        if app._realm_process is not None and app._realm_process.poll() is None:
            app._realm_process.terminate()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
