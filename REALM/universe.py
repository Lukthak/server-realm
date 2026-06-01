import math
import random

from background import (
    Background,
    BG_COLOR,
    BlackHole,
    BRIGHT_STAR_CHANCE,
    BRIGHT_STAR_PARALLAX,
    _create_bright_star,
    _create_solar_system_planets,
)

# Offsets: 5x5 completo (radio 2)
_OFFSETS = [(dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)]

_BH_SPAWN_PROB = 0.0025
_BH_MIN_CHUNK_DISTANCE = 40
_BH_HAS_CACHE = {}
_STAR_SPAWN_PROB = BRIGHT_STAR_CHANCE
_STAR_MIN_CHUNK_DISTANCE = 20
_STAR_HAS_CACHE = {}


def _towards_white(color, amount):
    if amount <= 0.0:
        return color
    a = max(0.0, min(1.0, amount))
    r, g, b = color
    return (
        int(r + (255 - r) * a),
        int(g + (255 - g) * a),
        int(b + (255 - b) * a),
    )


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


def _chunk_has_bh(cx, cy):
    """Comprueba deterministamente si un chunk tiene black hole, sin instanciarlo.

    Regla adicional: no puede haber dos black holes a menos de
    _BH_MIN_CHUNK_DISTANCE chunks entre si.
    """
    key = (cx, cy)
    cached = _BH_HAS_CACHE.get(key)
    if cached is not None:
        return cached

    bh_seed = (cx * 48271) ^ (cy * 16807) ^ 0xDEAD
    my_roll = random.Random(bh_seed).random()
    if my_roll >= _BH_SPAWN_PROB:
        _BH_HAS_CACHE[key] = False
        return False

    # Supresion por vecindad: en el radio permitido solo sobrevive el
    # candidato con menor roll. En empate, gana la coordenada menor.
    for dx in range(-_BH_MIN_CHUNK_DISTANCE, _BH_MIN_CHUNK_DISTANCE + 1):
        for dy in range(-_BH_MIN_CHUNK_DISTANCE, _BH_MIN_CHUNK_DISTANCE + 1):
            if dx == 0 and dy == 0:
                continue
            if (dx * dx + dy * dy) > (_BH_MIN_CHUNK_DISTANCE * _BH_MIN_CHUNK_DISTANCE):
                continue
            nx = cx + dx
            ny = cy + dy
            n_seed = (nx * 48271) ^ (ny * 16807) ^ 0xDEAD
            n_roll = random.Random(n_seed).random()
            if n_roll >= _BH_SPAWN_PROB:
                continue
            if (n_roll < my_roll) or (n_roll == my_roll and (nx, ny) < (cx, cy)):
                _BH_HAS_CACHE[key] = False
                return False

    _BH_HAS_CACHE[key] = True
    return True


def _chunk_has_bright_star(cx, cy):
    """Spawn determinista de estrella brillante por chunk, con separacion minima."""
    if cx == 0 and cy == 0:
        return True

    key = (cx, cy)
    cached = _STAR_HAS_CACHE.get(key)
    if cached is not None:
        return cached

    s_seed = (cx * 73856093) ^ (cy * 19349663) ^ 0xA11CE
    my_roll = random.Random(s_seed).random()
    if my_roll >= _STAR_SPAWN_PROB:
        _STAR_HAS_CACHE[key] = False
        return False

    for dx in range(-_STAR_MIN_CHUNK_DISTANCE, _STAR_MIN_CHUNK_DISTANCE + 1):
        for dy in range(-_STAR_MIN_CHUNK_DISTANCE, _STAR_MIN_CHUNK_DISTANCE + 1):
            if dx == 0 and dy == 0:
                continue
            if (dx * dx + dy * dy) > (_STAR_MIN_CHUNK_DISTANCE * _STAR_MIN_CHUNK_DISTANCE):
                continue
            nx = cx + dx
            ny = cy + dy
            n_seed = (nx * 73856093) ^ (ny * 19349663) ^ 0xA11CE
            n_roll = random.Random(n_seed).random()
            if n_roll >= _STAR_SPAWN_PROB:
                continue
            if (n_roll < my_roll) or (n_roll == my_roll and (nx, ny) < (cx, cy)):
                _STAR_HAS_CACHE[key] = False
                return False

    _STAR_HAS_CACHE[key] = True
    return True


