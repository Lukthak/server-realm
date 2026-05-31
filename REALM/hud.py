import io
import math
import os
import time

import pygame
from PIL import Image

_SPRITES_DIR = os.path.join(os.path.dirname(__file__), "sprites")
_pen_sprite: pygame.Surface | None = None
_REMOTE_SKIN_CACHE: dict[int, int] = {}


def _get_pen(target_h: int = 20) -> pygame.Surface:
    global _pen_sprite
    path = os.path.join(_SPRITES_DIR, "pen.png")
    img = pygame.image.load(path).convert_alpha()
    ow, oh = img.get_size()
    new_w = max(1, int(ow * target_h / oh))
    _pen_sprite = pygame.transform.scale(img, (new_w, target_h))
    return _pen_sprite


def draw_debug(surface, universe, cam_x, cam_y, font, chunk_coord, ping_ms: float = 0.0) -> None:
    overlay = pygame.Surface((surface.get_width(), surface.get_height()), pygame.SRCALPHA)
    grid_color = (0, 220, 90, 128)
    cx0, cy0 = universe.center
    for dcx in range(-1, 3):
        for dcy in range(-1, 3):
            wx = (cx0 + dcx) * universe.map_w
            wy = (cy0 + dcy) * universe.map_h
            sx = wx - cam_x
            sy = wy - cam_y
            pygame.draw.rect(overlay, grid_color,
                             pygame.Rect(sx, sy, universe.map_w, universe.map_h), 1)
    surface.blit(overlay, (0, 0))

    for chunk in universe.chunks.values():
        sx = chunk.world_x - cam_x
        sy = chunk.world_y - cam_y
        rect = pygame.Rect(sx, sy, universe.map_w, universe.map_h)
        pygame.draw.rect(surface, (0, 200, 80), rect, 1)
        label = font.render(f"[{chunk.cx},{chunk.cy}]", True, (0, 220, 90))
        surface.blit(label, (sx + 4, sy + 4))

    hud = font.render(f"[{chunk_coord[0]}, {chunk_coord[1]}]", True, (0, 220, 90))
    surface.blit(hud, (6, 6))
    ping_color = (0, 220, 90) if ping_ms < 150 else (255, 200, 0) if ping_ms < 300 else (255, 80, 80)
    ping_surf = font.render(f"ping {ping_ms:.0f} ms", True, ping_color)
    surface.blit(ping_surf, (6, 6 + hud.get_height() + 2))


def draw_minimap(surface, player_x, player_y, others, minimap_range) -> None:
    surface.fill((0, 0, 0))
    w, h = surface.get_size()
    cx, cy = w // 2, h // 2
    scale_x = w / (2 * minimap_range)
    scale_y = h / (2 * minimap_range)
    for _pid, (rx, ry, _rangle, _rskin, _rchunks, _rnick, _rchat) in others.items():
        px = int(cx + (rx - player_x) * scale_x)
        py = int(cy + (ry - player_y) * scale_y)
        if 0 <= px < w and 0 <= py < h:
            surface.set_at((px, py), (255, 255, 255))
    surface.set_at((cx, cy), (100, 150, 255))


