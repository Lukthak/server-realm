import math
import random
import sys
from dataclasses import dataclass

import pygame


WIDTH = 1100
HEIGHT = 700
FPS = 60

BLACK = (0, 0, 0)
TEXT_COLOR = (238, 238, 238)


@dataclass
class Star:
    kind: str
    x: int
    y: int
    radius: int
    color: tuple[int, int, int]
    pulse_speed: float
    pulse_offset: float
    planets: list["Planet"]


@dataclass
class Planet:
    orbit_radius: float
    orbit_speed: float
    radius: int
    color: tuple[int, int, int]
    angle: float
    vertical_tilt: float
    depth_strength: float
    moons: list["Moon"]


@dataclass
class Moon:
    orbit_radius: float
    orbit_speed: float
    radius: int
    color: tuple[int, int, int]
    angle: float


STAR_TYPES: list[tuple[str, tuple[int, int, int], tuple[int, int]]] = [
    ("azul", (95, 155, 255), (7, 11)),
    ("roja", (255, 88, 88), (4, 7)),
    ("naranja", (255, 168, 65), (5, 8)),
    ("celeste", (145, 235, 255), (6, 10)),
]


def create_planets(kind: str, star_radius: int) -> list[Planet]:
    if kind == "azul":
        planet_count = random.randint(3, 5)
        orbit_base = star_radius * 4.5
    elif kind == "celeste":
        planet_count = random.randint(2, 4)
        orbit_base = star_radius * 4.0
    elif kind == "naranja":
        planet_count = random.randint(1, 3)
        orbit_base = star_radius * 3.5
    else:
        planet_count = random.randint(0, 2)
        orbit_base = star_radius * 3.0

    planet_palette = [
        (170, 170, 190),
        (120, 185, 120),
        (190, 145, 110),
        (110, 160, 210),
        (220, 210, 170),
    ]

    planets: list[Planet] = []
    for index in range(planet_count):
        orbit_radius = orbit_base + index * random.uniform(star_radius * 1.5, star_radius * 2.2)
        orbit_speed = random.uniform(0.35, 1.15) / max(1.0, orbit_radius / star_radius)
        planet_radius = random.randint(2, 4 if kind in {"azul", "celeste"} else 3)
        planets.append(
            Planet(
                orbit_radius=orbit_radius,
                orbit_speed=orbit_speed,
                radius=planet_radius,
                color=random.choice(planet_palette),
                angle=random.uniform(0.0, math.tau),
                vertical_tilt=random.uniform(0.25, 0.55),
                depth_strength=random.uniform(0.35, 0.75),
                moons=create_moons(planet_radius),
            )
        )

    return planets


def create_moons(planet_radius: int) -> list[Moon]:
    if planet_radius <= 2:
        moon_count = 0
    elif planet_radius == 3:
        moon_count = random.randint(0, 1)
    elif planet_radius == 4:
        moon_count = random.randint(1, 2)
    elif planet_radius == 5:
        moon_count = random.randint(2, 3)
    elif planet_radius == 6:
        moon_count = random.randint(3, 5)
    else:
        moon_count = random.randint(5, 8)

    moons: list[Moon] = []
    base_color = (220, 220, 220)
    for index in range(moon_count):
        orbit_radius = planet_radius * 2.2 + index * random.uniform(1.8, 3.0)
        orbit_speed = random.uniform(1.0, 2.8) / max(1.0, orbit_radius / planet_radius)
        moons.append(
            Moon(
                orbit_radius=orbit_radius,
                orbit_speed=orbit_speed,
                radius=1,
                color=base_color,
                angle=random.uniform(0.0, math.tau),
            )
        )

    return moons


def create_star(x: int, y: int) -> Star:
    kind, color, size_range = random.choice(STAR_TYPES)
    radius = random.randint(size_range[0], size_range[1])
    return Star(
        kind=kind,
        x=x,
        y=y,
        radius=radius,
        color=color,
        pulse_speed=random.uniform(1.2, 3.2),
        pulse_offset=random.uniform(0.0, math.tau),
        planets=create_planets(kind, radius),
    )


