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
    FRICTION_COAST  = 0.995   # al soltar: tarda ~6s en llegar a deriva lenta
    FRICTION_DRIFT  = 1.0     # deriva constante: no decae más
    DRIFT_THRESHOLD = 0.15    # fracción de speed donde cambia a deriva eterna
    SPACE_BRAKE     = 0.05    # freno manual por frame mientras se mantiene Espacio
    ACCEL           = 0.6     # aceleración por frame al presionar tecla
    ACCEL_RAMP      = 180     # frames hasta velocidad máxima (~3s a 60fps)
    MAX_V_START     = 0.25    # arranca en 0.5 (si speed=2), luego sube al máximo
    ROT_SPEED       = 2.2     # grados/frame máximos con Q/E
    ROT_RAMP        = 120     # frames hasta velocidad máxima de giro (~2s a 60fps)
    ROT_STOP_FRAMES = 600     # al soltar Q/E, tarda ~10s en frenar giro a 0
    ROT_SNAP_DEG    = 3.0     # mini bloqueo cerca de 0° para recentrar fácil
    _SC_Q           = 20      # SDL scancode físico de Q
    _SC_E           = 8       # SDL scancode físico de E

    def __init__(self, start_x, start_y, speed=2):
        self.speed = speed

        self.sprites = [_load_sprite(name) for name in SPRITE_NAMES]
        self.skin_index = 0
        self.angle = 0.0
        self.image = self.sprites[self.skin_index]
        self.w, self.h = self.image.get_size()
        self.base_w, self.base_h = self.w, self.h

        # Posición lógica (top-left del sprite base sin rotar): estable para física/red.
        self.x = float(start_x - self.base_w / 2)
        self.y = float(start_y - self.base_h / 2)
        self.vx = 0.0
        self.vy = 0.0
        self._thrust_frames = 0   # frames consecutivos presionando tecla
        self._rot_frames = 0      # frames consecutivos girando
        self._rot_vel = 0.0       # velocidad angular actual (grados/frame)
        self._rot_left = False
        self._rot_right = False

    @staticmethod
    def _norm_angle(deg):
        """Normaliza a rango [-180, 180)."""
        return ((deg + 180.0) % 360.0) - 180.0

    def _refresh_image(self):
        """Recompone sprite según skin + ángulo, anclado al centro lógico."""
        base = self.sprites[self.skin_index]
        self.base_w, self.base_h = base.get_size()
        # pygame rota CCW, por eso usamos ángulo negativo para giro horario con E
        self.image = pygame.transform.rotate(base, -self.angle)
        self.w, self.h = self.image.get_size()

    def _world_center(self):
        """Centro lógico en mundo basado en sprite base (sin rotar)."""
        return (self.x + self.base_w / 2, self.y + self.base_h / 2)

    def get_label_anchor(self, cam_x, cam_y):
        """Centro X y borde inferior Y del sprite base (sin rotar), en pantalla."""
        cx_world, cy_world = self._world_center()
        cx_screen = int(cx_world - cam_x)
        bottom_screen = int(cy_world + self.base_h / 2 - cam_y)
        return cx_screen, bottom_screen

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            ch = (event.unicode or "").lower()
            is_q = (ch == "q" or event.key == pygame.K_q or
                    getattr(event, "scancode", -1) == self._SC_Q)
            is_e = (ch == "e" or event.key == pygame.K_e or
                    getattr(event, "scancode", -1) == self._SC_E)
            if is_q:
                was_rotating = self._rot_left or self._rot_right
                self._rot_left = True
                if not was_rotating:
                    self._rot_frames = 0
            if is_e:
                was_rotating = self._rot_left or self._rot_right
                self._rot_right = True
                if not was_rotating:
                    self._rot_frames = 0
            if event.key == pygame.K_RIGHT:
                self.skin_index = (self.skin_index + 1) % len(self.sprites)
                self._refresh_image()
            elif event.key == pygame.K_LEFT:
                self.skin_index = (self.skin_index - 1) % len(self.sprites)
                self._refresh_image()
        elif event.type == pygame.KEYUP:
            ch = (event.unicode or "").lower()
            if (ch == "q" or event.key == pygame.K_q or
                    getattr(event, "scancode", -1) == self._SC_Q):
                self._rot_left = False
            if (ch == "e" or event.key == pygame.K_e or
                    getattr(event, "scancode", -1) == self._SC_E):
                self._rot_right = False

    def update(self, keys):
        rot_dir = 0
        # Flags por evento + fallback por keycode para máxima compatibilidad.
        if self._rot_left or keys[pygame.K_q]:
            rot_dir -= 1
        if self._rot_right or keys[pygame.K_e]:
            rot_dir += 1

        if rot_dir:
            self._rot_frames = min(self._rot_frames + 1, self.ROT_RAMP)
            tr = self._rot_frames / self.ROT_RAMP
            self._rot_vel = rot_dir * (self.ROT_SPEED * tr)
            prev_norm = self._norm_angle(self.angle)
            self.angle = (self.angle + self._rot_vel) % 360.0
            cur_norm = self._norm_angle(self.angle)
            # Mini bloqueo solo al cruzar hacia 0 desde afuera.
            if abs(prev_norm) > self.ROT_SNAP_DEG and abs(cur_norm) <= self.ROT_SNAP_DEG:
                self.angle = 0.0
                self._rot_vel = 0.0
            self._refresh_image()
        else:
            self._rot_frames = 0
            # Inercia de rotación: al soltar Q/E, frena progresivamente en ~10s.
            if self._rot_vel != 0.0:
                rot_decel = self.ROT_SPEED / self.ROT_STOP_FRAMES
                if abs(self._rot_vel) <= rot_decel:
                    self._rot_vel = 0.0
                else:
                    self._rot_vel -= rot_decel if self._rot_vel > 0 else -rot_decel
                self.angle = (self.angle + self._rot_vel) % 360.0
                self._refresh_image()

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
        # Durante empuje, converger al límite vectorial (sin cortes bruscos).
        if pressing:
            spd = (self.vx ** 2 + self.vy ** 2) ** 0.5
            if spd > max_v and spd > 0:
                target_k = max_v / spd
                clamp_blend = 0.28
                k = 1.0 + (target_k - 1.0) * clamp_blend
                self.vx *= k
                self.vy *= k

        # Al soltar movimiento: freno inicial + deriva eterna muy lenta.
        if not pressing:
            drift_v = self.speed * self.DRIFT_THRESHOLD
            spd = (self.vx ** 2 + self.vy ** 2) ** 0.5
            friction = self.FRICTION_DRIFT if spd <= drift_v else self.FRICTION_COAST
            self.vx *= friction
            self.vy *= friction

        # Freno manual: mantener Espacio reduce la velocidad en 0.1 por frame.
        if keys[pygame.K_SPACE]:
            spd = (self.vx ** 2 + self.vy ** 2) ** 0.5
            if spd > 0.0:
                if spd <= self.SPACE_BRAKE:
                    self.vx = 0.0
                    self.vy = 0.0
                else:
                    k = (spd - self.SPACE_BRAKE) / spd
                    self.vx *= k
                    self.vy *= k

        self.x += self.vx
        self.y += self.vy

    def get_camera(self, screen_w, screen_h):
        cx_world, cy_world = self._world_center()
        cam_x = int(cx_world - screen_w // 2)
        cam_y = int(cy_world - screen_h // 2)
        return cam_x, cam_y

    def draw(self, surface, cam_x, cam_y):
        cx_world, cy_world = self._world_center()
        cx_screen = int(cx_world - cam_x)
        cy_screen = int(cy_world - cam_y)
        sx = cx_screen - self.w // 2
        sy = cy_screen - self.h // 2
        surface.blit(self.image, (sx, sy))
