import queue
import random
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.messagebox as mb
from pathlib import Path

import pygame

from config import (SERVER_IP, SERVER_PORT,
                    WIDTH, HEIGHT, MAP_WIDTH, MAP_HEIGHT, FPS, ICONO_PATH)
from dialogs import (ask_nickname, open_chat_dialog, get_user_position, save_user_position,
                     get_user_bio, save_user_bio, open_bio_dialog,
                     get_user_max_chunks, save_user_max_chunks,
                     get_user_skin, save_user_skin,
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
    icon = load_icon(ICONO_PATH)
    if icon:
        pygame.display.set_icon(icon)
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
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

    chat_msg: dict = {"text": "", "until": 0.0}
    chat_queue: queue.Queue = queue.Queue()
    chat_open = threading.Event()

    debug = False
    map_open = False
    conn_error = False
    _popup_shown = threading.Event()
    minimap_range = 3000
    profile = None
    profile_open_t = 0.0
    PANEL_ANIM = 0.25
    profile_data: dict = {"bio": "", "max_dist": 0.0, "loading": False}
    profile_btn_rect = None
    bio_queue: queue.Queue = queue.Queue()
    bio_editing = threading.Event()
    cam_x = cam_y = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_user_position(nickname, player.x, player.y)
                save_user_max_chunks(nickname, total_chunks)
                save_user_skin(nickname, player.skin_index)
                net.disconnect()
                net.stop()
                pygame.quit()
                sys.exit()

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
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
                if event.key == pygame.K_F3:
                    debug = not debug
                elif event.key == pygame.K_m:
                    map_open = not map_open
                    if map_open:
                        profile = None
                elif event.key == pygame.K_RETURN and not chat_open.is_set():
                    chat_open.set()
                    threading.Thread(
                        target=open_chat_dialog,
                        args=(chat_queue, chat_open),
                        daemon=True,
                    ).start()

            elif event.type == pygame.MOUSEWHEEL and map_open:
                minimap_range = max(100, int(minimap_range * (0.8 if event.y > 0 else 1.25)))

            player.handle_event(event)

        try:
            msg = chat_queue.get_nowait()
            if msg:
                raw = msg.strip()
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
        except queue.Empty:
            pass

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
        if any(keys[k] for k in (pygame.K_w, pygame.K_s, pygame.K_a, pygame.K_d)):
            if chat_msg["text"] and chat_msg["until"] == float("inf"):
                chat_msg["until"] = time.time() + 5.0

        player.update(keys)
        chunk_coord = universe.update(player.x, player.y)
        _visited_chunks.add(chunk_coord)
        total_chunks = _chunks_all_time + len(_visited_chunks)

        current_chat = chat_msg["text"] if time.time() < chat_msg["until"] else ""
        net.send(player.x, player.y, player.angle, player.skin_index, total_chunks, nickname,
                 "\x01" if chat_open.is_set() else current_chat)

        cam_x, cam_y = player.get_camera(WIDTH, HEIGHT)

        if map_open:
            draw_minimap(screen, player.x, player.y, net.get_others(), minimap_range)
        else:
            universe.draw(screen, cam_x, cam_y)
            draw_players(screen, net.get_others(), cam_x, cam_y, nick_font, ghost_sprites)
            draw_local_player(screen, player, nickname, cam_x, cam_y, nick_font,
                              chat_open.is_set(), current_chat)
            if debug:
                draw_debug(screen, universe, cam_x, cam_y, font, chunk_coord, _ping_stats["tcp_ms"])

        if profile:
            panel_h = HEIGHT // 2
            t = min((time.time() - profile_open_t) / PANEL_ANIM, 1.0)
            offset_y = int(-panel_h + panel_h * (1.0 - (1.0 - t) ** 3))
            own = profile["name"] == nickname
            profile_btn_rect = draw_profile_panel(
                screen, profile["name"], profile["sprite"],
                offset_y, profile_data["bio"], profile_data["max_dist"], own,
            )

        net.update()
        udp_lost = net.status == UDPLink.LOST
        if not _is_local and (_ping_down.is_set() or udp_lost) and not conn_error:
            conn_error = True
            net.stop()
            _ping_stop.set()  # detener el monitor TCP
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

        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()

