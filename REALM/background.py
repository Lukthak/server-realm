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

