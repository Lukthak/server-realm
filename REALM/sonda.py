import pygame
import os

SPRITES_DIR = os.path.join(os.path.dirname(__file__), "sprites")
SPRITE_SCALE = 1.5
SPRITE_NAMES = ["sonda1.png", "sonda2.png", "sonda3.png"]


def _load_sprite(name):
    path = os.path.join(SPRITES_DIR, name)
    img = pygame.image.load(path).convert_alpha()
    w, h = img.get_size()
    return pygame.transform.scale(img, (int(w * SPRITE_SCALE), int(h * SPRITE_SCALE)))


class Sonda:
    FRICTION_COAST  = 0.90    # freno rápido al soltar (baja a ~15% en ~0.5s)
    FRICTION_DRIFT  = 1.0     # deriva constante: no decae más
    DRIFT_THRESHOLD = 0.15    # fracción de speed donde cambia de fase
    ACCEL           = 0.6     # aceleración por frame al presionar tecla
    ACCEL_RAMP      = 180     # frames hasta velocidad máxima (~3s a 60fps)
    MAX_V_START     = 0.75    # fracción del speed al comenzar a moverse

    def __init__(self, start_x, start_y, speed=2):
        self.speed = speed

        self.sprites = [_load_sprite(name) for name in SPRITE_NAMES]
        self.skin_index = 0
        self.image = self.sprites[self.skin_index]
        self.w, self.h = self.image.get_size()

        self.x = float(start_x - self.w // 2)
        self.y = float(start_y - self.h // 2)
        self.vx = 0.0
        self.vy = 0.0
        self._thrust_frames = 0   # frames consecutivos presionando tecla

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RIGHT:
                self.skin_index = (self.skin_index + 1) % len(self.sprites)
                self.image = self.sprites[self.skin_index]
            elif event.key == pygame.K_LEFT:
                self.skin_index = (self.skin_index - 1) % len(self.sprites)
                self.image = self.sprites[self.skin_index]

    def update(self, keys):
        pressing = (keys[pygame.K_w] or keys[pygame.K_s] or
                    keys[pygame.K_a] or keys[pygame.K_d])

        if pressing:
            self._thrust_frames = min(self._thrust_frames + 1, self.ACCEL_RAMP)
        else:
            self._thrust_frames = 0

        # max_v sube linealmente de 75% → 100% en ACCEL_RAMP frames
        t = self._thrust_frames / self.ACCEL_RAMP
        max_v = self.speed * (self.MAX_V_START + (1.0 - self.MAX_V_START) * t)

        if keys[pygame.K_w]:
            self.vy -= self.ACCEL
        if keys[pygame.K_s]:
            self.vy += self.ACCEL
        if keys[pygame.K_a]:
            self.vx -= self.ACCEL
        if keys[pygame.K_d]:
            self.vx += self.ACCEL
        if self.vx > max_v:  self.vx = max_v
        if self.vx < -max_v: self.vx = -max_v
        if self.vy > max_v:  self.vy = max_v
        if self.vy < -max_v: self.vy = -max_v

        # Aplicar inercia en dos fases
        drift_v = self.speed * self.DRIFT_THRESHOLD
        spd = (self.vx ** 2 + self.vy ** 2) ** 0.5
        friction = self.FRICTION_DRIFT if spd <= drift_v else self.FRICTION_COAST
        self.vx *= friction
        self.vy *= friction

        self.x += self.vx
        self.y += self.vy

    def get_camera(self, screen_w, screen_h):
        cam_x = int(self.x + self.w // 2 - screen_w // 2)
        cam_y = int(self.y + self.h // 2 - screen_h // 2)
        return cam_x, cam_y

    def draw(self, surface, cam_x, cam_y):
        surface.blit(self.image, (int(self.x) - cam_x, int(self.y) - cam_y))
