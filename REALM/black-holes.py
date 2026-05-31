import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.widgets as mwidgets
from matplotlib.colors import LinearSegmentedColormap

# ── Parámetros fijos ──────────────────────────────────────────────────────────
STARS_PER_ARM  = 1200
CORE_STARS     = 800
DUST_PARTICLES = 600
GALAXY_RADIUS  = 10.0
CORE_RADIUS    = 1.2
galaxy_scale   = [0.3]   # factor de tamaño: 0.1 (pequeña) – 1.0 (grande)

# Velocidad angular base (rad/frame). El centro rota más rápido.
OMEGA_SCALE    = 0.0018   # ajusta la velocidad general
ROT_SOFTENING  = 1.2      # evita velocidades infinitas en r≈0

# ── Helpers ───────────────────────────────────────────────────────────────────

def spiral_arm(n, arm_index, n_arms, turns, radius, spread, rng):
    t = rng.power(0.55, n) * turns * np.pi
    r = (t / (turns * np.pi)) * radius
    theta = t + (2 * np.pi * arm_index) / n_arms
    x = (r + rng.normal(0, spread * r + 0.05, n)) * np.cos(theta + rng.normal(0, spread * 0.12, n))
    y = (r + rng.normal(0, spread * r + 0.05, n)) * np.sin(theta + rng.normal(0, spread * 0.12, n))
    return x, y


def core_cluster(n, core_r, rng):
    r     = np.abs(rng.normal(0, core_r * 0.45, n))
    theta = rng.uniform(0, 2 * np.pi, n)
    return r * np.cos(theta), r * np.sin(theta)


def star_colors_rgba(n, rng, alpha_range=(0.25, 1.0), tint=None):
    """Colores estelares RGBA con tinte de nebulosa opcional (RGB 0-1)."""
    palette = np.array([
        [0.67, 0.83, 1.00],   # azul-blanco
        [1.00, 1.00, 1.00],   # blanco
        [1.00, 0.96, 0.80],   # blanco-amarillo
        [1.00, 0.84, 0.50],   # amarillo
        [1.00, 0.67, 0.33],   # naranja
    ])
    weights = [0.25, 0.40, 0.20, 0.10, 0.05]
    idx    = rng.choice(len(palette), size=n, p=weights)
    rgb    = palette[idx].copy()
    if tint is not None:
        # mezcla 40% del tinte con el color estelar base
        mix = rng.uniform(0.0, 0.45, (n, 1))
        rgb = rgb * (1 - mix) + np.array(tint) * mix
    bright = rng.uniform(0.4, 1.0, (n, 1))
    rgb    = np.clip(rgb * bright, 0, 1)
    alpha  = rng.uniform(*alpha_range, (n, 1))
    return np.hstack([rgb, alpha])


# Paletas de nebulosa: cada entrada es (color_interior, color_brazo, dust_colors)
NEBULA_THEMES = [
    # teal/verde
    {'inner': (0.20, 0.85, 0.75), 'arm': (0.10, 0.70, 0.80),
     'dust': ['#041a14', '#062a20', '#0a3d30', '#051f18']},
    # rojo/magenta
    {'inner': (0.95, 0.20, 0.35), 'arm': (0.85, 0.15, 0.55),
     'dust': ['#1a0408', '#2a060f', '#3d0a18', '#1f0510']},
    # azul/violeta (clásico)
    {'inner': (0.45, 0.55, 1.00), 'arm': (0.30, 0.40, 0.90),
     'dust': ['#0a0a1a', '#1a1040', '#2a1a5a', '#0d0820']},
    # naranja/dorado
    {'inner': (1.00, 0.55, 0.10), 'arm': (0.90, 0.40, 0.05),
     'dust': ['#1a0e00', '#2a1800', '#3d2600', '#1f1000']},
    # rosa/lavanda
    {'inner': (0.90, 0.50, 0.90), 'arm': (0.70, 0.35, 0.85),
     'dust': ['#180a18', '#281028', '#3a1a3d', '#1a0820']},
    # aguamarina/cian
    {'inner': (0.10, 0.90, 0.95), 'arm': (0.05, 0.70, 0.85),
     'dust': ['#001a1c', '#002a2e', '#003d40', '#001f22']},
]