def _chunk_bright_stars(cx, cy, map_w, map_h):
    """Genera deterministamente las bright stars del chunk con reglas globales."""
    seed = (cx * 73856093) ^ (cy * 19349663)
    rng = random.Random(seed)

    if cx == 0 and cy == 0:
        forced_star = _create_bright_star(rng, 0, 0)
        forced_star.kind = "naranja"
        forced_star.color = (255, 168, 65)
        forced_star.radius = max(8, int(forced_star.radius * 2.0))
        forced_star.planets = _create_solar_system_planets(rng, forced_star.radius, hub_mode=True)
        forced_star.solar_system = True
        return [forced_star]

    if not _chunk_has_bright_star(cx, cy):
        return []

    # Consumir el primer random para mantener el flujo similar al generador original.
    rng.random()
    bx = rng.randint(0, map_w - 1)
    by = rng.randint(0, map_h - 1)
    return [_create_bright_star(rng, bx, by)]


def _chunk_bh_pos(cx, cy, map_w, map_h):
    """Devuelve la posición mundial exacta del BH en un chunk, sin instanciarlo."""
    bh_seed = (cx * 48271) ^ (cy * 16807) ^ 0xDEAD
    bh_rng = random.Random(bh_seed)
    bh_rng.random()          # consumir el roll de probabilidad
    world_x = cx * map_w
    world_y = cy * map_h
    wx = world_x + bh_rng.randint(map_w // 5, map_w * 4 // 5)
    wy = world_y + bh_rng.randint(map_h // 5, map_h * 4 // 5)
    return (wx, wy)


class Chunk:
    def __init__(self, cx, cy, map_w, map_h, screen_w, screen_h):
        self.cx = cx
        self.cy = cy
        self.world_x = cx * map_w
        self.world_y = cy * map_h
        # Semilla determinista: mismo chunk → mismas estrellas siempre
        seed = (cx * 73856093) ^ (cy * 19349663)
        self.bg = Background(map_w, map_h, screen_w, screen_h, seed=seed)
        self.bg.bright_stars = _chunk_bright_stars(cx, cy, map_w, map_h)
        # Black hole: probabilidad determinista + separacion minima entre chunks.
        if _chunk_has_bh(cx, cy):
            bh_seed = (cx * 48271) ^ (cy * 16807) ^ 0xDEAD
            wx, wy = _chunk_bh_pos(cx, cy, map_w, map_h)
            self.black_hole = BlackHole(
                wx,
                wy,
                seed=bh_seed)
        else:
            self.black_hole = None


class Universe:
    def __init__(self, map_w, map_h, screen_w, screen_h):
        self.map_w = map_w
        self.map_h = map_h
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.center = (0, 0)
        self.chunks = {}
        self._lingering = {}   # key → (chunk, frames_left)
        self._tick = 0
        self._bh_darkness = 0.0   # 0.0=normal, 1.0=negro total
        self._sun_glow = 0.0      # 0.0=sin influencia, 1.0=tinte máximo
        self._sun_color = (0, 0, 0)
        self._prev_cam = None
        # Capas de parallax globales (tilan con real_cam, sin saltos en chunk boundaries)
        self._far_stars = _gen_parallax_layer(700, map_w, map_h, 35,  90,  seed=42)
        self._mid_stars = _gen_parallax_layer(550, map_w, map_h, 90, 150,  seed=1337)
        self._reload(0, 0)

    def get_sun_tint(self):
        """Color e intensidad de tinte para sprites cerca del sol."""
        if self._sun_glow <= 0.0:
            return (0, 0, 0), 0.0
        amount = min(0.72, self._sun_glow * 0.85)
        return self._sun_color, amount

    def get_player_light(self):
        """Devuelve tinte por sol + brillo por black hole para el sprite local."""
        tint_color, tint_amount = self.get_sun_tint()
        # Cerca del sol, elevar la luz y llevar el tinte hacia blanco.
        sun_white = min(0.55, self._sun_glow * 0.65)
        tint_color = _towards_white(tint_color, sun_white)
        tint_amount = min(0.90, tint_amount + self._sun_glow * 0.25)
        # Cerca del black hole bajar bastante el brillo del sprite.
        brightness = max(0.22, 1.0 - self._bh_darkness * 0.78)
        # Cerca del sol, subir brillo del sprite.
        brightness = min(1.35, brightness + self._sun_glow * 0.35)
        return tint_color, tint_amount, brightness

    def get_light_at(self, world_x: float, world_y: float):
        """Devuelve (tint_color, tint_amount, brightness) para una posicion mundial."""
        BH_DARK_RADIUS = 1200.0
        SUN_LIGHT_RADIUS = 1800.0

        min_bh_dist = float("inf")
        for bh in self._all_blackholes():
            d = math.hypot(float(bh.wx) - world_x, float(bh.wy) - world_y)
            if d < min_bh_dist:
                min_bh_dist = d
        bh_darkness = 1.0 - (min_bh_dist / BH_DARK_RADIUS) if min_bh_dist < BH_DARK_RADIUS else 0.0

        min_sun_dist = float("inf")
        near_sun_color = (0, 0, 0)
        for chunk in self.chunks.values():
            wx0 = chunk.world_x
            wy0 = chunk.world_y
            for star in chunk.bg.bright_stars:
                sx = wx0 + star.x
                sy = wy0 + star.y
                d = math.hypot(float(sx) - world_x, float(sy) - world_y)
                if d < min_sun_dist:
                    min_sun_dist = d
                    near_sun_color = star.color
        sun_glow = 1.0 - (min_sun_dist / SUN_LIGHT_RADIUS) if min_sun_dist < SUN_LIGHT_RADIUS else 0.0

        tint_amount = min(0.72, sun_glow * 0.85)
        sun_white = min(0.55, sun_glow * 0.65)
        tint_color = _towards_white(near_sun_color, sun_white)
        tint_amount = min(0.90, tint_amount + sun_glow * 0.25)
        brightness = max(0.22, 1.0 - bh_darkness * 0.78)
        brightness = min(1.35, brightness + sun_glow * 0.35)
        return tint_color, tint_amount, brightness

    def _needed(self, cx, cy):
        base = {(cx + dx, cy + dy) for dx, dy in _OFFSETS}
        # los chunks con black hole cargan sus 8 vecinos también
        extra = set()
        for (bx, by) in base:
            if _chunk_has_bh(bx, by):
                for dx, dy in _OFFSETS:
                    extra.add((bx + dx, by + dy))
        return base | extra

    def _reload(self, cx, cy):
        needed = self._needed(cx, cy)
        for key in list(self.chunks):
            if key not in needed:
                chunk = self.chunks.pop(key)
                if chunk.black_hole is not None:
                    self._lingering[key] = chunk   # sin timer: se elimina al salir de pantalla
        for key in needed:
            if key not in self.chunks:
                self._lingering.pop(key, None)   # si vuelve al grid, dejar de lingerear
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
        # Eliminar lingering black holes que ya salieron de pantalla
        cam_x = world_x - self.screen_w / 2
        cam_y = world_y - self.screen_h / 2
        margin = 60
        for key in list(self._lingering):
            bh = self._lingering[key].black_hole
            sx = (bh.wx - cam_x) * bh.PARALLAX + self.screen_w / 2
            sy = (bh.wy - cam_y) * bh.PARALLAX + self.screen_h / 2
            if sx < -margin or sx > self.screen_w + margin or \
               sy < -margin or sy > self.screen_h + margin:
                del self._lingering[key]
        # Calcular oscurecimiento por proximidad al black hole más cercano
        # Radio de influencia: 1200 px mundo → negro total a 0 px
        BH_DARK_RADIUS = 1200.0
        min_dist = float('inf')
        all_bh = [c.black_hole for c in self.chunks.values() if c.black_hole]
        all_bh += [c.black_hole for c in self._lingering.values() if c.black_hole]
        for bh in all_bh:
            d = math.hypot(bh.wx - world_x, bh.wy - world_y)
            if d < min_dist:
                min_dist = d
        if min_dist < BH_DARK_RADIUS:
            self._bh_darkness = 1.0 - (min_dist / BH_DARK_RADIUS)
        else:
            self._bh_darkness = 0.0

        # Iluminación por estrella gigante más cercana (sol)
        SUN_LIGHT_RADIUS = 1800.0
        min_sun_dist = float('inf')
        near_sun_color = (0, 0, 0)
        for chunk in self.chunks.values():
            wx0 = chunk.world_x
            wy0 = chunk.world_y
            for star in chunk.bg.bright_stars:
                sx = wx0 + star.x
                sy = wy0 + star.y
                d = math.hypot(sx - world_x, sy - world_y)
                if d < min_sun_dist:
                    min_sun_dist = d
                    near_sun_color = star.color
        if min_sun_dist < SUN_LIGHT_RADIUS:
            self._sun_glow = 1.0 - (min_sun_dist / SUN_LIGHT_RADIUS)
            self._sun_color = near_sun_color
        else:
            self._sun_glow = 0.0
            self._sun_color = (0, 0, 0)
        return self.center

    def draw(self, surface, cam_x, cam_y):
        if self._prev_cam is None:
            cam_dx = 0.0
            cam_dy = 0.0
        else:
            cam_dx = float(cam_x - self._prev_cam[0])
            cam_dy = float(cam_y - self._prev_cam[1])
        self._prev_cam = (cam_x, cam_y)

        # Mezclar BG_COLOR con negro según proximidad al black hole
        d = self._bh_darkness
        bg = (int(BG_COLOR[0] * (1 - d)),
              int(BG_COLOR[1] * (1 - d)),
              int(BG_COLOR[2] * (1 - d)))

        # Tinte por proximidad al sol más cercano.
        if self._sun_glow > 0.0:
            tint = min(0.62, self._sun_glow * 0.62)
            sr, sg, sb = self._sun_color
            bg = (
                int(bg[0] * (1.0 - tint) + sr * tint),
                int(bg[1] * (1.0 - tint) + sg * tint),
                int(bg[2] * (1.0 - tint) + sb * tint),
            )

        surface.fill(bg)
        t = self._tick * 0.04
        self._tick += 1
        star_white = min(1.0, self._sun_glow * 1.05)
        ghost_amount = max(0.0, min(1.0, (star_white - 0.18) * 2.30))

        # Black holes (parallax 0.12, lo más lejano)
        BH_DARK_RADIUS = 1200.0
        world_x = cam_x + self.screen_w / 2
        world_y = cam_y + self.screen_h / 2
        for chunk in self.chunks.values():
            if chunk.black_hole is not None:
                bh = chunk.black_hole
                d = math.hypot(bh.wx - world_x, bh.wy - world_y)
                sat = max(0.0, 1.0 - d / BH_DARK_RADIUS)
                bh.draw(surface, cam_x, cam_y, sat)
        # Black holes de chunks en fade-out
        for chunk in self._lingering.values():
            bh = chunk.black_hole
            d = math.hypot(bh.wx - world_x, bh.wy - world_y)
            sat = max(0.0, 1.0 - d / BH_DARK_RADIUS)
            bh.draw(surface, cam_x, cam_y, sat)

        # Capa lejana (parallax 0.2) — global, tila cada map_w/map_h
        vcx = int(cam_x * 0.2)
        vcy = int(cam_y * 0.2)
        for sx, sy, color, phase in self._far_stars:
            rx = (sx - vcx) % self.map_w
            ry = (sy - vcy) % self.map_h
            if 0 <= rx < self.screen_w and 0 <= ry < self.screen_h:
                glow = int((math.sin(t * 0.6 + phase) * 0.5 + 0.5) * 40)
                b = min(255, color[0] + glow)
                c = (b, max(0, b - 5), min(255, b + 8))
                main_c = _towards_white(c, star_white)
                if ghost_amount > 0.0:
                    gdx = max(-3, min(3, int(cam_dx * 0.2 * 0.9)))
                    gdy = max(-3, min(3, int(cam_dy * 0.2 * 0.9)))
                    gx = rx + gdx
                    gy = ry + gdy
                    if 0 <= gx < self.screen_w and 0 <= gy < self.screen_h:
                        surface.set_at((gx, gy), _towards_white(main_c, min(1.0, ghost_amount * 0.9)))
                surface.set_at((rx, ry), main_c)

        # Capa intermedia (parallax 0.55) — global, tila cada map_w/map_h
        vcx = int(cam_x * 0.55)
        vcy = int(cam_y * 0.55)
        for sx, sy, color, phase in self._mid_stars:
            rx = (sx - vcx) % self.map_w
            ry = (sy - vcy) % self.map_h
            if 0 <= rx < self.screen_w and 0 <= ry < self.screen_h:
                glow = int((math.sin(t * 0.8 + phase) * 0.5 + 0.5) * 80)
                b = min(255, color[0] + glow)
                c = (b, max(0, b - 10), min(255, b + 10))
                main_c = _towards_white(c, star_white)
                if ghost_amount > 0.0:
                    gdx = max(-4, min(4, int(cam_dx * 0.55 * 0.9)))
                    gdy = max(-4, min(4, int(cam_dy * 0.55 * 0.9)))
                    gx = rx + gdx
                    gy = ry + gdy
                    if 0 <= gx < self.screen_w and 0 <= gy < self.screen_h:
                        surface.set_at((gx, gy), _towards_white(main_c, min(1.0, ghost_amount * 0.9)))
                surface.set_at((rx, ry), main_c)

        # Chunks: estrellas frontales (parallax 1:1) + estrellas fugaces
        for chunk in self.chunks.values():
            local_cam_x = cam_x - chunk.world_x
            local_cam_y = cam_y - chunk.world_y
            chunk.bg.draw(
                surface,
                local_cam_x,
                local_cam_y,
                bg,
                world_x=chunk.world_x,
                world_y=chunk.world_y,
                global_cam_x=cam_x,
                global_cam_y=cam_y,
                white_shift=star_white,
                cam_dx=cam_dx,
                cam_dy=cam_dy,
            )

    def find_nearby_blackhole(self, world_x, world_y, scan_radius=50):
        """Escanea un radio de chunks usando solo la función determinista (sin instanciar).
        Devuelve (wx, wy) de un BH cercano aleatorio, o None si no hay ninguno."""
        cur_cx = int(world_x // self.map_w)
        cur_cy = int(world_y // self.map_h)
        candidates = []
        for dcx in range(-scan_radius, scan_radius + 1):
            for dcy in range(-scan_radius, scan_radius + 1):
                if dcx == 0 and dcy == 0:
                    continue
                cx = cur_cx + dcx
                cy = cur_cy + dcy
                if not _chunk_has_bh(cx, cy):
                    continue
                wx, wy = _chunk_bh_pos(cx, cy, self.map_w, self.map_h)
                dist = math.hypot(wx - world_x, wy - world_y)
                candidates.append((dist, wx, wy))
        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0])
        pick = random.choice(candidates[:3])
        return (pick[1], pick[2])

    def _chunk_suns(self, cx, cy):
        """Devuelve lista de soles (estrellas gigantes) en coordenadas mundo para un chunk."""
        key = (cx, cy)
        if key in self.chunks:
            bright_stars = self.chunks[key].bg.bright_stars
        else:
            bright_stars = _chunk_bright_stars(cx, cy, self.map_w, self.map_h)

        wx0 = cx * self.map_w
        wy0 = cy * self.map_h
        return [(wx0 + s.x, wy0 + s.y) for s in bright_stars]

    def _chunk_sun_objects(self, cx, cy):
        """Devuelve soles del chunk en mundo: (wx, wy, BrightStar)."""
        key = (cx, cy)
        if key in self.chunks:
            bright_stars = self.chunks[key].bg.bright_stars
        else:
            bright_stars = _chunk_bright_stars(cx, cy, self.map_w, self.map_h)

        wx0 = cx * self.map_w
        wy0 = cy * self.map_h
        return [(float(wx0 + s.x), float(wy0 + s.y), s) for s in bright_stars]

    def _all_blackholes(self):
        seen = set()
        out = []
        for chunk in self.chunks.values():
            bh = chunk.black_hole
            if bh is None:
                continue
            key = (int(bh.wx), int(bh.wy))
            if key in seen:
                continue
            seen.add(key)
            out.append(bh)
        for chunk in self._lingering.values():
            bh = chunk.black_hole
            if bh is None:
                continue
            key = (int(bh.wx), int(bh.wy))
            if key in seen:
                continue
            seen.add(key)
            out.append(bh)
        return out

    def get_loaded_map_markers(self) -> dict:
        """Devuelve marcadores de lo actualmente cargado para persistir en el mapa."""
        stars: list[dict] = []
        blackholes: list[dict] = []
        seen_stars = set()
        seen_bh = set()

        for chunk in self.chunks.values():
            wx0 = chunk.world_x
            wy0 = chunk.world_y
            for s in chunk.bg.bright_stars:
                sx = int(wx0 + s.x)
                sy = int(wy0 + s.y)
                skey = (sx, sy)
                if skey in seen_stars:
                    continue
                seen_stars.add(skey)
                stars.append({
                    "x": sx,
                    "y": sy,
                    "color": [int(s.color[0]), int(s.color[1]), int(s.color[2])],
                })

            bh = chunk.black_hole
            if bh is not None:
                bx = int(bh.wx)
                by = int(bh.wy)
                bkey = (bx, by)
                if bkey not in seen_bh:
                    seen_bh.add(bkey)
                    blackholes.append({"x": bx, "y": by})

        for chunk in self._lingering.values():
            bh = chunk.black_hole
            if bh is None:
                continue
            bx = int(bh.wx)
            by = int(bh.wy)
            bkey = (bx, by)
            if bkey not in seen_bh:
                seen_bh.add(bkey)
                blackholes.append({"x": bx, "y": by})

        return {
            "stars": stars,
            "blackholes": blackholes,
        }

    def get_star_under_player(self, world_x, world_y, scan_radius=1, footprint_radius=14.0):
        """Si el jugador está sobre un sol, devuelve info útil para UI/admin."""
        cur_cx = int(world_x // self.map_w)
        cur_cy = int(world_y // self.map_h)
        best = None

        for dcx in range(-scan_radius, scan_radius + 1):
            for dcy in range(-scan_radius, scan_radius + 1):
                cx = cur_cx + dcx
                cy = cur_cy + dcy
                for sx, sy, star in self._chunk_sun_objects(cx, cy):
                    dist = math.hypot(sx - world_x, sy - world_y)
                    hit_r = max(2.0, float(star.radius) + float(footprint_radius))
                    if dist <= hit_r:
                        if best is None or dist < best[0]:
                            best = (dist, sx, sy, star)

        if best is None:
            return None

        _, sx, sy, star = best
        moons_per_planet = [len(p.moons) for p in star.planets]
        sizes_per_planet = [float(p.radius) for p in star.planets]
        total_moons = sum(moons_per_planet)
        return {
            "x": sx,
            "y": sy,
            "kind": star.kind,
            "color": tuple(int(c) for c in star.color),
            "planets": len(star.planets),
            "moons": total_moons,
            "moons_per_planet": moons_per_planet,
            "sizes_per_planet": sizes_per_planet,
            "radius": int(star.radius),
            "pulse_speed": float(star.pulse_speed),
        }

    def get_planet_near_player(self, world_x, world_y, planet_time: float,
                               scan_radius=7, footprint_radius=10.0):
        """Devuelve todos los planetas visualmente cercanos al jugador.

        Importante: la deteccion se hace en coordenadas de pantalla para coincidir
        con el render de estrellas gigantes (parallax + orbitas en screen-space).
        """
        hits = []

        solar_names = [
            "Mercurion", "Venara", "Tierron", "Martis",
            "Jupiron", "Saturnia", "Uranix", "Neptaris",
        ]

        # Camara centrada en el jugador (mismo supuesto que el game loop actual).
        cam_cx = float(world_x)
        cam_cy = float(world_y)
        player_sx = float(self.screen_w) * 0.5
        player_sy = float(self.screen_h) * 0.5

        # Revisar chunks cargados: son los mismos que pueden dibujar estrellas.
        for chunk in self.chunks.values():
            wx0 = float(chunk.world_x)
            wy0 = float(chunk.world_y)
            for star in chunk.bg.bright_stars:
                sx_world = wx0 + float(star.x)
                sy_world = wy0 + float(star.y)

                # Misma proyeccion que background.draw para bright stars.
                star_sx = (sx_world - cam_cx) * BRIGHT_STAR_PARALLAX + player_sx
                star_sy = (sy_world - cam_cy) * BRIGHT_STAR_PARALLAX + player_sy

                for idx, planet in enumerate(star.planets):
                    angle = float(planet.angle) + float(planet_time) * float(planet.orbit_speed)
                    ex = math.cos(angle) * float(planet.orbit_radius)
                    ey = math.sin(angle) * float(planet.orbit_radius) * float(planet.vertical_tilt)
                    rot = float(getattr(planet, "orbit_rotation", 0.0))
                    cr = math.cos(rot)
                    sr = math.sin(rot)
                    px = star_sx + ex * cr - ey * sr
                    py = star_sy + ex * sr + ey * cr

                    dist = math.hypot(px - player_sx, py - player_sy)
                    hit_r = max(4.0, float(planet.radius) * 2.0 + float(footprint_radius))
                    if dist <= hit_r:
                        if getattr(star, "solar_system", False) and len(star.planets) == 8 and idx < len(solar_names):
                            pname = solar_names[idx]
                        else:
                            pname = f"Planeta {idx + 1}"
                        hits.append({
                            "name": pname,
                            "index": idx + 1,
                            "size": float(planet.radius),
                            "moons": len(planet.moons),
                            "orbit_radius": float(planet.orbit_radius),
                            "distance": float(dist),
                        })

        if not hits:
            return []
        hits.sort(key=lambda p: p.get("distance", 0.0))
        return hits

    def get_blackhole_near_player(self, world_x, world_y, footprint_radius=24.0):
        """Devuelve info detallada del BH mas cercano si esta dentro de rango."""
        BH_DARK_RADIUS = 1200.0
        best = None
        for bh in self._all_blackholes():
            d = math.hypot(float(bh.wx) - world_x, float(bh.wy) - world_y)
            if best is None or d < best[0]:
                best = (d, bh)

        if best is None:
            return None

        dist, bh = best
        detect_radius = max(64.0, BH_DARK_RADIUS + float(footprint_radius))
        if dist > detect_radius:
            return None

        m = getattr(bh, "meta", {})
        darkness = max(0.0, min(1.0, 1.0 - (dist / BH_DARK_RADIUS)))
        return {
            "x": float(bh.wx),
            "y": float(bh.wy),
            "distance": float(dist),
            "darkness": float(darkness),
            "seed": int(getattr(bh, "seed", 0)),
            "parallax": float(getattr(bh, "PARALLAX", 0.0)),
            "radius": float(m.get("radius", 0.0)),
            "arms": int(m.get("arms", 0)),
            "turns": float(m.get("turns", 0.0)),
            "spread": float(m.get("spread", 0.0)),
            "tilt": float(m.get("tilt", 0.0)),
            "scale": float(m.get("scale", 0.0)),
            "star_count": int(m.get("star_count", 0)),
            "rot_speed": float(m.get("rot_speed", 0.0)),
            "spike_rot_speed": float(m.get("spike_rot_speed", 0.0)),
            "theme_inner": tuple(m.get("theme_inner", (0, 0, 0))),
            "theme_arm": tuple(m.get("theme_arm", (0, 0, 0))),
        }

    def find_nearby_sun(self, world_x, world_y, scan_radius=12):
        """Busca un sol cercano (estrella gigante) en un radio de chunks y devuelve (wx, wy)."""
        cur_cx = int(world_x // self.map_w)
        cur_cy = int(world_y // self.map_h)
        candidates = []

        for dcx in range(-scan_radius, scan_radius + 1):
            for dcy in range(-scan_radius, scan_radius + 1):
                cx = cur_cx + dcx
                cy = cur_cy + dcy
                for wx, wy in self._chunk_suns(cx, cy):
                    dist = math.hypot(wx - world_x, wy - world_y)
                    candidates.append((dist, float(wx), float(wy)))

        if not candidates:
            return None

        candidates.sort(key=lambda c: c[0])
        pick = random.choice(candidates[:3])
        return (pick[1], pick[2])
