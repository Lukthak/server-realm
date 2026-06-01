import pygame
import random
import math
from dataclasses import dataclass

BG_COLOR = (15, 5, 25)
NUM_STARS = 400
BRIGHT_STAR_CHANCE = 0.0025
BRIGHT_STAR_PARALLAX = 0.18

# Estrellas fugaces normales
MAX_SHOOTING_STARS = 8
SHOOTING_SPAWN_CHANCE = 0.08
SHOOTING_TRAIL = 10

# Estrellas fugaces lejanas
MAX_FAR_SHOOTING_STARS = 12
FAR_SHOOTING_SPAWN_CHANCE = 0.06
FAR_SHOOTING_TRAIL = 6


@dataclass
class BrightStar:
    kind: str
    x: int
    y: int
    radius: int
    color: tuple[int, int, int]
    pulse_speed: float
    pulse_offset: float
    planets: list["Planet"]
    solar_system: bool = False


@dataclass
class Planet:
    orbit_radius: float
    orbit_speed: float
    radius: float
    color: tuple[int, int, int]
    angle: float
    vertical_tilt: float
    depth_strength: float
    orbit_rotation: float
    moons: list["Moon"]


@dataclass
class Moon:
    orbit_radius: float
    orbit_speed: float
    radius: int
    color: tuple[int, int, int]
    angle: float


BRIGHT_STAR_TYPES: list[tuple[str, tuple[int, int, int], tuple[int, int]]] = [
    ("azul", (95, 155, 255), (7, 14)),
    ("roja", (255, 88, 88), (4, 9)),
    ("naranja", (255, 168, 65), (5, 11)),
    ("celeste", (145, 235, 255), (6, 13)),
    ("blanca", (240, 245, 255), (8, 16)),
]