def omega(r):
    """Velocidad angular diferencial: más rápido en el centro. Negativa = CW."""
    return -OMEGA_SCALE / (r / GALAXY_RADIUS + ROT_SOFTENING / GALAXY_RADIUS)


def rotate(gx, gy, dtheta):
    """Rota en el plano galáctico."""
    r  = np.hypot(gx, gy)
    th = np.arctan2(gy, gx) + dtheta
    return r * np.cos(th), r * np.sin(th)


# view_params: proyección del plano galáctico a pantalla
#   pa   = ángulo de posición (rotación del disco en pantalla)
#   tilt = factor de inclinación en eje menor (1=cara, ~0.1=canto)
view_params  = {'pa': 0.0, 'tilt': 1.0}

def project(gx, gy):
    """Aplica inclinación + ángulo de posición."""
    pa   = view_params['pa']
    tilt = view_params['tilt']
    sx = np.cos(pa) * gx - np.sin(pa) * gy * tilt
    sy = np.sin(pa) * gx + np.cos(pa) * gy * tilt
    return sx, sy


# ── Estado global de la animación ─────────────────────────────────────────────
# Cada entrada de `particles` es un dict con:
#   'gx', 'gy' : coordenadas en plano galáctico (se rotan)
#   'omega'    : velocidad angular de cada punto (array)
#   'sc'       : objeto PathCollection (scatter)
#   'fixed'    : si True, no se proyecta (campo de fondo)
particles    = []
anim_obj     = [None]
current_seed = [42]

# ── Construcción de la galaxia ────────────────────────────────────────────────