def draw_chat_bubble(surface, font, text, cx, top_y) -> None:
    surf = font.render(text, True, (255, 255, 255))
    surface.blit(surf, (cx - surf.get_width() // 2, top_y - surf.get_height() - 4))


def draw_typing_dots(surface, cx, top_y) -> None:
    """Tres puntitos en secuencia: 1→2→3→1→... mientras el chat está abierto."""
    t = time.time()
    count = int(t * 2.5) % 3 + 1   # cambia cada ~0.4s, cicla 1→2→3
    spacing = 6
    radius = 2
    total_w = spacing * (count - 1)
    x0 = cx - total_w // 2
    color = (210, 210, 210)
    for i in range(count):
        pygame.draw.circle(surface, color, (x0 + i * spacing, top_y - 8), radius)


def _draw_wrapped(surface, font, text, color, rect, center=False) -> None:
    # parte en palabras; si una palabra sola no entra, la corta por carácter
    raw_words = text.split() if text.strip() else []
    words = []
    for word in raw_words:
        if font.size(word)[0] <= rect.width:
            words.append(word)
        else:
            # partir la palabra en trozos que entren
            chunk = ""
            for ch in word:
                if font.size(chunk + ch)[0] <= rect.width:
                    chunk += ch
                else:
                    if chunk:
                        words.append(chunk)
                    chunk = ch
            if chunk:
                words.append(chunk)

    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        if font.size(test)[0] <= rect.width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    lh = font.get_height() + 1
    total_h = lh * len(lines)
    y = rect.top + max(0, (rect.height - total_h) // 2)
    for line in lines:
        if y + lh > rect.bottom:
            break
        rendered = font.render(line, True, color)
        x = rect.left + (rect.width - rendered.get_width()) // 2 if center else rect.left
        surface.blit(rendered, (x, y))
        y += lh


def draw_profile_panel(surface, name: str, sprite: pygame.Surface,
                       offset_y: int, bio: str = "",
                       max_dist: float = 0, own: bool = False) -> pygame.Rect:
    """Panel 3 columnas: bio | sprite | distancia. Devuelve rect del botón Editar."""
    w, h = surface.get_size()
    panel_h = h // 2
    col = w // 3
    HEADER_H = 22
    FOOTER_H = 22
    body_top = HEADER_H
    body_h = panel_h - HEADER_H - FOOTER_H

    panel = pygame.Surface((w, panel_h))
    panel.fill((0, 0, 0))
    pygame.draw.line(panel, (60, 60, 60), (0, panel_h - 1), (w, panel_h - 1), 1)

    font_sm = pygame.font.SysFont(None, 16)

    # cabecera: nombre
    label = font_sm.render(name, True, (200, 200, 255))
    panel.blit(label, (10, 5))

    # columna izquierda: bio (centrado)
    _draw_wrapped(panel, font_sm, bio if bio.strip() else "...",
                  (140, 140, 140), pygame.Rect(4, body_top + 3, col - 8, body_h - 6), center=True)

    # columna central: sprite
    sw, sh = sprite.get_size()
    scale = min((col - 12) / sw, (body_h - 12) / sh, 3.0)
    scaled = pygame.transform.scale(sprite, (int(sw * scale), int(sh * scale)))
    panel.blit(scaled, (col + (col - scaled.get_width()) // 2,
                        body_top + (body_h - scaled.get_height()) // 2))

    # columna derecha: distancia max
    title = font_sm.render("Distancia maxima:", True, (160, 160, 160))
    panel.blit(title, (col * 2 + 4, body_top + 6))
    val = font_sm.render(str(int(max_dist)), True, (255, 210, 80))
    panel.blit(val, (col * 2 + 4, body_top + 20))

    # icono lápiz en esquina izquierda (solo perfil propio)
    pen_rect = pygame.Rect(0, 0, 0, 0)
    if own:
        pen = _get_pen(target_h=FOOTER_H - 4)
        px = 6
        py = panel_h - FOOTER_H + (FOOTER_H - pen.get_height()) // 2
        panel.blit(pen, (px, py))
        pen_rect = pygame.Rect(px, py + offset_y, pen.get_width(), pen.get_height())

    surface.blit(panel, (0, offset_y))
    return pen_rect


# ── Utilidades de render compartidas ────────────────────────────────────────

def load_icon(icono_path: str):
    """Carga ICONO.ico como superficie pygame 32×32."""
    try:
        img = Image.open(icono_path).convert("RGBA").resize((32, 32), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return pygame.image.load(buf, "icon.png")
    except Exception:
        return None


def draw_players(surface, others, cam_x, cam_y, nick_font, ghost_sprites) -> None:
    """Dibuja todos los jugadores remotos con sus burbujas/nick."""
    for _pid, (rx, ry, rangle, rskin, _rchunks, rnick, rchat) in others.items():
        rnick = str(rnick).replace("\x00", "")
        rchat = str(rchat).replace("\x00", "")
        try:
            skin_raw = int(rskin)
        except Exception:
            skin_raw = -1
        if 0 <= skin_raw < len(ghost_sprites):
            idx = skin_raw
            _REMOTE_SKIN_CACHE[_pid] = idx
        else:
            idx = _REMOTE_SKIN_CACHE.get(_pid, 0)

        try:
            angle = float(rangle)
        except Exception:
            angle = 0.0
        if not math.isfinite(angle):
            angle = 0.0

        base = ghost_sprites[idx]
        spr = pygame.transform.rotate(base, -angle)
        # Ancla estable en bounds lógicos (sprite base), no en el sprite rotado.
        cx_world = float(rx) + base.get_width() / 2
        cy_world = float(ry) + base.get_height() / 2
        rcx = int(cx_world - cam_x)
        rcy = int(cy_world - cam_y)
        sx = rcx - spr.get_width() // 2
        sy = rcy - spr.get_height() // 2
        top_base = int(float(ry) - cam_y)
        bottom_base = top_base + base.get_height()
        if rchat == "\x01":
            draw_typing_dots(surface, rcx, top_base)
        elif rchat:
            draw_chat_bubble(surface, nick_font, rchat, rcx, top_base)
        surface.blit(spr, (sx, sy))
        if rnick:
            label = nick_font.render(rnick, True, (200, 200, 255))
            surface.blit(label, (rcx - label.get_width() // 2, bottom_base + 2))


def draw_local_player(surface, player, nickname, cam_x, cam_y, nick_font,
                      is_typing: bool, current_chat: str,
                      tint_color=None, tint_amount: float = 0.0,
                      brightness: float = 1.0) -> None:
    """Dibuja el jugador local con nick y burbuja/dots."""
    player.draw(surface, cam_x, cam_y,
                tint_color=tint_color, tint_amount=tint_amount,
                brightness=brightness)
    if hasattr(player, "get_label_anchor"):
        pcx, pbottom = player.get_label_anchor(cam_x, cam_y)
        pcy = pbottom - getattr(player, "base_h", player.h)
    else:
        pcx = int(player.x) - cam_x + player.w // 2
        pcy = int(player.y) - cam_y
        pbottom = pcy + player.h
    label = nick_font.render(nickname, True, (200, 200, 255))
    surface.blit(label, (pcx - label.get_width() // 2, pbottom + 2))
    if is_typing:
        draw_typing_dots(surface, pcx, pcy)
    elif current_chat:
        draw_chat_bubble(surface, nick_font, current_chat, pcx, pcy)
