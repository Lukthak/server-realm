import queue
import random
import socket
import subprocess
import sys
import threading
import time
import math
import tkinter as tk
import tkinter.messagebox as mb
from pathlib import Path

import pygame
try:
    import numpy as np
except Exception:
    np = None

from config import (SERVER_IP, SERVER_PORT,
                    WIDTH, HEIGHT, MAP_WIDTH, MAP_HEIGHT, FPS, ICONO_PATH)
from dialogs import (ask_nickname, get_user_position, save_user_position,
                     get_user_bio, save_user_bio, open_bio_dialog,
                     get_user_max_chunks, save_user_max_chunks,
                     get_user_skin, save_user_skin,
                     get_user_map_markers, save_user_map_markers,
                     check_server_or_exit)
from hud import (draw_debug, draw_minimap, draw_profile_panel,
                 draw_players, draw_local_player, load_icon)
from net import UDPLink
from ping_test import start_monitor
from sonda import Sonda, SPRITE_NAMES, _load_sprite
from universe import Universe


def _local_server_running() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 5556), timeout=1):
            return True
    except Exception:
        return False


def _start_local_server() -> None:
    """Lanza server.py en una nueva consola si no está corriendo."""
    if _local_server_running():
        print("[LOCAL] Servidor ya en ejecución.")
        return
    server_path = str(Path(__file__).parent / "server.py")
    subprocess.Popen(
        [sys.executable, server_path],
        creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )
    print("[LOCAL] Servidor iniciado — esperando...")
    for _ in range(15):          # hasta 3 segundos
        time.sleep(0.2)
        if _local_server_running():
            print("[LOCAL] Servidor listo.")
            return
    print("[LOCAL] Advertencia: el servidor tardó más de lo esperado.")


