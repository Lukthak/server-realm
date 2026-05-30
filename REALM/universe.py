import math
import random

from background import Background, BG_COLOR

# Offsets: centro + 4 cardinales + 4 diagonales = 3x3 completo
_OFFSETS = [
    (0, 0),
    (1, 0), (-1, 0), (0, 1), (0, -1),
    (1, 1), (1, -1), (-1, 1), (-1, -1),
]


def _gen_parallax_layer(n, tile_w, tile_h, b_min, b_max, seed):
    rng = random.Random(seed)
    stars = []
    for _ in range(n):
        sx = rng.randint(0, tile_w - 1)
        sy = rng.randint(0, tile_h - 1)
        b = rng.randint(b_min, b_max)
        color = (b, max(0, b - 10), min(255, b + 10))
        phase = rng.uniform(0, math.pi * 2)
        stars.append((sx, sy, color, phase))
    return stars


class Chunk:
    def __init__(self, cx, cy, map_w, map_h, screen_w, screen_h):
        self.cx = cx
        self.cy = cy
        self.world_x = cx * map_w
        self.world_y = cy * map_h
        # Semilla determinista: mismo chunk → mismas estrellas siempre
        seed = (cx * 73856093) ^ (cy * 19349663)
        self.bg = Background(map_w, map_h, screen_w, screen_h, seed=seed)


class Universe:
    def __init__(self, map_w, map_h, screen_w, screen_h):
        self.map_w = map_w
        self.map_h = map_h
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.center = (0, 0)
        self.chunks = {}
        self._tick = 0
        # Capas de parallax globales (tilan con real_cam, sin saltos en chunk boundaries)
        self._far_stars = _gen_parallax_layer(700, map_w, map_h, 35,  90,  seed=42)
        self._mid_stars = _gen_parallax_layer(550, map_w, map_h, 90, 150,  seed=1337)
        self._reload(0, 0)

    def _needed(self, cx, cy):
        return {(cx + dx, cy + dy) for dx, dy in _OFFSETS}

    def _reload(self, cx, cy):
        needed = self._needed(cx, cy)
        for key in list(self.chunks):
            if key not in needed:
                del self.chunks[key]
        for key in needed:
            if key not in self.chunks:
                self.chunks[key] = Chunk(
                    *key, self.map_w, self.map_h, self.screen_w, self.screen_h
                )

    def update(self, world_x, world_y):
        """Llama con la posición del jugador en coordenadas mundiales."""
        cx = int(world_x // self.map_w)
        cy = int(world_y // self.map_h)
        if (cx, cy) != self.center:
            self.center = (cx, cy)
            self._reload(cx, cy)
        return self.center

    def draw(self, surface, cam_x, cam_y):
        surface.fill(BG_COLOR)
        t = self._tick * 0.04
        self._tick += 1

        # Capa lejana (parallax 0.2) — global, tila cada map_w/map_h
        vcx = int(cam_x * 0.2)
        vcy = int(cam_y * 0.2)
        for sx, sy, color, phase in self._far_stars:
            rx = (sx - vcx) % self.map_w
            ry = (sy - vcy) % self.map_h
            if 0 <= rx < self.screen_w and 0 <= ry < self.screen_h:
                glow = int((math.sin(t * 0.6 + phase) * 0.5 + 0.5) * 40)
                b = min(255, color[0] + glow)
                surface.set_at((rx, ry), (b, max(0, b - 5), min(255, b + 8)))

        # Capa intermedia (parallax 0.55) — global, tila cada map_w/map_h
        vcx = int(cam_x * 0.55)
        vcy = int(cam_y * 0.55)
        for sx, sy, color, phase in self._mid_stars:
            rx = (sx - vcx) % self.map_w
            ry = (sy - vcy) % self.map_h
            if 0 <= rx < self.screen_w and 0 <= ry < self.screen_h:
                glow = int((math.sin(t * 0.8 + phase) * 0.5 + 0.5) * 80)
                b = min(255, color[0] + glow)
                surface.set_at((rx, ry), (b, max(0, b - 10), min(255, b + 10)))

        # Chunks: estrellas frontales (parallax 1:1) + estrellas fugaces
        for chunk in self.chunks.values():
            local_cam_x = cam_x - chunk.world_x
            local_cam_y = cam_y - chunk.world_y
            chunk.bg.draw(surface, local_cam_x, local_cam_y)