def build_galaxy(seed):
    global particles
    scale  = galaxy_scale[0]
    radius = GALAXY_RADIUS * scale
    cr     = CORE_RADIUS   * scale
    # Conteos proporcionales al tamaño (mínimo 40 para que siempre haya algo)
    stars_per_arm  = max(40, int(STARS_PER_ARM  * scale))
    core_stars     = max(20, int(CORE_STARS     * scale))
    dust_particles = max(20, int(DUST_PARTICLES * scale))
    rng = np.random.default_rng(seed)
    ax.clear()
    particles = []
    ax.set_facecolor('black')
    ax.set_aspect('equal')
    ax.axis('off')
    lim = GALAXY_RADIUS * 1.55          # límite de vista siempre fijo
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)

    # ── Ángulo de vista aleatorio
    view_params['pa']   = rng.uniform(0, np.pi)          # orientación en pantalla
    view_params['tilt'] = rng.uniform(0.18, 0.95)        # 1=cara, 0.18=casi de canto

    # ── Campo estelar de fondo (fijo en pantalla, no proyectado)
    bg_n  = 720
    bx    = rng.uniform(-lim, lim, bg_n)
    by    = rng.uniform(-lim, lim, bg_n)
    ba    = rng.uniform(0.05, 0.5, (bg_n, 1))
    bb    = rng.uniform(0.5, 1.0, (bg_n, 1))
    brgba = np.hstack([np.ones((bg_n, 3)) * bb, ba])
    sc_bg = ax.scatter(bx, by, s=rng.uniform(0.05, 1.2, bg_n),
                       c=brgba, linewidths=0)
    particles.append({'gx': bx, 'gy': by,
                      'omega': omega(np.hypot(bx, by)) * 0.0,
                      'sc': sc_bg, 'fixed': True})

    # ── Parámetros espirales
    n_arms = int(rng.integers(2, 6))
    turns  = rng.uniform(3.5, 5.5)
    spread = rng.uniform(0.06, 0.13)

    # ── Tema de color para esta galaxia
    theme = NEBULA_THEMES[int(rng.integers(0, len(NEBULA_THEMES)))]
    dust_cmap = LinearSegmentedColormap.from_list('dust', theme['dust'])

    # ── Polvo espiral
    dust_per_arm = dust_particles // n_arms
    dxl, dyl = [], []
    for i in range(n_arms):
        t  = rng.power(0.55, dust_per_arm) * turns * np.pi
        r  = (t / (turns * np.pi)) * radius
        th = t + (2 * np.pi * i) / n_arms
        nr = rng.normal(0, spread * r * 2.5 + 0.3 * scale, dust_per_arm)
        nt = rng.normal(0, spread * 0.6, dust_per_arm)
        dxl.append((r + nr) * np.cos(th + nt))
        dyl.append((r + nr) * np.sin(th + nt))
    dx = np.concatenate(dxl);  dy = np.concatenate(dyl)
    td = len(dx)
    sx, sy = project(dx, dy)
    sc_dust = ax.scatter(sx, sy, s=rng.uniform(60, 300, td),
                         c=[dust_cmap(v) for v in rng.uniform(0, 1, td)],
                         alpha=0.06, linewidths=0)
    particles.append({'gx': dx, 'gy': dy,
                      'omega': omega(np.hypot(dx, dy)),
                      'sc': sc_dust, 'fixed': False})

    # ── Brazos espirales
    axl, ayl, acl, asl = [], [], [], []
    for i in range(n_arms):
        ax_, ay_ = spiral_arm(stars_per_arm, i, n_arms, turns, radius, spread, rng)
        axl.append(ax_);  ayl.append(ay_)
        dist = np.hypot(ax_, ay_)
        # tinte varía con la distancia al centro: interior=inner, exterior=arm
        t_blend = np.clip(dist / radius, 0, 1)  # 0=centro, 1=borde
        inner_t = np.array(theme['inner'])
        arm_t   = np.array(theme['arm'])
        # tinte por estrella
        per_star_tint = inner_t[np.newaxis, :] * (1 - t_blend[:, np.newaxis]) + \
                        arm_t[np.newaxis, :] * t_blend[:, np.newaxis]
        # construir RGBA manualmente con tinte por estrella
        n_s = stars_per_arm
        palette = np.array([
            [0.67, 0.83, 1.00], [1.00, 1.00, 1.00], [1.00, 0.96, 0.80],
            [1.00, 0.84, 0.50], [1.00, 0.67, 0.33]])
        w = [0.25, 0.40, 0.20, 0.10, 0.05]
        idx = rng.choice(5, size=n_s, p=w)
        rgb = palette[idx]
        mix = rng.uniform(0.0, 0.45, (n_s, 1))
        rgb = rgb * (1 - mix) + per_star_tint * mix
        bright = rng.uniform(0.4, 1.0, (n_s, 1))
        rgb = np.clip(rgb * bright, 0, 1)
        alpha = rng.uniform(0.2, 0.95, (n_s, 1))
        acl.append(np.hstack([rgb, alpha]))
        asl.append(rng.uniform(0.3, 3.5, n_s) * (1 - dist / (radius * 1.4) + 0.3))
    axc = np.concatenate(axl);  ayc = np.concatenate(ayl)
    sxc, syc = project(axc, ayc)
    sc_arms = ax.scatter(sxc, syc, s=np.concatenate(asl),
                         c=np.concatenate(acl), linewidths=0)
    particles.append({'gx': axc, 'gy': ayc,
                      'omega': omega(np.hypot(axc, ayc)),
                      'sc': sc_arms, 'fixed': False})

    # ── Halo del núcleo
    hx_all, hy_all, hs_all, ha_all = [], [], [], []
    for hrad, halpha in [(3.5, 0.025), (2.2, 0.06), (1.4, 0.12), (0.7, 0.22)]:
        hr = np.abs(rng.normal(0, hrad * scale * 0.5, 1200))
        ht = rng.uniform(0, 2 * np.pi, 1200)
        hx_all.append(hr * np.cos(ht));  hy_all.append(hr * np.sin(ht))
        hs_all.append(rng.uniform(40, 200, 1200))
        ha_all.append(np.full(1200, halpha))
    hxc = np.concatenate(hx_all);  hyc = np.concatenate(hy_all)
    hsc = np.concatenate(hs_all);  hac = np.concatenate(ha_all)
    # Halo con gradiente del color interior del tema
    inner_rgb = np.array(theme['inner'])
    halo_rgb  = np.clip(inner_rgb * 0.9 + np.array([1.0, 0.91, 0.67]) * 0.1, 0, 1)
    rgba_halo = np.column_stack([
        np.ones((len(hxc), 3)) * halo_rgb,
        hac])
    shxc, shyc = project(hxc, hyc)
    sc_halo = ax.scatter(shxc, shyc, s=hsc, c=rgba_halo, linewidths=0)
    particles.append({'gx': hxc, 'gy': hyc,
                      'omega': omega(np.hypot(hxc, hyc)) * 1.4,
                      'sc': sc_halo, 'fixed': False})

    # ── Núcleo estelar
    cx, cy = core_cluster(core_stars, cr, rng)
    scx, scy = project(cx, cy)
    sc_core = ax.scatter(scx, scy, s=rng.uniform(0.4, 5.0, core_stars),
                         c=star_colors_rgba(core_stars, rng, alpha_range=(0.4, 1.0),
                                            tint=theme['inner']),
                         linewidths=0)
    particles.append({'gx': cx, 'gy': cy,
                      'omega': omega(np.hypot(cx, cy)) * 1.8,
                      'sc': sc_core, 'fixed': False})

    # ── Punto central (escala con la galaxia)
    s2 = scale ** 2   # área proporcional a escala²
    ax.scatter([0], [0], s=320 * s2, c='white',   alpha=1.00, linewidths=0, zorder=10)
    ax.scatter([0], [0], s=900 * s2, c='#fff5cc', alpha=0.35, linewidths=0, zorder=9)

    # ── Títulos
    fig.texts.clear()
    fig.text(0.5, 0.93, 'G A L A X Y   G E N E R A T O R',
             ha='center', fontsize=14, color='#aad4ff', fontfamily='monospace', alpha=0.8)
    fig.text(0.5, 0.07,
             f'Brazos: {n_arms}   ·   Estrellas: {n_arms * stars_per_arm + core_stars:,}'
             f'   ·   Semilla: {seed}   ·   Tamaño: {scale:.2f}   ·   [clic para nueva galaxia]',
             ha='center', fontsize=8, color='#556688', fontfamily='monospace')

    fig.canvas.draw_idle()