def main():
    print(f"Servidor: {SERVER_IP}:{SERVER_PORT}")
    check_server_or_exit()

    _ping_down = threading.Event()
    _is_local = SERVER_IP in ("127.0.0.1", "localhost", "::1")
    if _is_local:
        _start_local_server()
        _ping_stop = threading.Event()
        _ping_stats: dict = {"tcp_ms": 0.0}
        print("[PING] Servidor local — monitor desactivado.")
    else:
        _ping_stop, _ping_stats = start_monitor(on_offline=_ping_down.set)

    nickname = ask_nickname()

    pygame.init()
    click_sounds: list[pygame.mixer.Sound] = []

    def _make_pitch_variant(base_sound: pygame.mixer.Sound, pitch_factor: float):
        if np is None or abs(pitch_factor - 1.0) < 0.0001:
            return base_sound
        try:
            arr = pygame.sndarray.array(base_sound)
            if arr is None or len(arr) < 8:
                return base_sound

            src_len = arr.shape[0]
            new_len = max(8, int(src_len / pitch_factor))
            old_x = np.arange(src_len)
            new_x = np.linspace(0, src_len - 1, new_len)

            if arr.ndim == 1:
                pitched = np.interp(new_x, old_x, arr)
            else:
                channels = []
                for ci in range(arr.shape[1]):
                    channels.append(np.interp(new_x, old_x, arr[:, ci]))
                pitched = np.stack(channels, axis=1)

            pitched = np.clip(pitched, -32768, 32767).astype(np.int16)
            return pygame.sndarray.make_sound(pitched)
        except Exception:
            return base_sound

    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        sounds_dir = Path(__file__).parent / "sounds"
        for snd_path in sorted(sounds_dir.glob("click*.wav")):
            try:
                base = pygame.mixer.Sound(str(snd_path))
                # Variacion suave de pitch (+/- pocos porcentajes)
                for pf in (0.97, 0.99, 1.00, 1.01, 1.03):
                    click_sounds.append(_make_pitch_variant(base, pf))
            except Exception:
                pass
    except Exception:
        click_sounds = []

    def _play_type_click() -> None:
        if not click_sounds:
            return
        try:
            snd = random.choice(click_sounds)
            ch = snd.play()
            if ch is not None:
                ch.set_volume(random.uniform(0.39, 0.50))
        except Exception:
            pass

    icon = load_icon(ICONO_PATH)
    if icon:
        pygame.display.set_icon(icon)
    is_fullscreen = False
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    render_surface = pygame.Surface((WIDTH, HEIGHT)).convert_alpha()

    def _compute_viewport(win_w: int, win_h: int):
        scale = min(win_w / WIDTH, win_h / HEIGHT)
        vw = max(1, int(WIDTH * scale))
        vh = max(1, int(HEIGHT * scale))
        vx = (win_w - vw) // 2
        vy = (win_h - vh) // 2
        return vx, vy, vw, vh

    def _to_virtual(pos):
        mx, my = pos
        win_w, win_h = screen.get_size()
        vx, vy, vw, vh = _compute_viewport(win_w, win_h)
        if vw <= 0 or vh <= 0:
            return None
        if mx < vx or my < vy or mx >= vx + vw or my >= vy + vh:
            return None
        sx = (mx - vx) / vw
        sy = (my - vy) / vh
        return int(sx * WIDTH), int(sy * HEIGHT)

    def _wrap_chat_lines(text: str, max_width: int):
        if not text:
            return [""]
        lines = []
        cur = ""
        for ch in text:
            test = cur + ch
            if nick_font.size(test)[0] <= max_width:
                cur = test
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
        return lines
    pygame.display.set_caption("REALM")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 14)
    nick_font = pygame.font.SysFont(None, 16)

    universe = Universe(MAP_WIDTH, MAP_HEIGHT, WIDTH, HEIGHT)
    start_x, start_y = get_user_position(nickname, MAP_WIDTH // 2, MAP_HEIGHT // 2)
    start_x += random.randint(-20, 20)
    start_y += random.randint(-20, 20)
    player = Sonda(start_x=start_x, start_y=start_y, speed=1.4)
    player.skin_index = get_user_skin(nickname) % len(player.sprites)
    player.image = player.sprites[player.skin_index]
    net = UDPLink()
    ghost_sprites = [_load_sprite(name) for name in SPRITE_NAMES]

    _visited_chunks: set = set()
    _chunks_all_time: int = get_user_max_chunks(nickname)
    total_chunks = _chunks_all_time
    _saved_map = get_user_map_markers(nickname)
    _discovered_stars: dict[str, dict] = {}
    _discovered_blackholes: dict[str, dict] = {}
    _map_markers_dirty = False
    _map_last_save_t = 0.0
    _MAP_SAVE_INTERVAL = 2.0

    def _marker_key(x: int, y: int) -> str:
        return f"{int(x)}:{int(y)}"

    def _to_map_star(raw: dict) -> dict | None:
        try:
            x = int(raw.get("x"))
            y = int(raw.get("y"))
            c = raw.get("color", [255, 255, 255])
            if not isinstance(c, (list, tuple)) or len(c) != 3:
                c = [255, 255, 255]
            color = [
                max(0, min(255, int(c[0]))),
                max(0, min(255, int(c[1]))),
                max(0, min(255, int(c[2]))),
            ]
            return {"x": x, "y": y, "color": color}
        except Exception:
            return None

    def _to_map_blackhole(raw: dict) -> dict | None:
        try:
            x = int(raw.get("x"))
            y = int(raw.get("y"))
            return {"x": x, "y": y}
        except Exception:
            return None

    for _s in _saved_map.get("stars", []):
        s = _to_map_star(_s) if isinstance(_s, dict) else None
        if s is None:
            continue
        _discovered_stars[_marker_key(s["x"], s["y"])] = s

    for _b in _saved_map.get("blackholes", []):
        b = _to_map_blackhole(_b) if isinstance(_b, dict) else None
        if b is None:
            continue
        _discovered_blackholes[_marker_key(b["x"], b["y"])] = b

    def _flush_map_markers(force: bool = False) -> None:
        nonlocal _map_markers_dirty, _map_last_save_t
        if not _map_markers_dirty:
            return
        now = time.time()
        if not force and (now - _map_last_save_t) < _MAP_SAVE_INTERVAL:
            return
        saved_ok = save_user_map_markers(
            nickname,
            list(_discovered_stars.values()),
            list(_discovered_blackholes.values()),
        )
        if saved_ok:
            _map_markers_dirty = False
            _map_last_save_t = now

    def _shutdown_and_exit():
        _flush_map_markers(force=True)
        save_user_position(nickname, player.x, player.y)
        save_user_max_chunks(nickname, total_chunks)
        save_user_skin(nickname, player.skin_index)
        net.disconnect()
        net.stop()
        pygame.quit()
        sys.exit()

    chat_msg: dict = {"text": "", "until": 0.0}
    chat_typing = False
    chat_input = ""
    chat_history: list[str] = []
    chat_hist_idx = 0
    chat_draft = ""
    pending_chat_msg = None

    cmd_console_open = False
    cmd_input = ""
    cmd_lines: list[str] = [
        "SPACE SHIP ADMINISTRATOR - help for info",
    ]
    cmd_visible_chars: list[int] = [0]
    cmd_type_last_t = time.time()
    CMD_TYPE_CPS = 119
    CMD_BOOT_DELAY = 1.0
    cmd_boot_until = 0.0
    cmd_input_enabled = False
    cmd_history: list[str] = []
    cmd_hist_idx = 0
    cmd_draft = ""

    debug = False
    map_open = False
    map_chunk_grid = False
    map_clicked_chunk: tuple[int, int] | None = None
    exit_confirm_presses = 0
    exit_after_confirm = False
    conn_error = False
    _popup_shown = threading.Event()
    MINIMAP_MAX_CHUNKS = 250
    minimap_range = 3000
    minimap_max_range = int(max(MAP_WIDTH, MAP_HEIGHT) * MINIMAP_MAX_CHUNKS)
    profile = None
    profile_open_t = 0.0
    PANEL_ANIM = 0.25
    profile_data: dict = {"bio": "", "max_dist": 0.0, "loading": False}
    profile_btn_rect = None
    bio_queue: queue.Queue = queue.Queue()
    bio_editing = threading.Event()
    cam_x = cam_y = 0
    admin_chunk = (0, 0)
    last_view_star: dict | None = None

    def _submit_chat_message(msg: str) -> None:
        nonlocal pending_chat_msg
        pending_chat_msg = msg

    def _process_action_command(raw_cmd: str) -> str:
        nonlocal map_open, cmd_console_open, profile, last_view_star
        parts = raw_cmd.strip().split()
        if not parts:
            return "ERR comando vacio"

        cmd = parts[0].lower()
        if cmd == "help":
            return "OK comandos: help | nave | ver | planetas | mapa | inventario | exit"

        if cmd == "nave":
            return (
                f"OK nave nick={nickname} pos=({int(player.x)}, {int(player.y)}) "
                f"vel={player.speed:.2f} ang={player.angle:.1f} skin={player.skin_index}"
            )

        if cmd == "ver":
            player_cx = player.x + getattr(player, "base_w", player.w) / 2.0
            player_cy = player.y + getattr(player, "base_h", player.h) / 2.0
            player_hit = max(getattr(player, "base_w", player.w), getattr(player, "base_h", player.h)) * 0.55 * 14.0
            player_close_hit = max(getattr(player, "base_w", player.w), getattr(player, "base_h", player.h)) * 0.40
            planet_infos = universe.get_planet_near_player(
                player_cx,
                player_cy,
                pygame.time.get_ticks() / 1000.0,
                footprint_radius=player_close_hit,
            )
            star_info = universe.get_star_under_player(player_cx, player_cy, footprint_radius=player_hit)
            bh_info = universe.get_blackhole_near_player(player_cx, player_cy, footprint_radius=player_hit)
            last_view_star = star_info if star_info else None

            lines: list[str] = []
            if planet_infos:
                lines.append("OK planetas cercanos:")
                for p in planet_infos:
                    lines.append(f"- {p['name']}")
                    lines.append(f"  - tamano: {p['size']:.2f}")
                    lines.append(f"  - lunas: {p['moons']}")

            if star_info:
                if lines:
                    lines.append("")
                lines.extend([
                    "OK sistema solar:",
                    f"- color: {star_info['kind']}",
                    f"- planetas: {star_info['planets']}",
                    f"- lunas totales: {star_info.get('moons', 0)}",
                ])

            if bh_info:
                if lines:
                    lines.append("")
                lines.extend([
                    "OK agujero negro cercano:",
                    f"- espirales: {bh_info['arms']}",
                    f"- estrellas del disco: {bh_info['star_count']}",
                    f"- tamano: {bh_info['radius']:.1f}",
                ])

            if not lines:
                return "solo estrellas"
            return "\n".join(lines)

        if cmd == "planetas":
            player_cx = player.x + getattr(player, "base_w", player.w) / 2.0
            player_cy = player.y + getattr(player, "base_h", player.h) / 2.0
            player_hit = max(getattr(player, "base_w", player.w), getattr(player, "base_h", player.h)) * 0.55 * 14.0
            current_star = universe.get_star_under_player(player_cx, player_cy, footprint_radius=player_hit)
            if current_star:
                last_view_star = current_star

            if not last_view_star:
                return "ERR ponte sobre una estrella o usa ver primero"

            moons_per_planet = list(last_view_star.get("moons_per_planet", []))
            sizes_per_planet = list(last_view_star.get("sizes_per_planet", []))
            if not moons_per_planet:
                return "OK esta estrella no tiene planetas"

            if len(moons_per_planet) == 8:
                planet_names = [
                    "Mercurion", "Venara", "Tierron", "Martis",
                    "Jupiron", "Saturnia", "Uranix", "Neptaris",
                ]
            else:
                planet_names = [f"Planeta {i + 1}" for i in range(len(moons_per_planet))]

            lines = ["OK planetas detectados:"]
            for i, moon_count in enumerate(moons_per_planet):
                pname = planet_names[i] if i < len(planet_names) else f"Planeta {i + 1}"
                psize = sizes_per_planet[i] if i < len(sizes_per_planet) else 0
                lines.append(f"- {pname}")
                lines.append(f"  - tamano: {float(psize):.2f}")
                lines.append(f"  - lunas: {moon_count}")
            return "\n".join(lines)

        if cmd == "mapa":
            map_open = True
            cmd_console_open = False
            profile = None
            return (
                f"OK mapa abierto chunk={admin_chunk} chunks_total={total_chunks} "
                "(pulsa I para volver al administrador)"
            )

        if cmd == "inventario":
            return "OK inventario no implementado (vacio)"

        return f"ERR comando desconocido: {cmd}"

    def _push_cmd_line(text: str, animate: bool = True) -> None:
        cmd_lines.append(text)
        cmd_visible_chars.append(0 if animate else len(text))
        if len(cmd_lines) > 240:
            overflow = len(cmd_lines) - 240
            del cmd_lines[:overflow]
            del cmd_visible_chars[:overflow]

    def _advance_cmd_typing() -> None:
        nonlocal cmd_type_last_t
        now = time.time()
        elapsed = now - cmd_type_last_t
        if elapsed <= 0.0:
            return
        to_add = int(elapsed * CMD_TYPE_CPS)
        if to_add <= 0:
            return
        cmd_type_last_t = now

        for i, line in enumerate(cmd_lines):
            current = cmd_visible_chars[i]
            full = len(line)
            if current >= full:
                continue
            grow = min(to_add, full - current)
            cmd_visible_chars[i] = current + grow
            to_add -= grow
            if to_add <= 0:
                break

    def _open_cmd_console() -> None:
        nonlocal cmd_console_open, cmd_input, cmd_type_last_t
        nonlocal cmd_hist_idx, cmd_draft, cmd_boot_until, cmd_input_enabled

        cmd_console_open = True
        cmd_input = ""
        cmd_hist_idx = len(cmd_history)
        cmd_draft = ""
        cmd_lines.clear()
        cmd_visible_chars.clear()
        _push_cmd_line("SPACE SHIP ADMINISTRATOR - help for info")
        cmd_boot_until = time.time() + CMD_BOOT_DELAY
        cmd_type_last_t = cmd_boot_until
        # Permitir escribir de inmediato aunque la animacion de arranque siga corriendo.
        cmd_input_enabled = True

    def _execute_cmd_console(text: str) -> None:
        nonlocal cmd_hist_idx, cmd_draft, cmd_console_open
        cmd = text.strip()
        if not cmd:
            return
        _push_cmd_line(f"> {cmd}")
        cmd_history.append(cmd)
        if len(cmd_history) > 100:
            del cmd_history[:-100]
        cmd_hist_idx = len(cmd_history)
        cmd_draft = ""

        if cmd.lower() in ("clear", "cls"):
            cmd_lines.clear()
            cmd_visible_chars.clear()
            _push_cmd_line("SPACE SHIP ADMINISTRATOR - help for info")
            return

        if cmd.lower() == "exit":
            cmd_console_open = False
            return

        result = _process_action_command(cmd)
        for line in str(result).splitlines() or [""]:
            _push_cmd_line(line)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _shutdown_and_exit()

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if exit_confirm_presses > 0:
                    continue
                if cmd_console_open:
                    continue
                mapped = _to_virtual(event.pos)
                if mapped is None:
                    continue
                mx, my = mapped
                if (profile and profile_btn_rect and
                        profile["name"] == nickname and
                        profile_btn_rect.collidepoint(mx, my) and
                        not bio_editing.is_set()):
                    bio_editing.set()
                    threading.Thread(
                        target=open_bio_dialog,
                        args=(bio_queue, bio_editing, profile_data["bio"]),
                        daemon=True,
                    ).start()
                elif map_open:
                    if map_chunk_grid:
                        scale_x = WIDTH / (2 * minimap_range)
                        scale_y = HEIGHT / (2 * minimap_range)
                        world_x = player.x + (mx - (WIDTH / 2)) / scale_x
                        world_y = player.y + (my - (HEIGHT / 2)) / scale_y
                        map_clicked_chunk = (
                            int(math.floor(world_x / MAP_WIDTH)),
                            int(math.floor(world_y / MAP_HEIGHT)),
                        )
                    else:
                        map_open = False
                else:
                    clicked = None
                    if pygame.Rect(int(player.x) - cam_x, int(player.y) - cam_y,
                                   player.w, player.h).collidepoint(mx, my):
                        clicked = {"name": nickname, "sprite": player.image, "chunks": total_chunks}
                    else:
                        for _pid, (rx, ry, _rangle, rskin, rchunks, rnick, _rchat) in net.get_others().items():
                            spr = ghost_sprites[int(rskin) % len(ghost_sprites)]
                            if pygame.Rect(int(rx) - cam_x, int(ry) - cam_y,
                                           spr.get_width(), spr.get_height()).collidepoint(mx, my):
                                clicked = {"name": rnick, "sprite": spr, "chunks": rchunks}
                                break
                    if clicked:
                        if profile is None or profile["name"] != clicked["name"]:
                            profile_open_t = time.time()
                            profile_data.update({"bio": "", "loading": True})
                            _pname = clicked["name"]
                            _is_own = _pname == nickname
                            _tc = total_chunks
                            _rc = clicked.get("chunks", 0)
                            def _load_profile(name=_pname, own=_is_own, tc=_tc, rc=_rc):
                                profile_data["bio"] = get_user_bio(name)
                                profile_data["max_dist"] = tc if own else rc
                                profile_data["loading"] = False
                            threading.Thread(target=_load_profile, daemon=True).start()
                        profile = clicked
                    else:
                        profile = None

            elif event.type == pygame.KEYDOWN:
                if cmd_console_open:
                    if event.key == pygame.K_ESCAPE:
                        cmd_console_open = False
                    elif event.key == pygame.K_RETURN:
                        _execute_cmd_console(cmd_input)
                        cmd_input = ""
                    elif event.key == pygame.K_BACKSPACE:
                        cmd_input = cmd_input[:-1]
                        _play_type_click()
                    elif event.key == pygame.K_UP:
                        if cmd_history:
                            if cmd_hist_idx == len(cmd_history):
                                cmd_draft = cmd_input
                            if cmd_hist_idx > 0:
                                cmd_hist_idx -= 1
                                cmd_input = cmd_history[cmd_hist_idx]
                    elif event.key == pygame.K_DOWN:
                        if cmd_history:
                            if cmd_hist_idx < len(cmd_history) - 1:
                                cmd_hist_idx += 1
                                cmd_input = cmd_history[cmd_hist_idx]
                            elif cmd_hist_idx == len(cmd_history) - 1:
                                cmd_hist_idx = len(cmd_history)
                                cmd_input = cmd_draft
                    else:
                        ch = event.unicode or ""
                        if ch.isprintable() and ch not in ("\r", "\n"):
                            if len(cmd_input) < 160:
                                cmd_input += ch
                                _play_type_click()
                    continue

                if exit_confirm_presses > 0:
                    if event.key == pygame.K_ESCAPE:
                        exit_confirm_presses += 1
                        if exit_confirm_presses >= 4:
                            exit_after_confirm = True
                    else:
                        exit_confirm_presses = 0
                    continue

                if map_open and event.key == pygame.K_i:
                    map_open = False
                    _open_cmd_console()
                    continue

                # Mientras se escribe, bloquear todas las demás teclas.
                if chat_typing:
                    if event.key == pygame.K_RETURN:
                        text = chat_input.strip()[:48]
                        if text:
                            chat_history.append(text)
                            if len(chat_history) > 50:
                                del chat_history[:-50]
                            _submit_chat_message(text)
                        chat_typing = False
                        chat_input = ""
                        chat_hist_idx = len(chat_history)
                        chat_draft = ""
                    elif event.key == pygame.K_ESCAPE:
                        chat_typing = False
                        chat_input = ""
                        chat_hist_idx = len(chat_history)
                        chat_draft = ""
                    elif event.key == pygame.K_BACKSPACE:
                        chat_input = chat_input[:-1]
                        _play_type_click()
                    elif event.key == pygame.K_UP:
                        if chat_history:
                            if chat_hist_idx == len(chat_history):
                                chat_draft = chat_input
                            if chat_hist_idx > 0:
                                chat_hist_idx -= 1
                                chat_input = chat_history[chat_hist_idx]
                    elif event.key == pygame.K_DOWN:
                        if chat_history:
                            if chat_hist_idx < len(chat_history) - 1:
                                chat_hist_idx += 1
                                chat_input = chat_history[chat_hist_idx]
                            elif chat_hist_idx == len(chat_history) - 1:
                                chat_hist_idx = len(chat_history)
                                chat_input = chat_draft
                    else:
                        ch = event.unicode or ""
                        if ch.isprintable() and ch not in ("\r", "\n"):
                            if len(chat_input) < 48:
                                chat_input += ch
                                _play_type_click()
                    continue

                if event.key == pygame.K_F3:
                    if map_open:
                        map_chunk_grid = not map_chunk_grid
                        if not map_chunk_grid:
                            map_clicked_chunk = None
                    else:
                        debug = not debug
                elif event.key == pygame.K_ESCAPE:
                    exit_confirm_presses = 1
                elif event.key == pygame.K_F11:
                    is_fullscreen = not is_fullscreen
                    if is_fullscreen:
                        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode((WIDTH, HEIGHT))
                elif event.key == pygame.K_m:
                    pass
                elif event.key == pygame.K_i:
                    _open_cmd_console()
                elif event.key == pygame.K_RETURN:
                    chat_typing = True
                    chat_input = ""
                    chat_hist_idx = len(chat_history)
                    chat_draft = ""

            elif event.type == pygame.MOUSEWHEEL and map_open:
                next_range = int(minimap_range * (0.8 if event.y > 0 else 1.25))
                minimap_range = max(100, min(minimap_max_range, next_range))

            if not chat_typing and not cmd_console_open:
                player.handle_event(event)

        if pending_chat_msg:
            msg = pending_chat_msg
            pending_chat_msg = None
            if msg:
                raw = str(msg).strip()
                cmd = raw.lower()
                if cmd == "/blackhole":
                    dest = universe.find_nearby_blackhole(player.x, player.y)
                    if dest:
                        player.x, player.y = float(dest[0]), float(dest[1])
                        chat_msg["text"] = ">> Viajando al black hole..."
                        chat_msg["until"] = time.time() + 3.0
                    else:
                        chat_msg["text"] = ">> No hay black holes cercanos"
                        chat_msg["until"] = time.time() + 3.0
                elif cmd == "/hub":
                    pw = getattr(player, "base_w", player.w)
                    ph = getattr(player, "base_h", player.h)
                    player.x = float(MAP_WIDTH // 2 - pw // 2)
                    player.y = float(MAP_HEIGHT // 2 - ph // 2)
                    player.vx = 0.0
                    player.vy = 0.0
                    chat_msg["text"] = ">> Regresaste al hub"
                    chat_msg["until"] = time.time() + 3.0
                elif cmd == "/sun":
                    dest = universe.find_nearby_sun(player.x, player.y)
                    if dest:
                        player.x, player.y = float(dest[0]), float(dest[1])
                        player.vx = 0.0
                        player.vy = 0.0
                        chat_msg["text"] = ">> Viajando a un sol cercano..."
                        chat_msg["until"] = time.time() + 3.0
                    else:
                        chat_msg["text"] = ">> No hay soles cercanos"
                        chat_msg["until"] = time.time() + 3.0
                elif cmd.startswith("/tp"):
                    parts = raw.split(maxsplit=1)
                    target_name = parts[1].strip() if len(parts) > 1 else ""
                    if not target_name:
                        chat_msg["text"] = ">> Uso: /tp nombre"
                        chat_msg["until"] = time.time() + 3.0
                    else:
                        target_key = target_name.lower()
                        found = None
                        for _pid, (rx, ry, _rangle, _rskin, _rchunks, rnick, _rchat) in net.get_others().items():
                            nick_clean = str(rnick).replace("\x00", "")
                            if nick_clean.lower() == target_key:
                                found = (float(rx), float(ry), nick_clean)
                                break

                        if found is None:
                            chat_msg["text"] = f">> Jugador no encontrado: {target_name}"
                            chat_msg["until"] = time.time() + 3.0
                        else:
                            player.x, player.y = found[0], found[1]
                            player.vx = 0.0
                            player.vy = 0.0
                            chat_msg["text"] = f">> Teleport a {found[2]}"
                            chat_msg["until"] = time.time() + 3.0
                else:
                    chat_msg["text"] = msg
                    chat_msg["until"] = float("inf")

        try:
            new_bio = bio_queue.get_nowait()
            if new_bio is not None:
                profile_data["bio"] = new_bio
                save_user_bio(nickname, new_bio)
                save_user_max_chunks(nickname, total_chunks)
        except queue.Empty:
            pass

        # Si hay error de conexión, congelar pantalla y esperar a que se cierre el popup
        if conn_error:
            if not _popup_shown.is_set():
                pygame.quit()
                sys.exit()
            pygame.display.flip()
            clock.tick(FPS)
            continue

        keys = pygame.key.get_pressed()
        if chat_typing or cmd_console_open or exit_confirm_presses > 0:
            keys = [False] * len(keys)
        if any(keys[k] for k in (pygame.K_w, pygame.K_s, pygame.K_a, pygame.K_d)):
            if chat_msg["text"] and chat_msg["until"] == float("inf"):
                chat_msg["until"] = time.time() + 5.0

        player.update(keys)
        chunk_coord = universe.update(player.x, player.y)
        admin_chunk = chunk_coord
        _visited_chunks.add(chunk_coord)
        total_chunks = _chunks_all_time + len(_visited_chunks)

        loaded_map = universe.get_loaded_map_markers()
        discovered_now = False
        for _raw_s in loaded_map.get("stars", []):
            s = _to_map_star(_raw_s)
            if s is None:
                continue
            key = _marker_key(s["x"], s["y"])
            prev = _discovered_stars.get(key)
            if prev is None or prev.get("color") != s["color"]:
                _discovered_stars[key] = s
                _map_markers_dirty = True
                discovered_now = True
        for _raw_b in loaded_map.get("blackholes", []):
            b = _to_map_blackhole(_raw_b)
            if b is None:
                continue
            key = _marker_key(b["x"], b["y"])
            if key not in _discovered_blackholes:
                _discovered_blackholes[key] = b
                _map_markers_dirty = True
                discovered_now = True
        if discovered_now:
            _flush_map_markers(force=True)
        else:
            _flush_map_markers()

        current_chat = chat_msg["text"] if time.time() < chat_msg["until"] else ""
        net.send(player.x, player.y, player.angle, player.skin_index, total_chunks, nickname,
                 "\x01" if chat_typing else current_chat)

        cam_x, cam_y = player.get_camera(WIDTH, HEIGHT)

        if map_open:
            draw_minimap(
                render_surface,
                player.x,
                player.y,
                net.get_others(),
                minimap_range,
                map_stars=list(_discovered_stars.values()),
                map_blackholes=list(_discovered_blackholes.values()),
                show_chunk_grid=map_chunk_grid,
                chunk_w=MAP_WIDTH,
                chunk_h=MAP_HEIGHT,
            )
            if map_chunk_grid:
                grid_txt = nick_font.render("F3 GRID ON - click para ver chunk", True, (110, 180, 110))
                render_surface.blit(grid_txt, (8, 8))
                if map_clicked_chunk is not None:
                    chunk_txt = nick_font.render(
                        f"chunk click: [{map_clicked_chunk[0]}, {map_clicked_chunk[1]}]",
                        True,
                        (150, 220, 150),
                    )
                    render_surface.blit(chunk_txt, (8, 8 + nick_font.get_height() + 2))
        else:
            universe.draw(render_surface, cam_x, cam_y)
            sun_tint_color, sun_tint_amount, player_brightness = universe.get_player_light()
            draw_players(render_surface, net.get_others(), cam_x, cam_y, nick_font, ghost_sprites)
            draw_local_player(render_surface, player, nickname, cam_x, cam_y, nick_font,
                              chat_typing, current_chat,
                              tint_color=sun_tint_color, tint_amount=sun_tint_amount,
                              brightness=player_brightness)
            if debug:
                draw_debug(render_surface, universe, cam_x, cam_y, font, chunk_coord, _ping_stats["tcp_ms"])

        if chat_typing:
            box_w = int(WIDTH * 0.58)
            line_h = nick_font.get_height() + 2
            inner_w = box_w - 16
            prompt = "> " + chat_input
            show_cursor = int(time.time() * 2) % 2 == 0
            if show_cursor:
                prompt += "_"
            lines = _wrap_chat_lines(prompt, inner_w)
            max_visible_lines = 4
            if len(lines) > max_visible_lines:
                lines = lines[-max_visible_lines:]
            box_h = 10 + line_h * len(lines)
            box_x = (WIDTH - box_w) // 2
            box_y = HEIGHT - box_h - 14
            box = pygame.Rect(box_x, box_y, box_w, box_h)
            pygame.draw.rect(render_surface, (0, 0, 0), box)
            pygame.draw.rect(render_surface, (90, 90, 105), box, 1)
            ty = box_y + 5
            for line in lines:
                txt = nick_font.render(line, True, (220, 220, 235))
                render_surface.blit(txt, (box_x + 8, ty))
                ty += line_h

        if profile:
            panel_h = HEIGHT // 2
            t = min((time.time() - profile_open_t) / PANEL_ANIM, 1.0)
            offset_y = int(-panel_h + panel_h * (1.0 - (1.0 - t) ** 3))
            own = profile["name"] == nickname
            profile_btn_rect = draw_profile_panel(
                render_surface, profile["name"], profile["sprite"],
                offset_y, profile_data["bio"], profile_data["max_dist"], own,
            )

        if cmd_console_open:
            render_surface.fill((0, 0, 0))

            # Entrelineado estilo pantalla vieja (scanlines)
            for yy in range(0, HEIGHT, 3):
                pygame.draw.line(render_surface, (0, 0, 0, 120), (0, yy), (WIDTH, yy))

            now = time.time()
            if now >= cmd_boot_until:
                _advance_cmd_typing()
                if cmd_lines and cmd_visible_chars[0] >= len(cmd_lines[0]):
                    cmd_input_enabled = True
            else:
                if int(now * 2) % 2 == 0:
                    boot_cursor = nick_font.render("_", True, (70, 185, 70))
                    render_surface.blit(boot_cursor, (8, 8))

            line_h = nick_font.get_height() + 2
            max_lines = max(1, (HEIGHT - 44) // line_h)
            start = max(0, len(cmd_lines) - max_lines)
            y = 8
            for i in range(start, len(cmd_lines)):
                line = cmd_lines[i]
                shown = line[:cmd_visible_chars[i]]
                txt = nick_font.render(shown, True, (50, 165, 50))
                render_surface.blit(txt, (8, y))
                y += line_h

            # Mostrar siempre la casilla de entrada, incluso durante la intro.
            if now < cmd_boot_until:
                cursor = ""
            else:
                cursor = "_" if int(time.time() * 2) % 2 == 0 else ""
            prompt = "> " + cmd_input + cursor
            prompt_txt = nick_font.render(prompt, True, (70, 185, 70))
            render_surface.blit(prompt_txt, (8, HEIGHT - line_h - 8))

        if exit_confirm_presses > 0:
            render_surface.fill((0, 0, 0))
            p = max(0.0, min(1.0, (exit_confirm_presses - 1) / 3.0))
            esc_color = (
                240,
                int(220 + (70 - 220) * p),
                int(70 + (50 - 70) * p),
            )
            esc_txt = nick_font.render("ESC", True, esc_color)
            tail_txt = nick_font.render(" to exit", True, (225, 225, 225))
            total_w = esc_txt.get_width() + tail_txt.get_width()
            x0 = (WIDTH - total_w) // 2
            y0 = (HEIGHT - esc_txt.get_height()) // 2
            render_surface.blit(esc_txt, (x0, y0))
            render_surface.blit(tail_txt, (x0 + esc_txt.get_width(), y0))

        net.update()
        udp_lost = net.status == UDPLink.LOST
        if not _is_local and (_ping_down.is_set() or udp_lost) and not conn_error:
            conn_error = True
            net.stop()
            _ping_stop.set()  # detener el monitor TCP
            _flush_map_markers(force=True)
            save_user_position(nickname, player.x, player.y)
            save_user_max_chunks(nickname, total_chunks)
            save_user_skin(nickname, player.skin_index)
            _msg = (
                f"Sin conexión con el servidor:\n{SERVER_IP}\n\nEl juego se cerrará."
                if _ping_down.is_set()
                else "Fuiste desconectado del servidor.\n\nEl juego se cerrará."
            )
            def _show_popup(msg=_msg):
                _popup_shown.set()
                root = tk.Tk()
                root.withdraw()
                mb.showerror("REALM — Sin conexión", msg)
                root.destroy()
                _popup_shown.clear()
            threading.Thread(target=_show_popup, daemon=True).start()

        win_w, win_h = screen.get_size()
        vx, vy, vw, vh = _compute_viewport(win_w, win_h)
        if vw == WIDTH and vh == HEIGHT:
            screen.blit(render_surface, (0, 0))
        else:
            scaled = pygame.transform.smoothscale(render_surface, (vw, vh))
            screen.fill((0, 0, 0))
            screen.blit(scaled, (vx, vy))

        pygame.display.flip()
        clock.tick(FPS)

        if exit_after_confirm:
            _shutdown_and_exit()


if __name__ == "__main__":
    main()