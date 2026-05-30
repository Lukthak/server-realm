import io
import math
import os
import queue
import sys
import threading
import time

import pygame
from PIL import Image

from dialogs import (ask_nickname, check_server_or_exit, open_chat_dialog,
                     get_user_position, save_user_position,
                     get_user_bio, save_user_bio, open_bio_dialog,
                     get_user_max_chunks, save_user_max_chunks,
                     get_user_skin, save_user_skin)
from hud import draw_chat_bubble, draw_debug, draw_minimap, draw_typing_dots, draw_profile_panel
from config import SERVER_IP, SERVER_PORT
from net import UDPLink
from sonda import Sonda, SPRITE_NAMES, _load_sprite
from universe import Universe

WIDTH, HEIGHT = 350, 350
MAP_WIDTH, MAP_HEIGHT = WIDTH * 4, HEIGHT * 4
FPS = 60

ICONO_PATH = os.path.join(os.path.dirname(__file__), "ICONO.ico")


def _pygame_icon():
    try:
        img = Image.open(ICONO_PATH).convert("RGBA").resize((32, 32), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return pygame.image.load(buf, "icon.png")
    except Exception:
        return None


def _draw_server_error_overlay(screen: pygame.Surface, msg: str) -> pygame.Rect:
    W, H = screen.get_size()
    overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    screen.blit(overlay, (0, 0))

    box_w, box_h = min(W - 20, 300), 140
    box_x = (W - box_w) // 2
    box_y = (H - box_h) // 2
    pygame.draw.rect(screen, (40, 18, 18), (box_x, box_y, box_w, box_h), border_radius=8)
    pygame.draw.rect(screen, (180, 55, 55), (box_x, box_y, box_w, box_h), 2, border_radius=8)

    title_font = pygame.font.SysFont(None, 22)
    body_font  = pygame.font.SysFont(None, 17)

    title = title_font.render("Sin conexión al servidor", True, (230, 90, 90))
    screen.blit(title, (box_x + (box_w - title.get_width()) // 2, box_y + 12))

    for i, line in enumerate(msg.split("\n")):
        surf = body_font.render(line, True, (190, 190, 190))
        screen.blit(surf, (box_x + (box_w - surf.get_width()) // 2, box_y + 44 + i * 20))

    btn_w, btn_h = 80, 28
    btn_x = box_x + (box_w - btn_w) // 2
    btn_y = box_y + box_h - btn_h - 10
    btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
    mx, my = pygame.mouse.get_pos()
    btn_color = (210, 75, 75) if btn_rect.collidepoint(mx, my) else (150, 45, 45)
    pygame.draw.rect(screen, btn_color, btn_rect, border_radius=5)
    lbl = body_font.render("Cerrar", True, (255, 255, 255))
    screen.blit(lbl, (btn_x + (btn_w - lbl.get_width()) // 2, btn_y + (btn_h - lbl.get_height()) // 2))

    return btn_rect


def main():
    print(f"Servidor: {SERVER_IP}:{SERVER_PORT}")
    check_server_or_exit()
    nickname = ask_nickname()

    pygame.init()
    icon = _pygame_icon()
    if icon:
        pygame.display.set_icon(icon)
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("REALM")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 14)
    nick_font = pygame.font.SysFont(None, 16)

    universe = Universe(MAP_WIDTH, MAP_HEIGHT, WIDTH, HEIGHT)
    default_x, default_y = MAP_WIDTH // 2, MAP_HEIGHT // 2
    start_x, start_y = get_user_position(nickname, default_x, default_y)
    player = Sonda(start_x=start_x, start_y=start_y, speed=2)
    player.skin_index = get_user_skin(nickname) % len(player.sprites)
    player.image = player.sprites[player.skin_index]
    net = UDPLink()
    _connect_start = time.time()
    _server_error: str | None = None
    _err_btn_rect: pygame.Rect | None = None
    ghost_sprites = [_load_sprite(name) for name in SPRITE_NAMES]

    # chunks visitados: conjunto de (cx, cy) únicos recorridos esta sesión
    _visited_chunks: set = set()
    _chunks_all_time: int = get_user_max_chunks(nickname)  # cargado del servidor
    total_chunks: int = _chunks_all_time

    chat_msg = {"text": "", "until": 0.0}
    chat_queue = queue.Queue()
    chat_open = threading.Event()

    debug = False
    map_open = False
    minimap_range = 3000
    profile = None
    profile_open_t = 0.0
    PANEL_ANIM = 0.25
    profile_data = {"bio": "", "max_dist": 0.0, "loading": False}
    profile_btn_rect = None
    _profile_loading = False
    bio_queue: queue.Queue = queue.Queue()
    bio_editing = threading.Event()

    while True:
        # ── Detectar error de servidor ──────────────────────────────────────
        if _server_error is None and net.status == UDPLink.LOST:
            _server_error = f"Se perdió la conexión con el servidor.\n{SERVER_IP}:{SERVER_PORT}"

        if _server_error is not None:
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
                    if _err_btn_rect and _err_btn_rect.collidepoint(event.pos):
                        save_user_position(nickname, player.x, player.y)
                        save_user_max_chunks(nickname, total_chunks)
                        save_user_skin(nickname, player.skin_index)
                        net.disconnect()
                        net.stop()
                        pygame.quit()
                        sys.exit()
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    save_user_position(nickname, player.x, player.y)
                    save_user_max_chunks(nickname, total_chunks)
                    save_user_skin(nickname, player.skin_index)
                    net.disconnect()
                    net.stop()
                    pygame.quit()
                    sys.exit()
            _err_btn_rect = _draw_server_error_overlay(screen, _server_error)
            pygame.display.flip()
            clock.tick(FPS)
            continue

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
                # clic en botón Editar
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
                    px_s = int(player.x) - cam_x
                    py_s = int(player.y) - cam_y
                    if pygame.Rect(px_s, py_s, player.w, player.h).collidepoint(mx, my):
                        clicked = {"name": nickname, "sprite": player.image, "chunks": total_chunks}
                    else:
                        for _pid, (rx, ry, rskin, rchunks, rnick, _rchat) in net.get_others().items():
                            idx = int(rskin) % len(ghost_sprites)
                            spr = ghost_sprites[idx]
                            sx_g = int(rx) - cam_x
                            sy_g = int(ry) - cam_y
                            if pygame.Rect(sx_g, sy_g, spr.get_width(), spr.get_height()).collidepoint(mx, my):
                                clicked = {"name": rnick, "sprite": spr, "chunks": rchunks}
                                break
                    if clicked:
                        if profile is None or profile["name"] != clicked["name"]:
                            profile_open_t = time.time()
                            profile_data["bio"] = ""
                            profile_data["loading"] = True
                            _pname = clicked["name"]
                            _is_own = _pname == nickname
                            _tc = total_chunks
                            _rchunks = clicked.get("chunks", 0)
                            def _load_profile(name=_pname, own=_is_own, tc=_tc, rc=_rchunks):
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

        keys = pygame.key.get_pressed()
        if any(keys[k] for k in (pygame.K_w, pygame.K_s, pygame.K_a, pygame.K_d)):
            if chat_msg["text"] and chat_msg["until"] == float("inf"):
                chat_msg["until"] = time.time() + 5.0

        player.update(keys)
        chunk_coord = universe.update(player.x, player.y)

        # acumular chunks únicos
        _visited_chunks.add(chunk_coord)
        total_chunks = _chunks_all_time + len(_visited_chunks)

        current_chat = chat_msg["text"] if time.time() < chat_msg["until"] else ""
        _net_chat = "\x01" if chat_open.is_set() else current_chat
        net.send(player.x, player.y, player.skin_index, total_chunks, nickname, _net_chat)

        cam_x, cam_y = player.get_camera(WIDTH, HEIGHT)

        if map_open:
            draw_minimap(screen, player.x, player.y, net.get_others(), minimap_range)
        else:
            universe.draw(screen, cam_x, cam_y)

            for _pid, (rx, ry, rskin, rchunks, rnick, rchat) in net.get_others().items():
                idx = int(rskin) % len(ghost_sprites)
                spr = ghost_sprites[idx]
                sx = int(rx) - cam_x
                sy = int(ry) - cam_y
                rcx = sx + spr.get_width() // 2
                if rchat == "\x01":
                    draw_typing_dots(screen, rcx, sy)
                elif rchat:
                    draw_chat_bubble(screen, nick_font, rchat, rcx, sy)
                screen.blit(spr, (sx, sy))
                if rnick:
                    label = nick_font.render(rnick, True, (200, 200, 255))
                    screen.blit(label, (
                        rcx - label.get_width() // 2,
                        sy + spr.get_height() + 2,
                    ))

            player.draw(screen, cam_x, cam_y)
            _plabel = nick_font.render(nickname, True, (200, 200, 255))
            _pcx = int(player.x) - cam_x + player.w // 2
            screen.blit(_plabel, (_pcx - _plabel.get_width() // 2, int(player.y) - cam_y + player.h + 2))
            pcx = int(player.x) - cam_x + player.w // 2
            pcy = int(player.y) - cam_y
            if chat_open.is_set():
                draw_typing_dots(screen, pcx, pcy)
            elif current_chat:
                draw_chat_bubble(screen, nick_font, current_chat, pcx, pcy)

            if debug:
                draw_debug(screen, universe, cam_x, cam_y, font, chunk_coord)

        if profile:
            panel_h = HEIGHT // 2
            t = min((time.time() - profile_open_t) / PANEL_ANIM, 1.0)
            ease = 1.0 - (1.0 - t) ** 3
            offset_y = int(-panel_h + panel_h * ease)
            own = profile["name"] == nickname
            profile_btn_rect = draw_profile_panel(
                screen, profile["name"], profile["sprite"],
                offset_y, profile_data["bio"], profile_data["max_dist"], own
            )

        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()
