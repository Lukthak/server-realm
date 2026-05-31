import pygame
import random
import math

BG_COLOR = (15, 5, 25)
NUM_STARS = 400

# Estrellas fugaces normales
MAX_SHOOTING_STARS = 8
SHOOTING_SPAWN_CHANCE = 0.08
SHOOTING_TRAIL = 10

# Estrellas fugaces lejanas
MAX_FAR_SHOOTING_STARS = 12
FAR_SHOOTING_SPAWN_CHANCE = 0.06
FAR_SHOOTING_TRAIL = 6


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

    def draw(self, surface, cam_x, cam_y):
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
                surface.set_at((hx, hy), (head_b, head_b - 5, head_b))


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

    def draw(self, surface, cam_x, cam_y):
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
        self.stars = self._generate(map_width, map_height, seed)
        self.shooting_stars = []
        self.far_shooting_stars = []
        self.tick = 0

    def _generate(self, map_w, map_h, seed=None):
        rng = random.Random(seed)
        stars = []
        for _ in range(NUM_STARS):
            sx = rng.randint(0, map_w - 1)
            sy = rng.randint(0, map_h - 1)
            size = rng.choice([1, 1, 1, 2])
            brightness = rng.randint(160, 245)
            color = (brightness, brightness - 20, min(255, brightness + 10))
            phase = rng.uniform(0, math.pi * 2)
            stars.append((sx, sy, size, color, phase))
        return stars

    def _draw_star(self, surface, sx, sy, size, color, glow):
        gc = (glow // 2, glow // 4, glow)
        surface.set_at((sx, sy - 1), gc)
        surface.set_at((sx, sy + 1), gc)
        surface.set_at((sx - 1, sy), gc)
        surface.set_at((sx + 1, sy), gc)
        surface.set_at((sx, sy), color)
        if size >= 2:
            surface.set_at((sx + 1, sy), color)
            surface.set_at((sx, sy + 1), color)
            surface.set_at((sx + 1, sy + 1), color)

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

    def draw(self, surface, cam_x, cam_y):
        # El fill lo hace el caller (Universe)
        t = self.tick * 0.04
        self.tick += 1

        # Capa normal: 1:1 con la cámara
        for sx, sy, size, color, phase in self.stars:
            rx = sx - cam_x
            ry = sy - cam_y
            if -4 <= rx <= self.screen_w + 4 and -4 <= ry <= self.screen_h + 4:
                glow = int((math.sin(t + phase) * 0.5 + 0.5) * 200)
                self._draw_star(surface, rx, ry, size, color, glow)

        # Estrellas fugaces
        self._update_shooting_stars()
        for fs in self.far_shooting_stars:
            fs.draw(surface, cam_x, cam_y)
        for ss in self.shooting_stars:
            ss.draw(surface, cam_x, cam_y)