# ── Animación ─────────────────────────────────────────────────────────────────

def animate(_frame):
    for p in particles:
        if p['fixed']:
            continue
        ngx, ngy = rotate(p['gx'], p['gy'], p['omega'])
        p['gx'] = ngx;  p['gy'] = ngy
        sx, sy = project(ngx, ngy)
        p['sc'].set_offsets(np.column_stack([sx, sy]))
    return [p['sc'] for p in particles]


# ── Evento de clic ────────────────────────────────────────────────────────────

def on_click(event):
    # Ignorar clics sobre el slider
    if event.inaxes == ax_slider:
        return
    if event.button == 1:
        seed = np.random.randint(0, 2**31)
        current_seed[0] = seed
        build_galaxy(seed)


def on_scale_change(val):
    galaxy_scale[0] = slider.val
    build_galaxy(current_seed[0])


# ── Main ──────────────────────────────────────────────────────────────────────

fig = plt.figure(figsize=(10, 10.6), facecolor='black')
ax  = fig.add_axes([0, 0.06, 1, 0.94])     # galaxia

# Slider de tamaño
ax_slider = fig.add_axes([0.15, 0.015, 0.70, 0.025], facecolor='#111122')
slider = mwidgets.Slider(
    ax_slider, 'Tamaño', 0.08, 1.0,
    valinit=1.0, valstep=0.01,
    color='#334477')
slider.label.set_color('#aad4ff')
slider.valtext.set_color('#aad4ff')
slider.on_changed(on_scale_change)

fig.canvas.mpl_connect('button_press_event', on_click)

build_galaxy(seed=42)

anim_obj[0] = animation.FuncAnimation(
    fig, animate, interval=30, blit=True, cache_frame_data=False)

plt.show()