def draw_planets(surface: pygame.Surface, star: Star, t: float, front_only: bool | None = None) -> None:
    for planet in star.planets:
        angle = planet.angle + t * planet.orbit_speed
        depth = math.sin(angle)
        is_front = depth >= 0.0

        if front_only is True and not is_front:
            continue
        if front_only is False and is_front:
            continue

        px = int(star.x + math.cos(angle) * planet.orbit_radius)
        py = int(star.y + math.sin(angle) * planet.orbit_radius * planet.vertical_tilt)
        depth_scale = 0.52 + ((depth + 1.0) * 0.5) * planet.depth_strength
        scaled_radius = max(1, int(planet.radius * depth_scale))

        pygame.draw.circle(surface, planet.color, (px, py), scaled_radius)

        for moon in planet.moons:
            moon_angle = moon.angle + t * moon.orbit_speed
            mx = int(px + math.cos(moon_angle) * moon.orbit_radius)
            my = int(py + math.sin(moon_angle) * moon.orbit_radius * 0.6)
            pygame.draw.circle(surface, moon.color, (mx, my), moon.radius)


def draw_star(surface: pygame.Surface, star: Star, t: float) -> None:
    cx, cy = star.x, star.y

    shimmer_radius = int(star.radius * 3.2)
    shimmer_size = shimmer_radius * 2 + 6
    shimmer = pygame.Surface((shimmer_size, shimmer_size), pygame.SRCALPHA)
    scx = shimmer_size // 2
    scy = shimmer_size // 2

    band_count = 17
    for band in range(band_count):
        start_y = scy - int(star.radius * 2.8)
        step = int((star.radius * 5.6) / max(1, band_count - 1))
        y_base = start_y + band * max(1, step)
        phase = t * (2.5 + star.pulse_speed * 0.5) + band * 0.9 + star.pulse_offset

        points: list[tuple[int, int]] = []
        for x in range(0, shimmer_size, 2):
            dx = abs(x - scx)
            envelope = max(0.0, 1.0 - dx / max(1, shimmer_radius))
            wave = math.sin(x * 0.18 + phase) * (1.2 + star.radius * 0.08) * envelope
            points.append((x, int(y_base + wave)))

        alpha = max(28, min(96, int(40 + (math.sin(phase) + 1.0) * 18 + (math.sin(t * 1.6 + band) + 1.0) * 10)))
        if len(points) > 1:
            # Black alpha lines erase the pixels they cross against the dark background.
            pygame.draw.aalines(shimmer, (0, 0, 0, alpha), False, points)

            soft_points = [(px, py + 1) for px, py in points]
            soft_alpha = max(12, alpha // 2)
            pygame.draw.aalines(shimmer, (0, 0, 0, soft_alpha), False, soft_points)

    glow_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

    pulse = (math.sin(t * star.pulse_speed + star.pulse_offset) + 1.0) * 0.5
    outer_alpha = int(18 + pulse * 24)
    mid_alpha = int(36 + pulse * 38)
    outer_r = int(star.radius * 2.7)
    mid_r = int(star.radius * 1.8)

    pygame.draw.circle(glow_surface, (*star.color, outer_alpha), (cx, cy), outer_r)
    pygame.draw.circle(glow_surface, (*star.color, mid_alpha), (cx, cy), mid_r)
    surface.blit(glow_surface, (0, 0))

    pygame.draw.circle(surface, star.color, (cx, cy), star.radius)
    core_radius = max(2, int(star.radius * 0.55))
    pygame.draw.circle(surface, (255, 255, 255), (cx, cy), core_radius)

    # Back planets first so the star can partially occlude them.
    draw_planets(surface, star, t, front_only=False)

    # Draw heat haze on top so it overlays the star body.
    surface.blit(shimmer, (cx - scx, cy - scy))

    # Front planets after the haze so they feel closer to the camera.
    draw_planets(surface, star, t, front_only=True)


def draw_ui(surface: pygame.Surface, font: pygame.font.Font, count: int) -> None:
    text = f"Clic izquierdo: nueva estrella | C: limpiar | ESC: salir | Total: {count}"
    label = font.render(text, True, TEXT_COLOR)
    surface.blit(label, (22, HEIGHT - 36))


def main() -> None:
    pygame.init()
    pygame.display.set_caption("Creador de Estrellas")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 20)

    running = True
    global_time = 0.0
    stars: list[Star] = [create_star(WIDTH // 2, HEIGHT // 2)]

    while running:
        dt = clock.tick(FPS) / 1000.0
        global_time += dt

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_c:
                    stars.clear()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                stars.append(create_star(*event.pos))

        screen.fill(BLACK)

        for star in stars:
            draw_star(screen, star, global_time)

        draw_ui(screen, font, len(stars))

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