def _towards_white(color: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    if amount <= 0.0:
        return color
    a = max(0.0, min(1.0, amount))
    r, g, b = color
    return (
        int(r + (255 - r) * a),
        int(g + (255 - g) * a),
        int(b + (255 - b) * a),
    )


def _clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


def _create_bright_star(rng: random.Random, x: int, y: int) -> BrightStar:
    # Regla especial: 1 de cada 4 estrellas es celeste y el doble de grande.
    giant_celeste = rng.random() < 0.25
    if giant_celeste:
        kind = "celeste"
        color = (145, 235, 255)
        size_range = (6, 13)
    else:
        kind, color, size_range = rng.choice(BRIGHT_STAR_TYPES)

    base_radius = rng.randint(size_range[0], size_range[1])
    # Variacion extra para que haya estrellas notablemente mas chicas o mas grandes.
    radius = int(base_radius * rng.uniform(0.85, 1.35))
    if giant_celeste:
        radius *= 2
    radius_cap = 30 if giant_celeste else 18
    radius = max(4, min(radius_cap, radius))
    return BrightStar(
        kind=kind,
        x=x,
        y=y,
        radius=radius,
        color=color,
        pulse_speed=rng.uniform(1.2, 3.2),
        pulse_offset=rng.uniform(0.0, math.tau),
        planets=_create_planets(rng, kind, radius, giant_celeste=giant_celeste),
    )


def _create_moons(rng: random.Random, planet_radius: float) -> list[Moon]:
    pr = float(planet_radius)
    if pr <= 2.2:
        moon_count = 0
    elif pr <= 3.2:
        moon_count = rng.randint(0, 1)
    elif pr <= 4.2:
        moon_count = rng.randint(1, 2)
    elif pr <= 5.2:
        moon_count = rng.randint(2, 3)
    elif pr <= 6.2:
        moon_count = rng.randint(3, 5)
    else:
        moon_count = rng.randint(5, 8)

    moons: list[Moon] = []
    for index in range(moon_count):
        orbit_radius = pr * 2.2 + index * rng.uniform(1.8, 3.0)
        orbit_speed = rng.uniform(1.0, 2.8) / max(1.0, orbit_radius / max(1.0, pr))
        moons.append(
            Moon(
                orbit_radius=orbit_radius,
                orbit_speed=orbit_speed,
                radius=1,
                color=(220, 220, 220),
                angle=random.uniform(0.0, math.tau),
            )
        )
    return moons


def _create_planets(rng: random.Random, kind: str, star_radius: int,
                    giant_celeste: bool = False) -> list[Planet]:
    star_scale = max(0.70, min(2.40, star_radius / 8.0))
    if kind == "azul":
        planet_count = rng.randint(3, 6)
        orbit_base = star_radius * 5.4 * star_scale
    elif kind == "celeste":
        planet_count = rng.randint(2, 5)
        orbit_base = star_radius * 5.0 * star_scale
    elif kind == "blanca":
        planet_count = rng.randint(4, 7)
        orbit_base = star_radius * 6.0 * star_scale
    elif kind == "naranja":
        planet_count = rng.randint(1, 5)
        orbit_base = star_radius * 4.6 * star_scale
    else:
        planet_count = rng.randint(0, 4)
        orbit_base = star_radius * 4.0 * star_scale

    # Estrellas grandes: mayor espacio orbital percibido (se ven mas cerca/grandes).
    if star_radius >= 12:
        orbit_base *= 1.28
        planet_count = min(8, planet_count + rng.randint(0, 2))
    elif star_radius <= 6:
        planet_count = max(0, planet_count - rng.randint(0, 1))

    # Celeste gigante: planetas del mismo tamaño y mucho mas alejados.
    uniform_planet_radius = None
    if giant_celeste and planet_count > 0:
        orbit_base *= 1.85
        planet_count = min(9, max(3, planet_count + rng.randint(1, 3)))
        uniform_planet_radius = rng.uniform(2.4, 5.8)

    # Regla global: a mayor cantidad de planetas, mayor separacion orbital.
    count_space_scale = 1.0 + max(0, planet_count - 1) * 0.14
    orbit_base *= (1.0 + max(0, planet_count - 1) * 0.07)

    # Soles generados no-hub: órbitas más lejanas entre sí.
    if not giant_celeste:
        orbit_base *= 1.22

    palette = [
        (170, 170, 190),
        (120, 185, 120),
        (190, 145, 110),
        (110, 160, 210),
        (220, 210, 170),
    ]

    planets: list[Planet] = []
    orbit_cursor = orbit_base + rng.uniform(0.0, star_radius * (0.45 + 0.25 * star_scale))
    gap_min = star_radius * (1.9 + 0.85 * star_scale)
    gap_max = star_radius * (3.2 + 1.20 * star_scale)
    gap_min *= count_space_scale
    gap_max *= count_space_scale
    if not giant_celeste:
        gap_min *= 1.35
        gap_max *= 1.70
    if giant_celeste:
        gap_min *= 2.0
        gap_max *= 2.8
    for index in range(planet_count):
        if index > 0:
            orbit_cursor += rng.uniform(gap_min, gap_max)
            # Salto extra ocasional para sistemas menos uniformes.
            if rng.random() < 0.22:
                orbit_cursor += rng.uniform(star_radius * 0.8, star_radius * 2.2)

        orbit_radius = orbit_cursor
        orbit_speed = rng.uniform(0.35, 1.15) / max(1.0, orbit_radius / star_radius)

        if kind in {"azul", "celeste", "blanca"}:
            max_pr = 6 if star_radius >= 12 else 5
        elif kind == "naranja":
            max_pr = 5 if star_radius >= 10 else 4
        else:
            max_pr = 4

        if uniform_planet_radius is not None:
            planet_radius = uniform_planet_radius
        else:
            min_pr = 1 if rng.random() < 0.18 else 2
            planet_radius = rng.uniform(float(min_pr), float(max_pr))
        planets.append(
            Planet(
                orbit_radius=orbit_radius,
                orbit_speed=orbit_speed,
                radius=planet_radius,
                color=rng.choice(palette),
                angle=random.uniform(0.0, math.tau),
                vertical_tilt=rng.uniform(0.18, 0.62),
                depth_strength=rng.uniform(0.30, 0.90),
                orbit_rotation=rng.uniform(0.0, math.tau),
                moons=_create_moons(rng, planet_radius),
            )
        )
    return planets


def _create_solar_system_planets(rng: random.Random, star_radius: int,
                                 hub_mode: bool = False) -> list[Planet]:
    # Sistema tipo Solar: 8 planetas con radios orbitales crecientes.
    specs = [
        ((170, 160, 145), 2, 0),  # Mercurio
        ((220, 190, 120), 2, 0),  # Venus
        ((120, 165, 220), 3, 1),  # Tierra
        ((205, 120, 90), 2, 0),   # Marte
        ((210, 175, 120), 4, 4),  # Jupiter
        ((205, 185, 145), 4, 5),  # Saturno
        ((125, 205, 220), 3, 2),  # Urano
        ((95, 130, 220), 3, 2),   # Neptuno
    ]

    planets: list[Planet] = []
    spacing_scale = max(0.85, min(2.30, 1.0 + (star_radius - 8) * 0.09))
    n_planets = len(specs)
    count_space_scale = 1.0 + max(0, n_planets - 1) * 0.14
    if hub_mode:
        count_space_scale *= 1.55

    orbit_base = star_radius * 5.2 * spacing_scale * count_space_scale
    for index, (color, radius, moon_count) in enumerate(specs):
        orbit_step = star_radius * (2.8 + 0.35 * spacing_scale) * count_space_scale
        orbit_radius = orbit_base + index * orbit_step + rng.uniform(0.0, star_radius * (0.4 + 0.25 * spacing_scale))
        orbit_speed = (1.05 / (1.0 + index * 0.42)) / max(1.0, orbit_radius / star_radius)
        planet_radius = max(1.0, float(radius) + rng.uniform(-0.35, 0.45))

        moons: list[Moon] = []
        for mi in range(moon_count):
            moon_orbit = planet_radius * 2.3 + mi * rng.uniform(1.6, 2.6)
            moon_speed = rng.uniform(1.0, 2.4) / max(1.0, moon_orbit / max(1.0, planet_radius))
            moons.append(
                Moon(
                    orbit_radius=moon_orbit,
                    orbit_speed=moon_speed,
                    radius=1,
                    color=(220, 220, 220),
                    angle=random.uniform(0.0, math.tau),
                )
            )

        planets.append(
            Planet(
                orbit_radius=orbit_radius,
                orbit_speed=orbit_speed,
                radius=planet_radius,
                color=color,
                angle=random.uniform(0.0, math.tau),
                vertical_tilt=rng.uniform(0.24, 0.42),
                depth_strength=rng.uniform(0.45, 0.8),
                orbit_rotation=rng.uniform(0.0, math.tau),
                moons=moons,
            )
        )
    return planets


def _draw_bright_planets(surface: pygame.Surface, star: BrightStar, t: float,
                         cx: int, cy: int, star_radius: int, white_shift: float,
                         front_only: bool | None = None) -> None:
    for planet in star.planets:
        angle = planet.angle + t * planet.orbit_speed
        depth = math.sin(angle)
        is_front = depth >= 0.0

        if front_only is True and not is_front:
            continue
        if front_only is False and is_front:
            continue

        ex = math.cos(angle) * planet.orbit_radius
        ey = math.sin(angle) * planet.orbit_radius * planet.vertical_tilt
        rot = planet.orbit_rotation
        cr = math.cos(rot)
        sr = math.sin(rot)
        px = int(cx + ex * cr - ey * sr)
        py = int(cy + ex * sr + ey * cr)
        depth_scale = 0.52 + ((depth + 1.0) * 0.5) * planet.depth_strength
        scaled_radius = max(1, int(planet.radius * depth_scale))

        pcolor = _towards_white(planet.color, white_shift)
        if is_front:
            dx = px - cx
            dy = py - cy
            overlap_r = star_radius + max(1, int(scaled_radius * 0.65))
            if (dx * dx + dy * dy) <= (overlap_r * overlap_r):
                pcolor = (10, 10, 12)
        pygame.draw.circle(surface, pcolor, (px, py), scaled_radius)

        for moon in planet.moons:
            moon_angle = moon.angle + t * moon.orbit_speed
            mx = int(px + math.cos(moon_angle) * moon.orbit_radius)
            my = int(py + math.sin(moon_angle) * moon.orbit_radius * 0.6)
            mcolor = _towards_white(moon.color, white_shift)
            pygame.draw.circle(surface, mcolor, (mx, my), moon.radius)


class ShootingStar:
    LIFE = 10  # frames de viaje antes de empezar a desvanecerse

    def __init__(self, map_w, map_h):
        self.x = float(random.randint(0, map_w))
        self.y = float(random.randint(0, map_h))
        angle = random.uniform(math.pi * 0.1, math.pi * 0.45)
        speed = random.uniform(12, 20)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.trail = []
        self.alive = True
        self.dying = False
        self.age = 0
        self.map_w = map_w
        self.map_h = map_h
        # deriva en la misma dirección de la estrella, más suave
        drift_speed = 1.8
        self._drift_vx = math.cos(angle) * drift_speed
        self._drift_vy = math.sin(angle) * drift_speed

    def update(self):
        if not self.dying:
            self.trail.append((self.x, self.y))
            if len(self.trail) > SHOOTING_TRAIL:
                self.trail.pop(0)
            self.x += self.vx
            self.y += self.vy
            self.age += 1
            if self.age >= self.LIFE:
                self.dying = True
        else:
            # El último punto (punta) deriva lentamente
            if self.trail:
                lx, ly = self.trail[-1]
                self.trail[-1] = (lx + self._drift_vx, ly + self._drift_vy)
            # Elimina desde la cola hacia el punto final (lento: 1 por frame)
            for _ in range(1):
                if len(self.trail) > 1:
                    self.trail.pop(0)
                else:
                    self.alive = False
                    break

    def draw(self, surface, cam_x, cam_y, white_shift: float = 0.0):
        count = len(self.trail)
        if count < 2:
            return
        w = surface.get_width()
        h = surface.get_height()

        # pulso de brillo: seno sobre el ciclo de vida (0→1→0)
        life_t = self.age / self.LIFE          # 0.0 al inicio, 1.0 al final
        pulse = math.sin(life_t * math.pi)     # 0→1 en mitad→0
        max_brightness = int(60 + pulse * 195) # base 60 (25% menos que antes), pico ~255

        for i in range(1, count):
            t = i / count  # 0 = cola, 1 = cabeza
            brightness = int(t * max_brightness)
            brightness = min(255, brightness)
            color = (brightness, int(brightness * 0.6), brightness)
            color = _towards_white(color, white_shift)
            x1 = int(self.trail[i - 1][0] - cam_x)
            y1 = int(self.trail[i - 1][1] - cam_y)
            x2 = int(self.trail[i][0] - cam_x)
            y2 = int(self.trail[i][1] - cam_y)
            if (-10 <= x1 <= w + 10 or -10 <= x2 <= w + 10) and \
               (-10 <= y1 <= h + 10 or -10 <= y2 <= h + 10):
                pygame.draw.line(surface, color, (x1, y1), (x2, y2))
        # cabeza brillante (solo si aún viaja)
        if not self.dying:
            hx = int(self.x - cam_x)
            hy = int(self.y - cam_y)
            if 0 <= hx < w and 0 <= hy < h:
                head_b = min(255, max_brightness + 30)
                head_color = _towards_white((head_b, head_b - 5, head_b), white_shift)
                surface.set_at((hx, hy), head_color)


class FarShootingStar:
    """Estrella fugaz lejana: más lenta, más corta y menos brillante."""
    LIFE = 14
    PARALLAX = 0.35   # se mueve al 35% de la cámara

    def __init__(self, map_w, map_h):
        self.x = float(random.randint(0, map_w))
        self.y = float(random.randint(0, map_h))
        angle = random.uniform(math.pi * 0.1, math.pi * 0.45)
        speed = random.uniform(4, 8)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.trail = []
        self.alive = True
        self.dying = False
        self.age = 0
        drift_speed = 0.6
        self._drift_vx = math.cos(angle) * drift_speed
        self._drift_vy = math.sin(angle) * drift_speed

    def update(self):
        if not self.dying:
            self.trail.append((self.x, self.y))
            if len(self.trail) > FAR_SHOOTING_TRAIL:
                self.trail.pop(0)
            self.x += self.vx
            self.y += self.vy
            self.age += 1
            if self.age >= self.LIFE:
                self.dying = True
        else:
            if self.trail:
                lx, ly = self.trail[-1]
                self.trail[-1] = (lx + self._drift_vx, ly + self._drift_vy)
            if len(self.trail) > 1:
                self.trail.pop(0)
            else:
                self.alive = False

    def draw(self, surface, cam_x, cam_y, white_shift: float = 0.0):
        count = len(self.trail)
        if count < 2:
            return
        w = surface.get_width()
        h = surface.get_height()
        life_t = self.age / self.LIFE
        pulse = math.sin(life_t * math.pi)
        max_brightness = int(20 + pulse * 80)  # pico ~100, más tenue
        cx = cam_x * self.PARALLAX
        cy = cam_y * self.PARALLAX
        for i in range(1, count):
            t = i / count
            brightness = int(t * max_brightness)
            color = (brightness, int(brightness * 0.55), brightness)
            color = _towards_white(color, white_shift)
            x1 = int(self.trail[i - 1][0] - cx)
            y1 = int(self.trail[i - 1][1] - cy)
            x2 = int(self.trail[i][0] - cx)
            y2 = int(self.trail[i][1] - cy)
            if (-10 <= x1 <= w + 10 or -10 <= x2 <= w + 10) and \
               (-10 <= y1 <= h + 10 or -10 <= y2 <= h + 10):
                surface.set_at((x2, y2), color)  # solo 1px, sin line


# ── BlackHole ────────────────────────────────────────────────────────────────

class BlackHole:
    """
    Agujero negro con galaxia espiral. Solo tonos rojo/naranja/amarillo.
    Las posiciones de estrellas se guardan en espacio galáctico
    y se rotan matemáticamente cada frame → la galaxia entera rota como un disco.
    """
    PARALLAX  = 0.12

    _THEMES = [
        {'inner': (255,  60,  10), 'arm': (200,  30,   5)},   # rojo vivo
        {'inner': (255, 120,  15), 'arm': (220,  70,   5)},   # rojo-naranja
        {'inner': (255, 160,  20), 'arm': (230, 100,   8)},   # naranja
        {'inner': (255, 200,  30), 'arm': (240, 140,  10)},   # naranja-amarillo
        {'inner': (255, 230,  60), 'arm': (245, 170,  20)},   # amarillo cálido
        {'inner': (255,  80,  40), 'arm': (210,  40,  10)},   # rojo-coral
    ]
    _STAR_PAL = [
        (170, 212, 255), (255, 255, 255), (255, 245, 204),
        (255, 215, 127), (255, 171,  84),
    ]
    _STAR_W = [0.25, 0.40, 0.20, 0.10, 0.05]

    def __init__(self, world_x, world_y, seed):
        rng   = random.Random(seed)
        self.seed = int(seed)
        self.wx = world_x
        self.wy = world_y

        n_arms = rng.randint(2, 5)
        turns  = rng.uniform(3.5, 5.5)
        spread = rng.uniform(0.06, 0.13)
        tilt   = rng.uniform(0.30, 0.92)   # inclinación del disco (1=frontal)
        scale  = rng.uniform(0.50, 0.90)
        theme  = rng.choice(self._THEMES)

        half   = 220                        # radio del canvas en px
        radius = half * 0.80 * scale
        ir, ig, ib = theme['inner']
        ar, ag, ab = theme['arm']

        def _star_color():
            rv = rng.random(); cumul = 0.0
            for c, w in zip(self._STAR_PAL, self._STAR_W):
                cumul += w
                if rv < cumul:
                    return c
            return self._STAR_PAL[-1]

        # Stars: (gx, gy, r, g, b, big)
        # gx/gy son coordenadas en el plano galáctico ANTES de la inclinación.
        # La inclinación (tilt) se aplica en draw() junto con la rotación.
        self._stars = []

        # Brazos espirales
        n_stars = int(420 * scale)
        for arm_i in range(n_arms):
            for _ in range(n_stars):
                u     = rng.betavariate(0.55, 1.0)
                t     = u * turns * math.pi
                r     = (t / (turns * math.pi)) * radius
                theta = t + (2 * math.pi * arm_i) / n_arms
                nr    = rng.gauss(0, spread * (r + 0.05 * radius))
                nt    = rng.gauss(0, spread * 0.12)
                gx    = (r + nr) * math.cos(theta + nt)
                gy    = (r + nr) * math.sin(theta + nt)
                d     = min(1.0, math.hypot(gx, gy) / (radius + 1e-9))
                tr_   = int(ir + (ar - ir) * d)
                tg_   = int(ig + (ag - ig) * d)
                tb_   = int(ib + (ab - ib) * d)
                br_, bg2, bb2 = _star_color()
                mx    = rng.uniform(0.0, 0.45)
                brt   = rng.uniform(0.25, 0.85)
                cr_   = int((br_ * (1-mx) + tr_  * mx) * brt)
                cg_   = int((bg2 * (1-mx) + tg_ * mx) * brt)
                cb_   = int((bb2 * (1-mx) + tb_  * mx) * brt)
                self._stars.append((gx, gy, cr_, cg_, cb_, rng.random() < 0.10))

        # Núcleo
        core_n = int(330 * scale)
        for _ in range(core_n):
            r_     = abs(rng.gauss(0, radius * 0.14))
            theta  = rng.uniform(0, 2 * math.pi)
            gx     = r_ * math.cos(theta)
            gy     = r_ * math.sin(theta)
            mx     = rng.uniform(0.0, 0.4)
            brt    = rng.uniform(0.5, 1.0)
            br_, bg2, bb2 = _star_color()
            cr_    = int((br_ * (1-mx) + ir * mx) * brt)
            cg_    = int((bg2 * (1-mx) + ig * mx) * brt)
            cb_    = int((bb2 * (1-mx) + ib * mx) * brt)
            self._stars.append((gx, gy, cr_, cg_, cb_, rng.random() < 0.18))

        # Halo pre-renderizado (radialmente simétrico → no necesita rotar)
        halo_sz = int(half * 2 + 4)
        self._halo = pygame.Surface((halo_sz, halo_sz))
        self._halo.fill((0, 0, 0))
        hc = halo_sz // 2
        for h_frac, h_alpha in [(0.45, 20), (0.30, 38), (0.18, 62), (0.10, 90)]:
            hr = max(2, int(radius * h_frac))
            hs = pygame.Surface((hr * 2 + 2, hr * 2 + 2))
            hs.fill((0, 0, 0))
            pygame.draw.circle(hs, (ir * h_alpha // 255,
                                    ig * h_alpha // 255,
                                    ib * h_alpha // 255), (hr, hr), hr)
            self._halo.blit(hs, (hc - hr, hc - hr), special_flags=pygame.BLEND_ADD)

        # Anillo brillante en el borde del núcleo interior — superficie separada (brilla siempre)
        rr = max(3, int(radius * 0.10))
        rs = pygame.Surface((rr * 2 + 6, rr * 2 + 6))
        rs.fill((0, 0, 0))
        rc = rr + 3
        ring_r = min(255, ir + (255 - ir) * 180 // 255)
        ring_g = min(255, ig + (255 - ig) * 180 // 255)
        ring_b = min(255, ib + (255 - ib) * 180 // 255)
        pygame.draw.circle(rs, (ring_r, ring_g, ring_b), (rc, rc), rr, 2)
        self._ring_surf = rs
        self._ring_offset = rc   # offset desde el centro del halo

        # Rayos de difracción (spikes) — en superficie separada para poder rotarla
        n_spikes = rng.choice([4, 4, 6, 6, 8])
        spike_len = int(radius * 0.32)
        base_angle = rng.uniform(0, math.pi)   # orientación base del set
        spike_sz = halo_sz
        self._spike_surf = pygame.Surface((spike_sz, spike_sz))
        self._spike_surf.fill((0, 0, 0))
        for i in range(n_spikes):
            ang = base_angle + i * (math.pi / n_spikes)
            for side in (1, -1):
                steps = max(1, spike_len)
                for s in range(steps):
                    t = 1.0 - s / steps
                    bright = t ** 2.2
                    px_ = int(hc + math.cos(ang) * s * side)
                    py_ = int(hc + math.sin(ang) * s * side)
                    if 0 <= px_ < spike_sz and 0 <= py_ < spike_sz:
                        cr_ = min(255, int(ring_r * bright))
                        cg_ = min(255, int(ring_g * bright))
                        cb_ = min(255, int(ring_b * bright))
                        cur = self._spike_surf.get_at((px_, py_))[:3]
                        self._spike_surf.set_at((px_, py_), (
                            min(255, cur[0] + cr_),
                            min(255, cur[1] + cg_),
                            min(255, cur[2] + cb_),
                        ))
        self._tilt       = tilt
        self._halo_half  = hc
        self._core_color = (ir, ig, ib)
        self._angle      = rng.uniform(0, 360)
        self._rot_speed  = rng.uniform(0.008, 0.018) * rng.choice([-1, 1])
        self._spike_angle     = math.degrees(base_angle)
        self._spike_rot_speed = abs(self._rot_speed) * 0.35 * rng.choice([-1, 1])

        # Metadatos para inspeccion/debug (admin command "ver").
        self.meta = {
            "arms": int(n_arms),
            "turns": float(turns),
            "spread": float(spread),
            "tilt": float(tilt),
            "scale": float(scale),
            "theme_inner": (int(ir), int(ig), int(ib)),
            "theme_arm": (int(ar), int(ag), int(ab)),
            "radius": float(radius),
            "star_count": int(len(self._stars)),
            "rot_speed": float(self._rot_speed),
            "spike_rot_speed": float(self._spike_rot_speed),
            "parallax": float(self.PARALLAX),
        }

    def draw(self, surface, cam_x, cam_y, sat_boost: float = 0.0) -> None:
        self._angle = (self._angle + self._rot_speed) % 360
        a   = math.radians(self._angle)
        ca  = math.cos(a)
        sa  = math.sin(a)
        tilt = self._tilt

        sw = surface.get_width()
        sh = surface.get_height()
        cx = int((self.wx - cam_x) * self.PARALLAX + sw / 2)
        cy = int((self.wy - cam_y) * self.PARALLAX + sh / 2)

        # Halo (sin rotar, es redondo) — dimming por distancia
        hh = self._halo_half
        halo_bright = int((0.12 + sat_boost * 0.88) * 255)
        if halo_bright >= 254:
            surface.blit(self._halo, (cx - hh, cy - hh), special_flags=pygame.BLEND_ADD)
        else:
            _tmp = self._halo.copy()
            _mask = pygame.Surface(_tmp.get_size())
            _mask.fill((halo_bright, halo_bright, halo_bright))
            _tmp.blit(_mask, (0, 0), special_flags=pygame.BLEND_MULT)
            surface.blit(_tmp, (cx - hh, cy - hh), special_flags=pygame.BLEND_ADD)

        # Anillo: siempre a brillo completo, independiente de la distancia
        ro = self._ring_offset
        surface.blit(self._ring_surf, (cx - ro, cy - ro), special_flags=pygame.BLEND_ADD)

        # Spikes: rotan lentamente de forma independiente al disco
        self._spike_angle = (self._spike_angle + self._spike_rot_speed) % 360
        rot_spikes = pygame.transform.rotate(self._spike_surf, self._spike_angle)
        rw, rh = rot_spikes.get_size()
        if halo_bright >= 254:
            surface.blit(rot_spikes, (cx - rw // 2, cy - rh // 2), special_flags=pygame.BLEND_ADD)
        else:
            _tmp2 = rot_spikes.copy()
            _mask2 = pygame.Surface(_tmp2.get_size())
            _mask2.fill((halo_bright, halo_bright, halo_bright))
            _tmp2.blit(_mask2, (0, 0), special_flags=pygame.BLEND_MULT)
            surface.blit(_tmp2, (cx - rw // 2, cy - rh // 2), special_flags=pygame.BLEND_ADD)

        # Saturación: amplificar distancia de cada canal respecto a la luminancia media
        sat_amp = 1.0 + sat_boost * 2.0

        # Estrellas: rotar en plano galáctico, luego aplicar inclinación en Y
        for gx, gy, r, g, b, big in self._stars:
            rx = ca * gx - sa * gy          # rotación 2-D
            ry = sa * gx + ca * gy
            sx = cx + int(rx)
            sy = cy + int(ry * tilt)        # inclinación del disco
            if 0 <= sx < sw and 0 <= sy < sh:
                if sat_boost > 0.0:
                    lum = (r + g + b) // 3
                    r2 = min(255, max(0, int(lum + (r - lum) * sat_amp)))
                    g2 = min(255, max(0, int(lum + (g - lum) * sat_amp)))
                    b2 = min(255, max(0, int(lum + (b - lum) * sat_amp)))
                    surface.set_at((sx, sy), (r2, g2, b2))
                else:
                    surface.set_at((sx, sy), (r, g, b))
            if big:
                h = max(r // 2, g // 2, b // 2)
                for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = sx + ddx, sy + ddy
                    if 0 <= nx < sw and 0 <= ny < sh:
                        surface.set_at((nx, ny), (h, h, h))

        # Punto central
        ir, ig2, ib = self._core_color
        pygame.draw.circle(surface, (255, 255, 220), (cx, cy), 3)
        pygame.draw.circle(surface, (ir // 4, ig2 // 4, ib // 4), (cx, cy), 7)


class Background:
    def __init__(self, map_width, map_height, screen_width, screen_height, seed=None):
        self.map_w = map_width
        self.map_h = map_height
        self.screen_w = screen_width
        self.screen_h = screen_height
        self.stars, self.bright_stars = self._generate(map_width, map_height, seed)
        self.shooting_stars = []
        self.far_shooting_stars = []
        self.tick = 0

    def _generate(self, map_w, map_h, seed=None):
        rng = random.Random(seed)
        stars = []
        bright_stars = []

        # Prueba forzada: una estrella gigante en (0, 0) del chunk (0,0).
        if seed == 0:
            forced_star = _create_bright_star(rng, 0, 0)
            forced_star.kind = "naranja"
            forced_star.color = (255, 168, 65)
            forced_star.radius = max(8, int(forced_star.radius * 2.0))
            forced_star.planets = _create_solar_system_planets(rng, forced_star.radius, hub_mode=True)
            forced_star.solar_system = True
            bright_stars.append(forced_star)
        elif rng.random() < BRIGHT_STAR_CHANCE:
            bx = rng.randint(0, map_w - 1)
            by = rng.randint(0, map_h - 1)
            bright_stars.append(_create_bright_star(rng, bx, by))

        for _ in range(NUM_STARS):
            sx = rng.randint(0, map_w - 1)
            sy = rng.randint(0, map_h - 1)
            size = rng.choice([1, 1, 1, 2])
            brightness = rng.randint(160, 245)
            color = (brightness, brightness - 20, min(255, brightness + 10))
            phase = rng.uniform(0, math.pi * 2)
            stars.append((sx, sy, size, color, phase))
        return stars, bright_stars

    def _draw_star(self, surface, sx, sy, size, color, glow, white_shift: float = 0.0,
                   ghost_dx: int = 0, ghost_dy: int = 0, ghost_amount: float = 0.0):
        gc = _towards_white((glow // 2, glow // 4, glow), white_shift)
        color = _towards_white(color, white_shift)
        if ghost_amount > 0.0 and (ghost_dx != 0 or ghost_dy != 0):
            gx = sx + ghost_dx
            gy = sy + ghost_dy
            if -4 <= gx <= self.screen_w + 4 and -4 <= gy <= self.screen_h + 4:
                ghost_c = _towards_white(gc, min(1.0, ghost_amount * 0.9))
                surface.set_at((gx, gy), ghost_c)
                if size >= 2:
                    if 0 <= gx + 1 < self.screen_w and 0 <= gy < self.screen_h:
                        surface.set_at((gx + 1, gy), ghost_c)
                    if 0 <= gx < self.screen_w and 0 <= gy + 1 < self.screen_h:
                        surface.set_at((gx, gy + 1), ghost_c)
        surface.set_at((sx, sy - 1), gc)
        surface.set_at((sx, sy + 1), gc)
        surface.set_at((sx - 1, sy), gc)
        surface.set_at((sx + 1, sy), gc)
        surface.set_at((sx, sy), color)
        if size >= 2:
            surface.set_at((sx + 1, sy), color)
            surface.set_at((sx, sy + 1), color)
            surface.set_at((sx + 1, sy + 1), color)

    def _draw_bright_star(self, surface: pygame.Surface, star: BrightStar, t: float,
                          cx: int, cy: int, bg_color: tuple[int, int, int],
                          white_shift: float = 0.0, ghost_dx: int = 0,
                          ghost_dy: int = 0, ghost_amount: float = 0.0) -> None:
        shimmer_radius = int(star.radius * 3.2)
        shimmer_size = shimmer_radius * 2 + 6
        shimmer = pygame.Surface((shimmer_size, shimmer_size), pygame.SRCALPHA)
        scx = shimmer_size // 2
        scy = shimmer_size // 2

        band_count = 34
        for band in range(band_count):
            start_y = scy - int(star.radius * 2.8)
            step = int((star.radius * 5.6) / max(1, band_count - 1))
            y_base = start_y + band * max(1, step)
            phase = t * (2.5 + star.pulse_speed * 0.5) + band * 0.9 + star.pulse_offset

            points: list[tuple[int, int]] = []
            for x in range(0, shimmer_size):
                dx = abs(x - scx)
                envelope = max(0.0, 1.0 - dx / max(1, shimmer_radius))
                wave = math.sin(x * 0.18 + phase) * (0.75 + star.radius * 0.05) * envelope
                points.append((x, int(y_base + wave)))

            alpha = max(28, min(96, int(40 + (math.sin(phase) + 1.0) * 18 + (math.sin(t * 1.6 + band) + 1.0) * 10)))
            if len(points) > 1:
                pygame.draw.aalines(shimmer, (*bg_color, alpha), False, points)

                soft_points = [(px, py + 1) for px, py in points]
                soft_alpha = max(4, alpha // 4)
                pygame.draw.aalines(shimmer, (*bg_color, soft_alpha), False, soft_points)

        glow_surface = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)

        pulse = (math.sin(t * star.pulse_speed + star.pulse_offset) + 1.0) * 0.5
        outer_alpha = int(18 + pulse * 24)
        mid_alpha = int(36 + pulse * 38)
        outer_r = int(star.radius * 2.7)
        mid_r = int(star.radius * 1.8)
        star_color = _towards_white(star.color, white_shift)

        # Planetas traseros primero para que la estrella los oculte parcialmente.
        _draw_bright_planets(surface, star, t, cx, cy, star.radius, white_shift, front_only=False)

        pygame.draw.circle(glow_surface, (*star_color, outer_alpha), (cx, cy), outer_r)
        pygame.draw.circle(glow_surface, (*star_color, mid_alpha), (cx, cy), mid_r)
        if ghost_amount > 0.0 and (ghost_dx != 0 or ghost_dy != 0):
            ghost_alpha = int((12 + 36 * ghost_amount) * 0.7)
            gx = cx + ghost_dx
            gy = cy + ghost_dy
            pygame.draw.circle(glow_surface, (255, 255, 255, ghost_alpha), (gx, gy), max(3, int(star.radius * 1.2)))
        surface.blit(glow_surface, (0, 0))

        pygame.draw.circle(surface, star_color, (cx, cy), star.radius)
        core_radius = max(2, int(star.radius * 0.55))
        pygame.draw.circle(surface, (255, 255, 255), (cx, cy), core_radius)
        surface.blit(shimmer, (cx - scx, cy - scy))

        # Planetas delanteros después del shimmer para sensación de profundidad.
        _draw_bright_planets(surface, star, t, cx, cy, star.radius, white_shift, front_only=True)

    def _update_shooting_stars(self):
        for ss in self.shooting_stars:
            ss.update()
        self.shooting_stars = [ss for ss in self.shooting_stars if ss.alive]
        if (len(self.shooting_stars) < MAX_SHOOTING_STARS
                and random.random() < SHOOTING_SPAWN_CHANCE):
            self.shooting_stars.append(ShootingStar(self.map_w, self.map_h))

        for fs in self.far_shooting_stars:
            fs.update()
        self.far_shooting_stars = [fs for fs in self.far_shooting_stars if fs.alive]
        if (len(self.far_shooting_stars) < MAX_FAR_SHOOTING_STARS
                and random.random() < FAR_SHOOTING_SPAWN_CHANCE):
            self.far_shooting_stars.append(FarShootingStar(self.map_w, self.map_h))

    def draw(self, surface, cam_x, cam_y, bg_color=BG_COLOR,
             world_x=0, world_y=0, global_cam_x=None, global_cam_y=None,
             white_shift: float = 0.0, cam_dx: float = 0.0, cam_dy: float = 0.0):
        # El fill lo hace el caller (Universe)
        t = self.tick * 0.04
        bright_t = pygame.time.get_ticks() / 1000.0
        self.tick += 1

        if global_cam_x is None:
            global_cam_x = cam_x + world_x
        if global_cam_y is None:
            global_cam_y = cam_y + world_y

        ghost_amount = max(0.0, min(1.0, (white_shift - 0.18) * 2.30))
        ghost_dx_norm = _clamp(int(cam_dx * 0.65), -5, 5)
        ghost_dy_norm = _clamp(int(cam_dy * 0.65), -5, 5)
        ghost_dx_far = _clamp(int(cam_dx * BRIGHT_STAR_PARALLAX * 0.9), -3, 3)
        ghost_dy_far = _clamp(int(cam_dy * BRIGHT_STAR_PARALLAX * 0.9), -3, 3)

        # Estrellas gigantes en capa lejana (parallax bajo): fondo más atrás.
        cam_cx = global_cam_x + self.screen_w / 2
        cam_cy = global_cam_y + self.screen_h / 2
        for star in self.bright_stars:
            wx = world_x + star.x
            wy = world_y + star.y
            rx = int((wx - cam_cx) * BRIGHT_STAR_PARALLAX + self.screen_w / 2)
            ry = int((wy - cam_cy) * BRIGHT_STAR_PARALLAX + self.screen_h / 2)
            pad = int(star.radius * 4)
            if star.planets:
                max_orbit = max(float(p.orbit_radius) for p in star.planets)
                one_chunk_extra = max(self.map_w, self.map_h) * BRIGHT_STAR_PARALLAX
                pad = int(max(pad, max_orbit + one_chunk_extra))
            if -pad <= rx <= self.screen_w + pad and -pad <= ry <= self.screen_h + pad:
                self._draw_bright_star(
                    surface, star, bright_t, rx, ry, bg_color, white_shift,
                    ghost_dx_far, ghost_dy_far, ghost_amount,
                )

        # Capa normal: 1:1 con la cámara
        for sx, sy, size, color, phase in self.stars:
            rx = sx - cam_x
            ry = sy - cam_y
            if -4 <= rx <= self.screen_w + 4 and -4 <= ry <= self.screen_h + 4:
                glow = int((math.sin(t + phase) * 0.5 + 0.5) * 200)
                self._draw_star(
                    surface, rx, ry, size, color, glow, white_shift,
                    ghost_dx_norm, ghost_dy_norm, ghost_amount,
                )

        # Estrellas fugaces
        self._update_shooting_stars()
        for fs in self.far_shooting_stars:
            fs.draw(surface, cam_x, cam_y, white_shift)
        for ss in self.shooting_stars:
            ss.draw(surface, cam_x, cam_y, white_shift)

