import pygame
import random
import sys
import math
import asyncio
from pathlib import Path

# Window Initialize
pygame.init()
pygame.font.init()
W, H = 1000, 700
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("枪战游戏")
clock = pygame.time.Clock()

# Sound is optional: a missing/blocked device never prevents the game from
# starting.  Effects are synthesized, keeping the project self-contained.
IS_WEB = sys.platform in ("emscripten", "wasi")
TARGET_FPS = 50 if IS_WEB else 60
try:
    # Safari/Pygbag can expose the mixer before its audio backend is ready.
    # Initializing or decoding sounds at import time then stops the whole game
    # before the first frame, leaving only a grey canvas.  Web audio is kept
    # optional so gameplay always starts; desktop audio remains unchanged.
    if IS_WEB:
        SOUND_READY = False
    else:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        pygame.mixer.set_num_channels(16)
        SOUND_READY = True
except Exception:
    SOUND_READY = False
# Large battlefield with visible landmarks for camera movement.
WORLD_W, WORLD_H = 4000, 2800
CAMERA_X, CAMERA_Y = 0, 0
HIT_SHAKE_X, HIT_SHAKE_Y = 0.0, 0.0
HIT_SHAKE_TIMER, HIT_SHAKE_POWER = 0, 0.0
# Original encounter cadence.
NORMAL_SPAWN_INTERVAL = 35

BACKGROUND_CLOUDS = [
    (260, 280, 1.0), (980, 480, 1.3), (1720, 220, 0.9), (2580, 620, 1.4),
    (3420, 300, 1.1), (540, 1660, 1.2), (1500, 1420, 1.0), (2280, 1830, 1.3),
    (1850, 1660, 1.1), (3200, 1540, 0.9), (3650, 2260, 1.4), (1100, 2450, 1.1),
]
BACKGROUND_TRIANGLES = [
    (620, 760, 90), (1320, 980, 120), (2080, 460, 105), (2860, 1160, 130),
    (2320, 1510, 100), (3600, 920, 95), (360, 2220, 125), (1840, 2360, 110), (2660, 2460, 140),
]

def world_to_screen(x, y):
    return x - CAMERA_X + HIT_SHAKE_X, y - CAMERA_Y + HIT_SHAKE_Y

def update_hit_shake():
    """Decay a short world-only camera kick while leaving the HUD stable."""
    global HIT_SHAKE_X, HIT_SHAKE_Y, HIT_SHAKE_TIMER, HIT_SHAKE_POWER
    if HIT_SHAKE_TIMER > 0:
        ratio = HIT_SHAKE_TIMER / 10.0
        strength = HIT_SHAKE_POWER * min(1.0, ratio)
        HIT_SHAKE_X = random.uniform(-strength, strength)
        HIT_SHAKE_Y = random.uniform(-strength, strength)
        HIT_SHAKE_TIMER -= 1
        HIT_SHAKE_POWER *= 0.90
    else:
        HIT_SHAKE_X = HIT_SHAKE_Y = 0.0
        HIT_SHAKE_POWER = 0.0

def update_camera(player):
    """Let the player move visibly before the large-map camera starts scrolling."""
    global CAMERA_X, CAMERA_Y
    sx, sy = world_to_screen(player.x, player.y)
    left, right = W * 0.30, W * 0.70
    top, bottom = H * 0.30, H * 0.70
    if sx < left:
        CAMERA_X = player.x - left
    elif sx > right:
        CAMERA_X = player.x - right
    if sy < top:
        CAMERA_Y = player.y - top
    elif sy > bottom:
        CAMERA_Y = player.y - bottom
    CAMERA_X = max(0, min(WORLD_W - W, CAMERA_X))
    CAMERA_Y = max(0, min(WORLD_H - H, CAMERA_Y))

# Color Constants
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
YELLOW = (255, 220, 0)
DARK_RED = (120, 0, 0)
GRAY = (110, 110, 110)
DARK_GRAY = (40, 40, 40)
LIGHT_GRAY = (160, 160, 160)
ORANGE_FLASH = (255, 200, 0)
CARD_BG = (30, 30, 60)
CARD_BORDER = (80, 140, 255)
CARD_HOVER = (60, 80, 140)
CARD_RARE = (220, 160, 0)
CARD_EPIC = (160, 40, 220)
CARD_COMMON = (80, 100, 140)
BOSS_BAR_BG = (60, 0, 0)
WIN_BG = (10, 40, 10)
MENU_BG_MAIN = (255, 110, 30)
MENU_TRIANGLE_FADE = (255, 145, 70)
BTN_BG = (40, 60, 100)
BTN_HOVER = (70, 110, 180)
BTN_LOCKED = (70, 70, 70)
BTN_LOCKED_TEXT = (160, 160, 160)
GRID_COLOR = (44, 60, 44)
PURPLE = (180, 80, 220)

# Wasteland terminal UI palette.
UI_VOID = (10, 14, 16)
UI_METAL = (28, 35, 37)
UI_METAL_HOVER = (48, 56, 55)
UI_RUST = (118, 64, 30)
UI_ORANGE = (255, 136, 38)
UI_AMBER = (255, 202, 67)
UI_CYAN = (66, 226, 218)
UI_TEXT_DIM = (175, 186, 181)

# Image-backed button skin cache.  The source art gives every interactive
# control a real metal rim; state changes below provide hover/pressed depth.
UI_BUTTON_SKIN = None
UI_BUTTON_CACHE = {}
UI_CARD_SKIN = None
UI_CARD_CACHE = {}
UI_MOUSE_DOWN = False
WEB_GUN_ROTATION_CACHE = {}

def rotated_weapon_sprite(weapon, surface, angle):
    """Cache quantized weapon rotations in browsers to avoid a costly transform every frame."""
    if not IS_WEB:
        return pygame.transform.rotate(surface, -math.degrees(angle))
    bucket = int(round(math.degrees(angle) / 4.0)) % 90
    key = (weapon, bucket)
    cached = WEB_GUN_ROTATION_CACHE.get(key)
    if cached is None:
        cached = pygame.transform.rotate(surface, -(bucket * 4))
        WEB_GUN_ROTATION_CACHE[key] = cached
    return cached

def button_skin(size, state):
    if UI_BUTTON_SKIN is None:
        return None
    key = (max(1, int(size[0])), max(1, int(size[1])), state)
    if key in UI_BUTTON_CACHE:
        return UI_BUTTON_CACHE[key]
    surface = pygame.transform.smoothscale(UI_BUTTON_SKIN, key[:2]).convert_alpha()
    if state == "hover":
        glow = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        glow.fill((118, 94, 38, 18))
        surface.blit(glow, (0, 0))
    elif state == "disabled":
        shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        shade.fill((20, 25, 25, 145))
        surface.blit(shade, (0, 0))
    UI_BUTTON_CACHE[key] = surface
    return surface

def card_skin(size, state):
    if UI_CARD_SKIN is None:
        return None
    key = (max(1, int(size[0])), max(1, int(size[1])), state)
    if key in UI_CARD_CACHE:
        return UI_CARD_CACHE[key]
    surface = pygame.transform.smoothscale(UI_CARD_SKIN, key[:2]).convert_alpha()
    if state == "hover":
        glow = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        glow.fill((116, 84, 30, 16))
        surface.blit(glow, (0, 0))
    elif state == "selected":
        glow = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        glow.fill((32, 104, 100, 48))
        surface.blit(glow, (0, 0))
    elif state == "disabled":
        shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        shade.fill((20, 25, 25, 150))
        surface.blit(shade, (0, 0))
    UI_CARD_CACHE[key] = surface
    return surface

def draw_image_card_base(rect, mouse, enabled=True, selected=False):
    """Use the portrait metal panel for every clickable card surface."""
    rect = pygame.Rect(rect)
    hovered = enabled and rect.collidepoint(mouse)
    state = "disabled" if not enabled else ("selected" if selected else ("hover" if hovered else "normal"))
    art = card_skin(rect.size, state)
    pressed = hovered and (UI_MOUSE_DOWN or bool(pygame.mouse.get_pressed()[0]))
    if art:
        if pressed:
            shadow = art.copy()
            shadow.fill((0, 0, 0, 100), special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(shadow, (rect.x, rect.y + 3))
            screen.blit(art, (rect.x, rect.y + 2))
            return (0, 2)
        screen.blit(art, rect)
        return (0, 0)
    draw_wasteland_panel(rect, UI_ORANGE, UI_METAL, 2)
    return (0, 0)

def draw_image_button_base(rect, mouse, enabled=True, pressed=None):
    """Paint a tactile image button and return its text offset/state."""
    rect = pygame.Rect(rect)
    hovered = enabled and rect.collidepoint(mouse)
    if pressed is None:
        pressed = hovered and (UI_MOUSE_DOWN or bool(pygame.mouse.get_pressed()[0]))
    state = "disabled" if not enabled else ("hover" if hovered else "normal")
    art = button_skin(rect.size, state)
    if art:
        if pressed:
            # The shadow remains put while the face moves down: physical press.
            shadow = art.copy()
            shadow.fill((0, 0, 0, 115), special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(shadow, (rect.x, rect.y + 3))
            screen.blit(art, (rect.x, rect.y + 2))
            return (0, 2)
        screen.blit(art, rect)
        if hovered:
            pygame.draw.rect(screen, UI_CYAN, rect.inflate(-10, -10), 1, border_radius=4)
        return (0, 0)
    draw_wasteland_panel(rect, UI_ORANGE if enabled else (83, 89, 86), UI_METAL, 2)
    return (0, 0)

def draw_wasteland_panel(rect, accent=UI_ORANGE, fill=UI_METAL, border=3):
    """Draw a cut-corner metal panel with worn warning-line details."""
    rect = pygame.Rect(rect)
    cut = min(14, rect.width // 6, rect.height // 4)
    points = [(rect.left + cut, rect.top), (rect.right - cut, rect.top),
              (rect.right, rect.top + cut), (rect.right, rect.bottom - cut),
              (rect.right - cut, rect.bottom), (rect.left + cut, rect.bottom),
              (rect.left, rect.bottom - cut), (rect.left, rect.top + cut)]
    pygame.draw.polygon(screen, fill, points)
    pygame.draw.lines(screen, accent, True, points, border)
    pygame.draw.line(screen, UI_RUST, (rect.left + cut + 8, rect.top + 8), (rect.right - cut - 8, rect.top + 8), 1)
    pygame.draw.line(screen, (8, 10, 11), (rect.left + cut + 8, rect.bottom - 8), (rect.right - cut - 8, rect.bottom - 8), 2)

def draw_wasteland_button(rect, text, mouse, enabled=True, font=None):
    rect = pygame.Rect(rect)
    text_offset = draw_image_button_base(rect, mouse, enabled)
    label_font = font or font_menu_mid
    # The metal artwork has a thick frame, so type must fit the inset panel,
    # not the full rectangle.  This also bounds height for short buttons.
    label = fit_button_text(text, WHITE if enabled else UI_TEXT_DIM, rect, label_font.get_height())
    label_rect = label.get_rect(center=rect.center)
    label_rect.x += text_offset[0]
    label_rect.y += text_offset[1]
    screen.blit(label, label_rect)

def draw_wasteland_scanlines(alpha=22):
    layer = pygame.Surface((W, H), pygame.SRCALPHA)
    for y in range(0, H, 6):
        pygame.draw.line(layer, (255, 157, 55, alpha), (0, y), (W, y))
    screen.blit(layer, (0, 0))

# Stage Config
STAGE_LIVE_LIMIT = [
    {"basic": 12, "tank": 0, "fast": 0},
    {"basic": 10, "tank": 4, "fast": 0},
    {"basic": 10, "tank": 0, "fast": 6},
    {"basic": 10, "tank": 4, "fast": 6},
    {"basic": 0, "tank": 0, "fast": 0},
    {"basic": 11, "tank": 4, "fast": 5, "scout": 4, "brute": 2},
    {"basic": 12, "tank": 5, "fast": 6, "scout": 5, "brute": 3},
    {"basic": 12, "tank": 6, "fast": 7, "scout": 6, "brute": 4},
    {"basic": 13, "tank": 7, "fast": 8, "scout": 7, "brute": 5},
    {"basic": 14, "tank": 8, "fast": 9, "scout": 8, "brute": 6},
]
STAGE_KILL_QUOTA = [30, 40, 50, 60, 1, 75, 92, 112, 135, 160]
# Ground palettes stay dark and neutral so enemies, bullets and HUD remain
# legible without the old bright green field.
STAGE_BG_COLORS = [
    (45, 52, 54), (47, 45, 56), (56, 49, 42), (58, 40, 38), (50, 39, 56),
    (31, 48, 55), (53, 47, 36), (40, 42, 60), (55, 37, 46), (31, 43, 52),
]
STAGE_GROUND_ACCENTS = [
    (88, 75, 55), (74, 68, 100), (104, 76, 50), (112, 56, 47), (92, 55, 105),
    (48, 116, 128), (132, 103, 52), (83, 92, 144), (135, 54, 76), (48, 130, 119),
]
BATTLEFIELD_DEBRIS = [
    (180, 300, 26, 14), (540, 1060, 34, 16), (920, 510, 18, 38), (1280, 1780, 38, 18),
    (1650, 350, 30, 22), (1960, 1190, 20, 42), (2310, 640, 40, 17), (2660, 1510, 30, 24),
    (3090, 410, 22, 40), (3420, 1780, 44, 18), (3740, 930, 28, 25), (620, 2400, 40, 20),
    (1510, 2500, 28, 35), (2180, 2180, 42, 17), (2910, 2460, 30, 24), (3570, 2300, 38, 20),
]

FONT_CACHE = {}
BUNDLED_CJK_FONT = Path(__file__).resolve().parent / "wasteland-cn.ttf"

def chinese_font(size):
    """Return the original desktop face, or its web-safe visual match."""
    size = max(8, int(size))
    if size in FONT_CACHE:
        return FONT_CACHE[size]
    system_fonts = (
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
    )
    candidates = (BUNDLED_CJK_FONT,) if IS_WEB else system_fonts + (BUNDLED_CJK_FONT,)
    for path in candidates:
        if Path(path).exists():
            # Noto's web line box is about 7% taller than the original Arial
            # Unicode UI face.  Matching that metric restores the old visual
            # proportions without bringing back missing-glyph squares.
            actual_size = max(8, round(size * 0.93)) if Path(path) == BUNDLED_CJK_FONT else size
            FONT_CACHE[size] = pygame.font.Font(str(path), actual_size)
            return FONT_CACHE[size]
    FONT_CACHE[size] = pygame.font.SysFont(None, size)
    return FONT_CACHE[size]

font_big = chinese_font(90)
font_normal = chinese_font(36)
font_tip = chinese_font(42)
font_small = chinese_font(24)
font_card_title = chinese_font(22)
font_card_desc = chinese_font(16)
font_menu_large = chinese_font(54)
font_menu_mid = chinese_font(32)
font_menu_small = chinese_font(20)

def fit_text(text, color, max_width, start_size=24):
    """Render text small enough to remain inside its UI control."""
    size = start_size
    while size > 12:
        surface = chinese_font(size).render(text, True, color)
        if surface.get_width() <= max_width:
            return surface
        size -= 1
    return chinese_font(12).render(text, True, color)

def fit_button_text(text, color, rect, start_size=24):
    """Fit a label inside the actual recessed area of the button image."""
    rect = pygame.Rect(rect)
    max_width = max(28, int(rect.width * 0.63))
    max_height = max(12, int(rect.height * 0.42))
    for size in range(min(start_size, max_height), 9, -1):
        surface = chinese_font(size).render(text, True, color)
        if surface.get_width() <= max_width and surface.get_height() <= max_height:
            return surface
    return chinese_font(10).render(text, True, color)

def fit_card_text(text, color, rect, start_size=20):
    """Fit text inside the dark recessed center of a metal card image."""
    rect = pygame.Rect(rect)
    max_width = max(48, int(rect.width * 0.58))
    max_height = max(11, int(rect.height * 0.13))
    for size in range(min(start_size, max_height), 8, -1):
        surface = chinese_font(size).render(text, True, color)
        if surface.get_width() <= max_width and surface.get_height() <= max_height:
            return surface
    return chinese_font(9).render(text, True, color)

def wrap_card_lines(text, max_width, size, max_lines=2):
    """Wrap Chinese text by rendered width, preserving a readable font size."""
    font = chinese_font(size)
    lines, current = [], ""
    for char in text:
        candidate = current + char
        if current and font.size(candidate)[0] > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines if len(lines) <= max_lines else None

def card_text_lines(text, color, rect, start_size, min_size=13, max_lines=2):
    """Return one or two legible card-text surfaces before shrinking too far."""
    rect = pygame.Rect(rect)
    max_width = max(78, int(rect.width * 0.60))
    for size in range(start_size, min_size - 1, -1):
        lines = wrap_card_lines(text, max_width, size, max_lines)
        if lines:
            font = chinese_font(size)
            return [font.render(line, True, color) for line in lines]
    # Very rare overlong strings still remain bounded; use compact two lines.
    lines = wrap_card_lines(text, max_width, min_size, max_lines) or [text[:8], text[8:16]]
    font = chinese_font(min_size)
    return [font.render(line, True, color) for line in lines]

def draw_centered_card_lines(lines, center_x, center_y, line_gap=5):
    total_height = sum(line.get_height() for line in lines) + max(0, len(lines) - 1) * line_gap
    y = center_y - total_height // 2
    for line in lines:
        screen.blit(line, line.get_rect(center=(center_x, y + line.get_height() // 2)))
        y += line.get_height() + line_gap

# Populated from CC0 web-sourced audio assets after ASSET_DIR is available.
SHOT_SOUNDS = {}
SOUND_LAST_PLAYED = {}

# Pygbag's browser mixer can occasionally leave a Sound channel running after
# Safari unlocks the AudioContext.  Route every short effect through a fixed
# channel and give it a hard end time.  Background music uses the dedicated
# music stream below and is the only audio that may loop.
SFX_CHANNELS = {
    "gun": 0, "sniper": 1, "shotgun": 2, "grenade": 3,
    "laser": 4, "flame": 5, "boss_alarm": 6, "ui": 7,
    "result_music": 8,
}

def play_sound_once(sound, channel_name, max_ms=None):
    """Play a short effect exactly once, with a Safari-safe stop deadline."""
    if not SOUND_READY or sound is None:
        return
    try:
        channel = pygame.mixer.Channel(SFX_CHANNELS[channel_name])
        channel.stop()
        if max_ms is None:
            duration = int(sound.get_length() * 1000) + 120
            max_ms = max(250, min(duration, 5000))
        channel.play(sound, loops=0, maxtime=max_ms, fade_ms=0)
    except Exception:
        # Desktop fallback; loops=0 is still an explicit one-shot request.
        sound.stop()
        sound.play(loops=0, maxtime=max_ms or 3000, fade_ms=0)

WEAPON_SOUND_KIND = {
    "sniper": "sniper",
    "shotgun": "shotgun",
    "laser": "laser",
    "flamethrower": "flame",
    "grenade": "grenade",
}
# Keep rapid weapons underneath BGM; slower, high-impact weapons can retain
# more presence without turning the mix into noise.
WEAPON_SOUND_VOLUME = {
    "pistol": 0.27, "rifle": 0.23, "smg": 0.14,
    "sniper": 0.38, "shotgun": 0.34, "crossbow": 0.22,
    "laser": 0.28, "flamethrower": 0.15, "grenade": 0.28,
}

# Several downloaded samples contain a long tail (the generic gun sample is
# two seconds long).  Rapid weapons only use the clean attack portion, so a
# held trigger cannot stack or repeatedly restart a long noisy tail.
WEAPON_SOUND_MAX_MS = {
    "gun": 150, "sniper": 850, "shotgun": 520,
    "grenade": 650, "laser": 120, "flame": 150,
}

def play_weapon_sound(weapon):
    if not SOUND_READY:
        return
    kind = WEAPON_SOUND_KIND.get(weapon, "gun")
    now = pygame.time.get_ticks()
    interval = {"gun": 45, "sniper": 500, "shotgun": 150, "laser": 80, "flame": 120, "grenade": 220}[kind]
    if now - SOUND_LAST_PLAYED.get(kind, -interval) < interval:
        return
    sound = SHOT_SOUNDS.get(kind)
    if sound:
        sound.set_volume(WEAPON_SOUND_VOLUME.get(weapon, 0.16))
        play_sound_once(sound, kind, WEAPON_SOUND_MAX_MS[kind])
        SOUND_LAST_PLAYED[kind] = now

# Weapon Data
WEAPON_CONFIG = {
    "rifle": {"name": "突击步枪", "mag_cap": 30, "reload_sec": 2, "damage": 7, "pellet_count": 1, "shot_cd": 6, "cost": 30},
    # Sniper rounds pierce three targets but fire only once per second.
    "sniper": {"name": "狙击枪", "mag_cap": 10, "reload_sec": 5, "damage": 150, "pellet_count": 1, "shot_cd": 60, "cost": 90, "pierce": 3},
    # Four pellets with 14 damage each; shortened reload keeps it viable up close.
    "shotgun": {"name": "霰弹枪", "mag_cap": 15, "reload_sec": 4, "damage": 14, "pellet_count": 4, "shot_cd": 18, "cost": 160},
    "pistol": {"name": "手枪", "mag_cap": 10, "reload_sec": 3, "damage": 18, "pellet_count": 1, "shot_cd": 8, "cost": 0},
    "smg": {"name": "冲锋枪", "mag_cap": 45, "reload_sec": 2.5, "damage": 5, "pellet_count": 1, "shot_cd": 2, "cost": 130},
    "flamethrower": {"name": "喷火枪", "mag_cap": 70, "reload_sec": 4, "damage": 2, "pellet_count": 4, "shot_cd": 3, "cost": 190, "range": 24, "color": (255, 110, 0)},
    "grenade": {"name": "榴弹发射器", "mag_cap": 8, "reload_sec": 4.5, "damage": 48, "pellet_count": 1, "shot_cd": 28, "cost": 230, "grenade": True},
    # Laser damage is deliberately fixed: upgrades cannot raise it.
    "laser": {"name": "激光枪", "mag_cap": 30, "reload_sec": 3.5, "damage": 5, "pellet_count": 1, "shot_cd": 2, "cost": 220, "pierce": 99, "color": (80, 230, 255), "beam": True},
    "crossbow": {"name": "弩", "mag_cap": 20, "reload_sec": 3.5, "damage": 23, "pellet_count": 1, "shot_cd": 24, "cost": 100, "pierce": 3},
}

# Persistent progression materials.  They are kept for the whole game
# session and are spent after clearing a stage.
MATERIAL_INFO = {
    "alloy": ("废土合金", (188, 204, 214)),
    "energy": ("能量核心", (70, 225, 255)),
    "bio": ("生体样本", (115, 230, 120)),
}
STAGE_MATERIAL = ["alloy", "alloy", "energy", "alloy", "energy", "energy", "bio", "alloy", "bio", "energy"]
WEAPON_MATERIAL = {
    "pistol": "alloy", "rifle": "alloy", "smg": "alloy", "crossbow": "bio",
    "sniper": "energy", "shotgun": "alloy", "grenade": "alloy",
    "flamethrower": "bio", "laser": "energy",
}
ACTIVE_PROFILE = None
ALL_WEAPON_LIST = ["pistol", "rifle", "sniper", "shotgun", "smg", "flamethrower", "grenade", "laser", "crossbow"]

# Upgrade Perks List
UPGRADE_LIST = [
    {"id": 0, "name": "移速 +1", "desc": "玩家移动速度 +1", "tier": "普通", "func": "buff_speed"},
    {"id": 2, "name": "生命上限 +25", "desc": "最大生命值增加 25", "tier": "普通", "func": "buff_hp_25"},
    {"id": 3, "name": "弹匣 +5", "desc": "弹匣容量增加 5 发", "tier": "普通", "func": "buff_mag_5"},
    {"id": 4, "name": "装填 -0.3 秒", "desc": "装填时间减少 0.3 秒", "tier": "普通", "func": "buff_reload_fast"},
    {"id": 5, "name": "射速提升", "desc": "射击间隔缩短", "tier": "普通", "func": "buff_fire_rate"},
    {"id": 6, "name": "恢复 30 生命", "desc": "立刻恢复 30 点生命", "tier": "普通", "func": "heal_30"},
    {"id": 7, "name": "金币 +20", "desc": "获得额外 20 金币", "tier": "普通", "func": "gold_20"},
    {"id": 8, "name": "精准射击", "desc": "减少子弹散布", "tier": "普通", "func": "buff_accuracy"},
    {"id": 9, "name": "粒子强化", "desc": "命中时有更多爆炸特效", "tier": "普通", "func": "buff_particle"},
    {"id": 11, "name": "生命上限 +50", "desc": "最大生命值增加 50", "tier": "稀有", "func": "buff_hp_50"},
    {"id": 12, "name": "弹匣 ×1.5", "desc": "弹匣容量变为 1.5 倍", "tier": "稀有", "func": "buff_mag_half"},
    {"id": 13, "name": "恢复 60 生命", "desc": "立刻恢复 60 点生命", "tier": "稀有", "func": "heal_60"},
    {"id": 14, "name": "移速 +2", "desc": "大幅提升移动速度", "tier": "稀有", "func": "buff_speed_big"},
    {"id": 16, "name": "生命上限 +100", "desc": "最大生命值大幅增加 100", "tier": "史诗", "func": "buff_hp_100"},
    # Advanced upgrades are intentionally modest: they add choices, not raw DPS.
    {"id": 20, "name": "穿透弹药组件", "desc": "弹药可额外穿透 2 个目标", "tier": "稀有", "func": "perk_pierce"},
    {"id": 21, "name": "链式电弧模块", "desc": "每次跳转均有 30% 概率继续传导", "tier": "稀有", "func": "perk_chain"},
    {"id": 22, "name": "低温弹药", "desc": "命中时有 35% 概率显著减速目标", "tier": "普通", "func": "perk_chill"},
    {"id": 23, "name": "动能击退装置", "desc": "命中时有 25% 概率击退目标", "tier": "普通", "func": "perk_push"},
    {"id": 24, "name": "战地复苏模块", "desc": "每击败 5 名敌人时，有 50% 概率恢复 10 点生命", "tier": "稀有", "func": "perk_leech"},
    {"id": 25, "name": "肾上腺素", "desc": "生命低于 45 时，移动速度显著提升", "tier": "史诗", "func": "perk_adrenaline"},
    {"id": 26, "name": "首领定位罗盘", "desc": "在界面边缘持续指示首领方位", "tier": "普通", "func": "perk_compass"},
    {"id": 27, "name": "自动补弹系统", "desc": "每击败 8 名敌人后，自动补充 2 发弹药", "tier": "稀有", "func": "perk_autoload"},
    {"id": 28, "name": "备用弹匣", "desc": "弹匣耗尽时，可立即完成 1 次装填", "tier": "稀有", "func": "perk_reserve"},
    {"id": 29, "name": "临界防护协议", "desc": "生命低于 35 时，获得一次 2 秒护盾", "tier": "史诗", "func": "perk_shield"},
    {"id": 30, "name": "战术短冲", "desc": "按空格键进行长距离冲刺，冷却时间 5 秒", "tier": "稀有", "func": "perk_dash"},
    {"id": 31, "name": "轻型护甲", "desc": "接触伤害减少 2", "tier": "普通", "func": "perk_armor"},
    {"id": 32, "name": "战利品检索器", "desc": "每击败 5 名敌人后，额外获得 2 枚金币", "tier": "普通", "func": "perk_coin"},
    {"id": 33, "name": "战地医疗模块", "desc": "击败肉盾单位后，恢复 5 点生命", "tier": "稀有", "func": "perk_medic"},
    {"id": 34, "name": "诱导脉冲发生器", "desc": "每 8 秒显著减速附近敌人", "tier": "稀有", "func": "perk_decoy"},
    {"id": 35, "name": "防御无人机", "desc": "每 2 秒对最近敌人造成 8 点支援伤害", "tier": "史诗", "func": "perk_drone"},
    {"id": 36, "name": "感应地雷", "desc": "每 5 秒部署一枚造成 24 点伤害的地雷", "tier": "稀有", "func": "perk_mine"},
    {"id": 37, "name": "时间减速场", "desc": "每击败 10 名敌人后，显著减速全场敌人", "tier": "史诗", "func": "perk_time"},
    {"id": 38, "name": "战术补给", "desc": "连续 8 秒未受伤后，恢复 10 点生命", "tier": "普通", "func": "perk_ration"},
    {"id": 39, "name": "战场回收协议", "desc": "击败敌人时有 15% 概率回收 2 发弹药", "tier": "普通", "func": "perk_scavenge"},
]

ACHIEVEMENT_DETAILS = {
    "first_elite": ("精英清除者", "首次击败带有词缀的精英敌人。"),
    "combo_10": ("十连清除", "在连杀倒计时结束前连续击败 10 个目标。"),
    "stage_sweeper": ("战区清扫者", "清除任意战区规定数量的普通敌人。"),
    "boss_hunter": ("首领猎手", "击败任意一名首领。"),
}

# Weapon images
# Gameplay icons have a maximum visual dimension of 38 px, as requested.
ASSET_DIR = Path(__file__).resolve().parent / "assets"

def load_cc0_sound(filename, volume):
    """Load a downloaded CC0 sound, silently falling back if unavailable."""
    if not SOUND_READY:
        return None

def load_result_sound(track):
    """Load a result jingle as a Sound; this is more reliable than web streaming."""
    if not SOUND_READY:
        return None
    try:
        path, volume, _loops = BGM_TRACKS[track]
        sound = pygame.mixer.Sound(path)
        sound.set_volume(volume)
        return sound
    except Exception:
        return None
    try:
        sound = pygame.mixer.Sound(ASSET_DIR / "sfx" / filename)
        sound.set_volume(volume)
        return sound
    except Exception:
        return None

# Sources: OpenGameArt CC0 sound effects (see assets/sfx/SOURCES.md).
SHOT_SOUNDS.update({
    "gun": load_cc0_sound("gunfire_cc0.wav", 0.20),
    "sniper": load_cc0_sound("cc0_bangs/shot_01.ogg", 0.30),
    "shotgun": load_cc0_sound("cc0_bangs/cannon_05.ogg", 0.25),
    "grenade": load_cc0_sound("gunfire_cc0.wav", 0.20),
    "laser": load_cc0_sound("laser_cc0.mp3", 0.12),
    "flame": load_cc0_sound("flame_cc0.mp3", 0.10),
})

# Music uses its own mixer stream, so it can loop beneath the short weapon
# effects. Missing files or unavailable audio devices simply leave music off.
BGM_TRACKS = {
    # This version has its head and tail crossfaded, so pygame's repeat point
    # is inaudible instead of producing the old abrupt cut every loop.
    "combat": (ASSET_DIR / "music" / "combat_loop_seamless.wav", 0.12, -1),
    "boss": (ASSET_DIR / "music" / "boss_loop.mp3", 0.15, -1),
    "win": (ASSET_DIR / "music" / "win_jingle.ogg", 0.36, 0),
    "gameover": (ASSET_DIR / "music" / "game_over.mp3", 0.28, 0),
}
BOSS_ALARM_SOUND = load_cc0_sound("boss_alarm.wav", 0.48)
UI_BUTTON_SOUND = load_cc0_sound("ui_button_thump.wav", 0.34)
RESULT_SOUNDS = {
    "win": load_result_sound("win"),
    "gameover": load_result_sound("gameover"),
}
CURRENT_BGM = None
BOSS_BGM_START_AT = 0

def ensure_audio_ready():
    """Unlock Safari audio from the first real click, then load every sound."""
    global SOUND_READY, BOSS_ALARM_SOUND, UI_BUTTON_SOUND, CURRENT_BGM
    if SOUND_READY:
        return True
    try:
        # Browsers only allow an AudioContext to start while handling a user
        # gesture.  Calling this from MOUSEBUTTONDOWN avoids the old grey-screen
        # startup failure while restoring music and effects after the first click.
        # Recreate the browser mixer once, inside the user's click.  This clears
        # any stale web channels and matches the 44.1 kHz source material.
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            pygame.mixer.stop()
            pygame.mixer.quit()
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        pygame.mixer.set_num_channels(16)
        SOUND_READY = True
        SHOT_SOUNDS.update({
            "gun": load_cc0_sound("gunfire_cc0.wav", 0.20),
            "sniper": load_cc0_sound("cc0_bangs/shot_01.ogg", 0.30),
            "shotgun": load_cc0_sound("cc0_bangs/cannon_05.ogg", 0.25),
            "grenade": load_cc0_sound("gunfire_cc0.wav", 0.20),
            "laser": load_cc0_sound("laser_cc0.mp3", 0.12),
            "flame": load_cc0_sound("flame_cc0.mp3", 0.10),
        })
        BOSS_ALARM_SOUND = load_cc0_sound("boss_alarm.wav", 0.48)
        UI_BUTTON_SOUND = load_cc0_sound("ui_button_thump.wav", 0.34)
        RESULT_SOUNDS["win"] = load_result_sound("win")
        RESULT_SOUNDS["gameover"] = load_result_sound("gameover")
        pending_bgm = CURRENT_BGM
        CURRENT_BGM = None
        if pending_bgm:
            set_bgm(pending_bgm)
        return True
    except Exception:
        SOUND_READY = False
        return False

def play_ui_button_sound():
    """Short mechanical thump used by every non-combat interface control."""
    play_sound_once(UI_BUTTON_SOUND, "ui", 1200)

def set_bgm(track):
    """Switch the looping background music only when the battle state changes."""
    global CURRENT_BGM
    now = pygame.time.get_ticks()
    if track == "boss" and now < BOSS_BGM_START_AT:
        if CURRENT_BGM != "boss_wait":
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            CURRENT_BGM = "boss_wait"
        return
    if track == CURRENT_BGM:
        return
    CURRENT_BGM = track
    if not SOUND_READY:
        return
    try:
        pygame.mixer.music.stop()
        pygame.mixer.Channel(SFX_CHANNELS["result_music"]).stop()
        if track is None:
            return
        if track in RESULT_SOUNDS and RESULT_SOUNDS[track]:
            # Result jingles are buffered one-shots on web.  This restores the
            # missing victory/defeat music without ever allowing it to loop.
            play_sound_once(RESULT_SOUNDS[track], "result_music", 15000)
            return
        path, volume, _configured_loops = BGM_TRACKS[track]
        if not path.exists():
            return
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(volume)
        # Only ambient battle tracks repeat. Victory and defeat jingles must
        # always end after one play even if a browser backend mishandles data.
        loops = -1 if track in ("combat", "boss") else 0
        pygame.mixer.music.play(loops)
    except Exception:
        CURRENT_BGM = None

def play_boss_alarm():
    global BOSS_BGM_START_AT, CURRENT_BGM
    # Stop combat music, play a short warning by itself, then start boss music.
    # The old version started both together and sounded like two tracks colliding.
    try:
        pygame.mixer.music.stop()
    except Exception:
        pass
    CURRENT_BGM = "boss_wait"
    BOSS_BGM_START_AT = pygame.time.get_ticks() + 1800
    play_sound_once(BOSS_ALARM_SOUND, "boss_alarm", 1800)

_button_skin_path = ASSET_DIR / "ui-button-metal-v1.png"
if _button_skin_path.exists():
    UI_BUTTON_SKIN = pygame.image.load(_button_skin_path).convert_alpha()
    _button_bounds = UI_BUTTON_SKIN.get_bounding_rect()
    if _button_bounds.width and _button_bounds.height:
        UI_BUTTON_SKIN = UI_BUTTON_SKIN.subsurface(_button_bounds).copy()

_card_skin_path = ASSET_DIR / "ui-card-metal-v1.png"
if _card_skin_path.exists():
    UI_CARD_SKIN = pygame.image.load(_card_skin_path).convert_alpha()
    _card_bounds = UI_CARD_SKIN.get_bounding_rect()
    if _card_bounds.width and _card_bounds.height:
        UI_CARD_SKIN = UI_CARD_SKIN.subsurface(_card_bounds).copy()

def load_ui_background(filename):
    """Load a full-screen UI illustration without affecting gameplay assets."""
    path = ASSET_DIR / filename
    if not path.exists():
        return None
    image = pygame.image.load(path).convert()
    return pygame.transform.smoothscale(image, (W, H))

# A bespoke hand-painted command-bunker scene anchors the rewritten menu UI.
MENU_COMMAND_BG = load_ui_background("wasteland-command-background-v1.png")
# A separate top-down ruined-city arena is used only during combat.  It keeps
# the menu identity intact while making the battlefield visibly more premium.
BATTLEFIELD_CITY_BG = load_ui_background("battlefield-ruined-city-v1.png")

# High-detail inventory materials replace the old abstract geometry.  The
# source art is loaded once and scaled on demand for each UI location.
MATERIAL_ICON_FILES = {
    "alloy": "materials/scrap-alloy-icon.png",
    "energy": "materials/energy-core-icon.png",
    "bio": "materials/bio-sample-icon.png",
}
MATERIAL_ICON_SPRITES = {}
MATERIAL_ICON_CACHE = {}
for _key, _filename in MATERIAL_ICON_FILES.items():
    _path = ASSET_DIR / _filename
    if _path.exists():
        MATERIAL_ICON_SPRITES[_key] = pygame.image.load(_path).convert_alpha()

WEAPON_IMAGE_FILES = {
    "rifle": "rifle.png",
    "sniper": "shotgun.png",
    "shotgun": "sniper.png",
    "pistol": "pistol.png",
    "smg": "smg.png",
    "flamethrower": "flamethrower-clean.png",
    "grenade": "grenade.png",
    "laser": "laser.png",
}
# The source PNGs do not all face right.  Normalize them once here so the
# regular gameplay rotation can always use the mouse direction.
WEAPON_IMAGE_ORIENTATION = {
    "rifle": {"rotate": -122, "flip_x": True, "flip_y": True},
    "sniper": {},
    "shotgun": {"flip_x": True},
    "pistol": {"flip_x": True},
    "smg": {"flip_x": True},
    "flamethrower": {"flip_x": True},
    "grenade": {"flip_x": True},
    "laser": {"flip_x": True},
}

def draw_extra_weapon_image(weapon_key, max_size):
    """Simple built-in icons for the five new weapons, all facing right."""
    surf = pygame.Surface((52, 28), pygame.SRCALPHA)
    if weapon_key == "smg":
        pygame.draw.rect(surf, (80, 90, 100), (5, 8, 38, 8), border_radius=2)
        pygame.draw.rect(surf, (40, 45, 52), (38, 10, 11, 4))
        pygame.draw.polygon(surf, (55, 60, 65), [(18, 15), (28, 15), (25, 26), (18, 26)])
    elif weapon_key == "flamethrower":
        pygame.draw.rect(surf, (145, 70, 30), (4, 9, 31, 10), border_radius=3)
        pygame.draw.rect(surf, (65, 65, 65), (31, 11, 16, 6))
        pygame.draw.circle(surf, (255, 150, 0), (48, 14), 4)
        pygame.draw.polygon(surf, (55, 55, 55), [(14, 18), (24, 18), (20, 27), (14, 27)])
    elif weapon_key == "grenade":
        pygame.draw.rect(surf, (70, 110, 70), (5, 9, 35, 9), border_radius=4)
        pygame.draw.circle(surf, (90, 150, 80), (43, 14), 6)
        pygame.draw.rect(surf, (45, 50, 45), (18, 18, 8, 8))
    elif weapon_key == "laser":
        pygame.draw.rect(surf, (45, 70, 100), (4, 10, 38, 7), border_radius=2)
        pygame.draw.rect(surf, (80, 230, 255), (37, 12, 14, 3))
        pygame.draw.circle(surf, (170, 255, 255), (14, 13), 3)
    elif weapon_key == "crossbow":
        pygame.draw.line(surf, (120, 80, 35), (6, 14), (46, 14), 4)
        pygame.draw.line(surf, (160, 120, 65), (35, 4), (35, 24), 3)
        pygame.draw.line(surf, (210, 210, 210), (4, 14), (50, 14), 1)
    scale = max_size / max(surf.get_width(), surf.get_height())
    return pygame.transform.smoothscale(surf, (round(surf.get_width() * scale), round(surf.get_height() * scale)))

def load_weapon_image(weapon_key, max_size):
    """Load an alpha PNG, remove its transparent border, and preserve its aspect ratio."""
    if weapon_key not in WEAPON_IMAGE_FILES:
        return draw_extra_weapon_image(weapon_key, max_size)
    image = pygame.image.load(ASSET_DIR / WEAPON_IMAGE_FILES[weapon_key]).convert_alpha()
    opaque_rect = image.get_bounding_rect()
    if opaque_rect.width and opaque_rect.height:
        image = image.subsurface(opaque_rect).copy()
    orientation = WEAPON_IMAGE_ORIENTATION[weapon_key]
    if orientation.get("rotate"):
        image = pygame.transform.rotate(image, orientation["rotate"])
        opaque_rect = image.get_bounding_rect()
        if opaque_rect.width and opaque_rect.height:
            image = image.subsurface(opaque_rect).copy()
    if orientation.get("flip_x") or orientation.get("flip_y"):
        image = pygame.transform.flip(image, orientation.get("flip_x", False), orientation.get("flip_y", False))
    scale = max_size / max(image.get_width(), image.get_height())
    size = (max(1, round(image.get_width() * scale)), max(1, round(image.get_height() * scale)))
    return pygame.transform.smoothscale(image, size)

WEAPON_SPRITES = {key: load_weapon_image(key, 38) for key in WEAPON_CONFIG}
WEAPON_CARD_SPRITES = {key: load_weapon_image(key, 110) for key in WEAPON_CONFIG}
WEAPON_SELECT_SPRITES = {key: load_weapon_image(key, 70) for key in WEAPON_CONFIG}

def load_entity_image(filename, max_size):
    """Load a generated character model and scale it for the game world."""
    path = ASSET_DIR / filename
    if not path.exists():
        return None
    image = pygame.image.load(path).convert_alpha()
    opaque_rect = image.get_bounding_rect()
    if opaque_rect.width and opaque_rect.height:
        image = image.subsurface(opaque_rect).copy()
    scale = max_size / max(image.get_width(), image.get_height())
    return pygame.transform.smoothscale(image, (max(1, round(image.get_width() * scale)), max(1, round(image.get_height() * scale))))

# High-detail character models.  If an asset is unavailable, the original
# vector drawing remains active as a safe fallback.
ENTITY_SPRITES = {
    "player": load_entity_image("player-overhead-v4.png", 44),
    "basic": load_entity_image("cat-basic-v2.png", 36),
    "fast": load_entity_image("cat-fast-v3.png", 32),
    "tank": load_entity_image("cat-tank-v3.png", 62),
    "scout": load_entity_image("cat-scout-v1.png", 38),
    "brute": load_entity_image("cat-brute-v1.png", 56),
    "mini": load_entity_image("cat-basic-v2.png", 27),
    "boss": load_entity_image("cat-tank-v2.png", 128),
    "drone": load_entity_image("defense-drone-v3.png", 42),
    "mine": load_entity_image("proximity-mine-v3.png", 38),
}

# Eight-direction sprite sheets are built once from the high-detail top-down
# models.  This avoids visual sliding: every moving entity now switches to the
# nearest facing direction (right, down-right, down, and so on).
DIRECTION_ANGLES = tuple(index * math.tau / 8 for index in range(8))
ENTITY_BASE_HEADING = {
    "player": -math.pi / 2,
    "basic": math.pi / 2,
    "fast": math.pi / 2,
    "tank": math.pi / 2,
    "scout": math.pi / 2,
    "brute": math.pi / 2,
    "mini": math.pi / 2,
    "boss": math.pi / 2,
}

def build_directional_sprites(key):
    sprite = ENTITY_SPRITES.get(key)
    if sprite is None:
        return [None] * 8
    base_heading = ENTITY_BASE_HEADING[key]
    return [pygame.transform.rotate(sprite, math.degrees(base_heading - direction)) for direction in DIRECTION_ANGLES]

ENTITY_DIRECTION_SPRITES = {key: build_directional_sprites(key) for key in ENTITY_BASE_HEADING}

def directional_sprite(key, facing):
    variants = ENTITY_DIRECTION_SPRITES.get(key)
    if not variants or variants[0] is None:
        return ENTITY_SPRITES.get(key)
    index = int(round((facing % math.tau) / (math.tau / 8))) % 8
    return variants[index]
# Vertical location of the visible barrel tip within each cropped sprite.
WEAPON_MUZZLE_Y = {
    "pistol": 0.34, "rifle": 0.50, "sniper": 0.50, "shotgun": 0.47,
    "smg": 0.45, "flamethrower": 0.43, "grenade": 0.50,
    "laser": 0.45, "crossbow": 0.50,
}

# Bullet Class
class Bullet:
    def __init__(self, spawn_x, spawn_y, target_x, target_y, spread=0, dmg_mod=1, weapon_key="pistol", cfg=None):
        self.x = spawn_x
        self.y = spawn_y
        dx = target_x - spawn_x
        dy = target_y - spawn_y
        angle = math.atan2(dy, dx) + spread
        cfg = cfg or {}
        speed = 6 if weapon_key == "flamethrower" else 10
        if weapon_key == "laser":
            speed = 18
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.dmg_mod = dmg_mod
        self.weapon_key = weapon_key
        self.is_beam = cfg.get("beam", False)
        self.life = cfg.get("beam_life", 2) if self.is_beam else cfg.get("range", 90)
        self.radius = 6 if weapon_key in ("grenade", "laser") else 4
        self.explosion_radius = cfg.get("explosion_radius", 90)
        self.color = cfg.get("color", WHITE)
        self.pierce_left = cfg.get("pierce", 1)
        self.hit_targets = set()
        self.start_x, self.start_y = spawn_x, spawn_y
        self.end_x = spawn_x + math.cos(angle) * 1400
        self.end_y = spawn_y + math.sin(angle) * 1400

    def update(self):
        if not self.is_beam:
            self.x += self.vx
            self.y += self.vy
        self.life -= 1

    def out(self):
        return self.life <= 0 or self.x < 0 or self.x > WORLD_W or self.y < 0 or self.y > WORLD_H

    def draw(self):
        if self.is_beam:
            start = world_to_screen(self.start_x, self.start_y)
            end = world_to_screen(self.end_x, self.end_y)
            pygame.draw.line(screen, (190, 255, 255), start, end, 5 + self.radius // 2)
            pygame.draw.line(screen, self.color, start, end, 2 + self.radius // 4)
            return
        sx, sy = world_to_screen(self.x, self.y)
        if self.weapon_key == "crossbow":
            length = math.hypot(self.vx, self.vy)
            dx, dy = self.vx / length, self.vy / length
            pygame.draw.line(screen, (210, 175, 105), (int(sx - dx * 13), int(sy - dy * 13)), (int(sx + dx * 13), int(sy + dy * 13)), 3)
            pygame.draw.circle(screen, (230, 230, 230), (int(sx + dx * 13), int(sy + dy * 13)), 2)
            return
        pygame.draw.circle(screen, self.color, (int(sx), int(sy)), self.radius)
        if self.weapon_key == "grenade":
            pygame.draw.circle(screen, (50, 120, 50), (int(sx), int(sy)), self.radius - 2)


def point_to_segment_distance(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

# Particle Effect Class
class Particle:
    def __init__(self, x, y, color, boost=0, size=4, life=30):
        self.x = x
        self.y = y
        self.vx = random.uniform(-3 - boost, 3 + boost)
        self.vy = random.uniform(-3 - boost, 3 + boost)
        self.life = life
        self.max_life = life
        self.size = size
        self.color = color

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vx *= 0.95
        self.vy *= 0.95
        self.life -= 1

    def draw(self):
        if self.life > 0:
            alpha = int(255 * (self.life / self.max_life))
            s = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
            pygame.draw.circle(s, (*self.color, alpha), (self.size // 2, self.size // 2), max(1, self.size // 2))
            sx, sy = world_to_screen(self.x, self.y)
            screen.blit(s, (int(sx - self.size / 2), int(sy - self.size / 2)))


class DamagePopup:
    """A short, readable floating damage number anchored to a hit target."""
    def __init__(self, x, y, damage, emphasized=False, color=(255, 224, 82)):
        self.x = x + random.randint(-8, 8)
        self.y = y - random.randint(10, 24)
        self.damage = max(1, int(damage))
        self.life = 34 if emphasized else 26
        self.max_life = self.life
        self.vx = random.uniform(-0.35, 0.35)
        self.vy = -1.25 if emphasized else -0.85
        self.emphasized = emphasized
        self.color = color

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy *= 0.96
        self.life -= 1

    def draw(self):
        if self.life <= 0:
            return
        alpha = int(255 * self.life / self.max_life)
        age = self.max_life - self.life
        pop = max(0.0, 1.0 - age / 7.0)
        size = (34 if self.emphasized else 23) + int(pop * (11 if self.emphasized else 5))
        text = pygame.font.Font(None, size).render(str(self.damage), True, self.color)
        text.set_alpha(alpha)
        sx, sy = world_to_screen(self.x, self.y)
        shadow = pygame.font.Font(None, size).render(str(self.damage), True, BLACK)
        shadow.set_alpha(alpha)
        rect = text.get_rect(center=(int(sx), int(sy)))
        screen.blit(shadow, rect.move(2, 2))
        screen.blit(text, rect)

def draw_damage_vignette(player):
    """A restrained red edge cue for low health and immediate hits."""
    hp_ratio = max(0, player.hp) / max(1, player.calc_max_hp())
    hit_strength = 95 if player.hit_flash > 0 else 0
    low_hp_strength = int(max(0, 0.45 - hp_ratio) / 0.45 * 105)
    strength = max(hit_strength, low_hp_strength)
    if strength <= 0:
        return
    overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    for inset, alpha in ((0, strength), (18, int(strength * .72)), (42, int(strength * .38))):
        pygame.draw.rect(overlay, (185, 18, 28, alpha), (inset, inset, W-inset*2, H-inset*2), 18)
    screen.blit(overlay, (0, 0))

# Normal Enemy Class
class NormalEnemy:
    def __init__(self, typ="basic", slow_mod=1, stage=1, player_x=None, player_y=None, elite_affix=None):
        # Spawn inside the current camera view, but never directly on the player.
        player_x = WORLD_W / 2 if player_x is None else player_x
        player_y = WORLD_H / 2 if player_y is None else player_y
        left = max(25, int(CAMERA_X) + 25)
        right = min(WORLD_W - 25, int(CAMERA_X + W) - 25)
        top = max(25, int(CAMERA_Y) + 25)
        bottom = min(WORLD_H - 25, int(CAMERA_Y + H) - 25)
        for _ in range(20):
            self.x = random.randint(left, right)
            self.y = random.randint(top, bottom)
            if math.hypot(self.x - player_x, self.y - player_y) >= 100:
                break
        self.type = typ
        self.slow_mod = slow_mod
        base_hp = 80
        if typ == "basic":
            self.max_hp = base_hp
            self.r = 12
            self.speed = 3.0 * self.slow_mod
            self.dmg = 10
        elif typ == "tank":
            self.max_hp = base_hp * 3
            self.r = 22
            self.speed = 2.5 * self.slow_mod
            self.dmg = 5
        elif typ == "fast":
            self.max_hp = base_hp // 2
            self.r = 7
            self.speed = 3.8 * self.slow_mod
            self.dmg = 5
        elif typ == "scout":
            # A nimble mid-weight cat: more durable than a fast enemy but
            # still readable and nowhere near a boss-level threat.
            self.max_hp = 65
            self.r = 10
            self.speed = 3.35 * self.slow_mod
            self.dmg = 7
        else:  # brute
            # A compact bruiser fills the gap between normal cats and tanks.
            self.max_hp = 150
            self.r = 16
            self.speed = 2.7 * self.slow_mod
            self.dmg = 8
        # From stage 2 onward, cats have 1.25× health. Stage 1 stays beginner-friendly.
        if stage > 1:
            self.max_hp = int(self.max_hp * 1.25)
        self.elite_affix = elite_affix
        if elite_affix == "armored":
            self.max_hp = int(self.max_hp * 1.55)
        elif elite_affix == "swift":
            self.speed *= 1.35
        elif elite_affix == "berserk":
            self.dmg = int(self.dmg * 1.7)
        self.hp = self.max_hp
        self.atk_cd = 0
        self.hit_flash = 0
        self.slow_timer = 0
        self.anim_phase = random.uniform(0, math.tau)
        self.facing = math.pi / 2

    def update(self, px, py):
        if self.slow_timer > 0:
            self.slow_timer -= 1
        dx = px - self.x
        dy = py - self.y
        dist = math.hypot(dx, dy)
        if dist > 0:
            self.facing = math.atan2(dy, dx)
            move_speed = self.speed * (0.72 if self.slow_timer > 0 else 1)
            self.x += dx / dist * move_speed
            self.y += dy / dist * move_speed
        if self.atk_cd > 0:
            self.atk_cd -= 1
        if self.hit_flash > 0:
            self.hit_flash -= 1

    def draw(self):
        if self.type == "basic":
            c = RED
        elif self.type == "tank":
            c = (120, 20, 20)
        elif self.type == "fast":
            c = (255, 120, 0)
        elif self.type == "scout":
            c = (74, 196, 210)
        else:
            c = (174, 82, 44)
        if self.hit_flash > 0:
            c = WHITE
        sx, sy = world_to_screen(self.x, self.y)
        bob = round(math.sin(pygame.time.get_ticks() * 0.012 + self.anim_phase) * 1.5)
        sprite = directional_sprite(self.type, self.facing)
        if sprite:
            if self.hit_flash > 0:
                sprite = sprite.copy()
                sprite.fill((110, 110, 110), special_flags=pygame.BLEND_RGB_ADD)
            screen.blit(sprite, sprite.get_rect(center=(int(sx), int(sy + bob))))
        else:
            pygame.draw.circle(screen, c, (int(sx), int(sy)), self.r)
            pygame.draw.circle(screen, BLACK, (int(sx), int(sy)), self.r, 2)
            if self.type == "scout":
                pygame.draw.polygon(screen, (215, 255, 255), [(int(sx), int(sy - self.r - 3)), (int(sx - 4), int(sy - 2)), (int(sx + 4), int(sy - 2))])
            elif self.type == "brute":
                pygame.draw.rect(screen, (95, 35, 24), (int(sx - self.r * .55), int(sy - 3), int(self.r * 1.1), 7), border_radius=3)
            eye_off = self.r * 0.35
            pygame.draw.circle(screen, BLACK, (int(sx - eye_off), int(sy - eye_off)), 2)
            pygame.draw.circle(screen, BLACK, (int(sx + eye_off), int(sy - eye_off)), 2)
        bar_w = self.r * 1.6
        bar_h = 4
        bx = sx - bar_w / 2
        by = sy - self.r - 10
        pygame.draw.rect(screen, DARK_RED, (bx, by, bar_w, bar_h))
        pygame.draw.rect(screen, GREEN, (bx, by, bar_w * (self.hp / self.max_hp), bar_h))
        if self.elite_affix:
            colors = {"armored": (115, 190, 255), "swift": (255, 205, 64), "berserk": (255, 82, 68)}
            names = {"armored": "装甲", "swift": "迅捷", "berserk": "狂暴"}
            pygame.draw.circle(screen, colors[self.elite_affix], (int(sx), int(sy)), self.r + 4, 2)
            tag = font_small.render(names[self.elite_affix], True, colors[self.elite_affix])
            screen.blit(tag, tag.get_rect(center=(int(sx), int(by - 10))))

# Boss Class (Nerfed HP & Dash Damage)
class BossCat:
    def __init__(self, stage, phase=2, player_x=None, player_y=None):
        self.stage = stage
        self.phase = phase
        self.is_final_phase_one = stage == 5 and phase == 1
        combat_stage = 1 if self.is_final_phase_one else stage
        self.combat_stage = combat_stage
        self.max_hp = 360 + combat_stage * 220
        if self.is_final_phase_one:
            self.max_hp *= 2
        elif combat_stage > 1:
            self.max_hp = int(self.max_hp * 1.40)
        if stage == 5:
            self.max_hp = int(self.max_hp * 1.60)
        self.hp = self.max_hp
        self.r = 45
        if player_x is None or player_y is None:
            self.x, self.y = WORLD_W // 2, WORLD_H // 4
        else:
            left = max(self.r, int(CAMERA_X) + self.r)
            right = min(WORLD_W - self.r, int(CAMERA_X + W) - self.r)
            top = max(self.r, int(CAMERA_Y) + self.r)
            bottom = min(WORLD_H - self.r, int(CAMERA_Y + H) - self.r)
            for _ in range(20):
                self.x = random.randint(left, right)
                self.y = random.randint(top, bottom)
                if math.hypot(self.x - player_x, self.y - player_y) >= 130:
                    break
        self.tp_timer = 0
        self.tp_cd = max(130, 330 - combat_stage * 35)
        self.summ_timer = 0
        self.summ_cd = max(180, 510 - combat_stage * 45)
        self.atk_cd = 0
        # Every stage boss now deals the same 10 contact damage.
        self.dmg = 10
        self.base_speed = 0.63 + combat_stage * 0.15
        self.summon_count = 2 + combat_stage // 2
        self.hit_flash = 0
        self.slow_timer = 0
        self.anim_phase = random.uniform(0, math.tau)
        self.facing = math.pi / 2
        self.shock_timer = 0
        self.shock_cd = 300
        self.shock_active = 0
        self.shock_hit_cd = 0
        # Frost and burn bosses use tighter aura zones; the final boss keeps both.
        self.freeze_radius = 175 if stage in (2, 5, 6, 8, 9, 10) else 230
        self.burn_radius = 130 if stage in (3, 5, 6, 7, 9, 10) else 170
        # After enough damage, the exposed core becomes a high-risk weak point.
        self.weakpoint_threshold = 0.65
        self.weakpoint_r = 15
        self.weakpoint_suppressed = False

    def weakpoint_active(self):
        return (not self.weakpoint_suppressed
                and self.hp <= self.max_hp * self.weakpoint_threshold)

    def weakpoint_position(self):
        orbit = pygame.time.get_ticks() * 0.003 + self.stage
        return (self.x + math.cos(orbit) * 26, self.y + math.sin(orbit) * 26)

    def has_ability(self, ability):
        if self.is_final_phase_one:
            return False
        abilities = {
            1: set(),
            2: {"freeze"},
            3: {"burn"},
            4: {"shock"},
            5: {"freeze", "burn", "shock"},
            6: {"freeze", "burn"},
            7: {"burn", "shock"},
            8: {"freeze", "shock"},
            9: {"freeze", "burn", "shock"},
            10: {"freeze", "burn", "shock"},
        }
        return ability in abilities.get(self.stage, set())

    def update(self, px, py):
        # At half health the cat enrages: it closes distance and teleports faster.
        enraged = self.hp <= self.max_hp * 0.5
        if self.slow_timer > 0:
            self.slow_timer -= 1
        speed = self.base_speed * (1.85 if enraged else 1) * (0.8 if self.slow_timer > 0 else 1)
        dx = px - self.x
        dy = py - self.y
        dist = math.hypot(dx, dy)
        if dist > 85:
            self.facing = math.atan2(dy, dx)
            self.x += dx / dist * speed
            self.y += dy / dist * speed
        self.tp_timer += 1
        self.summ_timer += 1
        self.shock_timer += 1
        if self.atk_cd > 0:
            self.atk_cd -= 1
        if self.shock_hit_cd > 0:
            self.shock_hit_cd -= 1
        if self.hit_flash > 0:
            self.hit_flash -= 1
        # Rage still speeds up teleporting, but it no longer becomes overwhelming.
        teleport_cd = max(105, int(self.tp_cd * 0.70)) if enraged else self.tp_cd
        if self.tp_timer >= teleport_cd:
            self.tp_timer = 0
            # Teleport to a threatening, but fair, distance instead of on top of the player.
            angle = random.uniform(0, math.tau)
            distance = random.randint(190, 270)
            self.x = max(self.r, min(WORLD_W - self.r, px + math.cos(angle) * distance))
            self.y = max(self.r, min(WORLD_H - self.r, py + math.sin(angle) * distance))
        if self.summ_timer >= self.summ_cd:
            self.summ_timer = 0
            summon_count = max(1, self.summon_count - 1) if enraged else self.summon_count
            for _ in range(summon_count):
                mini_enemies.append(MiniCat(self.x, self.y, self.combat_stage))
        # The final boss keeps its electric paralysis circle active at all times.
        if self.stage == 5 and self.has_ability("shock"):
            self.shock_active = 1
        elif self.has_ability("shock") and self.shock_timer >= self.shock_cd:
            self.shock_timer = 0
            self.shock_active = 20
        if self.shock_active > 0 and not (self.stage == 5 and self.has_ability("shock")):
            self.shock_active -= 1

    def draw(self):
        col = (230, 70, 80) if self.hp <= self.max_hp * 0.5 else (160, 40, 220)
        if self.hit_flash > 0:
            col = WHITE
        sx, sy = world_to_screen(self.x, self.y)
        bob = round(math.sin(pygame.time.get_ticks() * 0.008 + self.anim_phase) * 2)
        sprite = directional_sprite("boss", self.facing)
        if sprite:
            sprite = sprite.copy()
            tint = (80, 0, 110) if not self.is_final_phase_one else (90, 15, 15)
            sprite.fill(tint, special_flags=pygame.BLEND_RGB_ADD)
            if self.hit_flash > 0:
                sprite.fill((110, 110, 110), special_flags=pygame.BLEND_RGB_ADD)
            screen.blit(sprite, sprite.get_rect(center=(int(sx), int(sy + bob))))
        else:
            pygame.draw.circle(screen, col, (int(sx), int(sy)), self.r)
            pygame.draw.circle(screen, BLACK, (int(sx), int(sy)), self.r, 3)
            pygame.draw.polygon(screen, col, [(int(sx) - 35, int(sy) - 35), (int(sx) - 20, int(sy) - 55), (int(sx) - 5, int(sy) - 35)])
            pygame.draw.polygon(screen, col, [(int(sx) + 35, int(sy) - 35), (int(sx) + 20, int(sy) - 55), (int(sx) + 5, int(sy) - 35)])
        if self.has_ability("freeze"):
            pygame.draw.circle(screen, (120, 210, 255), (int(sx), int(sy)), self.freeze_radius, 1)
        if self.has_ability("burn"):
            pygame.draw.circle(screen, (255, 120, 0), (int(sx), int(sy)), self.burn_radius, 1)
        if self.shock_active > 0:
            pygame.draw.circle(screen, (120, 210, 255), (int(sx), int(sy)), 150, 3)
        if self.weakpoint_active():
            wx, wy = self.weakpoint_position()
            wsx, wsy = world_to_screen(wx, wy)
            pygame.draw.circle(screen, (255, 205, 62), (int(wsx), int(wsy)), self.weakpoint_r + 5, 2)
            pygame.draw.circle(screen, (255, 236, 120), (int(wsx), int(wsy)), self.weakpoint_r // 2)
        # Reserve the top HUD area for player health and mission details.
        # The boss readout begins below it instead of being covered by panels.
        bar_w = W - 100
        bar_h = 14
        bar_y = 106
        pygame.draw.rect(screen, BOSS_BAR_BG, (50, bar_y, bar_w, bar_h))
        pygame.draw.rect(screen, GREEN, (50, bar_y, bar_w * (self.hp / self.max_hp), bar_h))
        pygame.draw.rect(screen, WHITE, (50, bar_y, bar_w, bar_h), 2)
        label = "最终首领－第一阶段" if self.is_final_phase_one else "首领"
        txt = font_menu_small.render(label, True, WHITE)
        screen.blit(txt, (W // 2 - txt.get_width() // 2, bar_y + 18))

# Boss Minion Class
class MiniCat:
    def __init__(self, sx, sy, stage=1):
        self.x, self.y = sx, sy
        self.max_hp = 80 if stage == 1 else 100
        self.hp = self.max_hp
        self.r = 10
        self.speed = 2.0
        self.tp_cd = 220
        self.tp_timer = 0
        # Boss minions are melee-only: they have no ranged attack or projectile.
        self.dmg = 2
        self.atk_cd = 0
        self.hit_flash = 0
        self.slow_timer = 0
        self.anim_phase = random.uniform(0, math.tau)
        self.facing = math.pi / 2

    def update(self, px, py):
        if self.slow_timer > 0:
            self.slow_timer -= 1
        dx = px - self.x
        dy = py - self.y
        dist = math.hypot(dx, dy)
        if dist > 0:
            self.facing = math.atan2(dy, dx)
            move_speed = self.speed * (0.72 if self.slow_timer > 0 else 1)
            self.x += dx / dist * move_speed
            self.y += dy / dist * move_speed
        self.tp_timer += 1
        if self.tp_timer >= self.tp_cd:
            self.tp_timer = 0
            self.x = px + random.randint(-80, 80)
            self.y = py + random.randint(-80, 80)
        if self.atk_cd > 0:
            self.atk_cd -= 1
        if self.hit_flash > 0:
            self.hit_flash -= 1

    def draw(self):
        c = (200, 100, 200)
        if self.hit_flash > 0:
            c = WHITE
        sx, sy = world_to_screen(self.x, self.y)
        bob = round(math.sin(pygame.time.get_ticks() * 0.016 + self.anim_phase) * 1)
        sprite = directional_sprite("mini", self.facing)
        if sprite:
            screen.blit(sprite, sprite.get_rect(center=(int(sx), int(sy + bob))))
        else:
            pygame.draw.circle(screen, c, (int(sx), int(sy)), self.r)
            pygame.draw.circle(screen, BLACK, (int(sx), int(sy)), self.r, 2)

# Player Class
class Player:
    def __init__(self, equip_weapon_id):
        persistent = ACTIVE_PROFILE or {}
        talents = persistent.get("talents", {})
        self.x, self.y = WORLD_W // 2, WORLD_H // 2
        self.base_speed = 4 + talents.get("speed", 0) * 0.15
        self.speed_buff = 0
        self.base_max_hp = 100 + talents.get("hp", 0) * 10
        self.hp_buff = 0
        self.hp = self.base_max_hp + self.hp_buff
        self.current_weapon = equip_weapon_id
        self.angle = 0
        # Character facing follows WASD movement; weapon aim follows the mouse.
        self.move_angle = -math.pi / 2
        self.anim_phase = random.uniform(0, math.tau)
        self.shoot_cd_buff = 0
        self.reload_sec_buff = 0
        self.mag_multi = 1
        self.mag_add = 0
        self.spread_mod = 1
        self.particle_boost = 0
        self.slow_enemy_mod = 1
        self.hit_flash = 0
        self.freeze_timer = 0
        self.burn_timer = 0
        self.burn_tick = 0
        self.stun_timer = 0
        # Counts the player's boss-fight recovery interval.
        self.boss_heal_timer = 0
        self.pierce_bonus = 0
        self.chain_chance = 0
        self.chill_chance = 0
        self.push_chance = 0
        self.kill_leech_enabled = False
        self.adrenaline = False
        self.boss_compass = False
        self.auto_loader = False
        self.reserve_reload = 0
        self.shield_ready = False
        self.shield_timer = 0
        # Baseline movement tool: rolling is always available and follows the
        # current WASD direction. It is no longer hidden behind an upgrade.
        self.dash_enabled = True
        self.dash_cd = 0
        self.dash_frames = 0
        self.dash_dir_x, self.dash_dir_y = 0, -1
        self.armor = talents.get("armor", 0)
        self.coin_finder = False
        self.field_medic = False
        self.decoy_enabled = False
        self.decoy_timer = 0
        self.drone_enabled = False
        self.drone_timer = 0
        self.mine_enabled = False
        self.mine_timer = 0
        self.time_ripple = False
        self.ration_enabled = False
        self.ration_timer = 0
        self.scavenge = False
        self.weapon_damage_bonus = 0
        self.weapon_pellet_bonus = 0
        self.weapon_pierce_bonus = 0
        self.weapon_range_bonus = 0
        self.weapon_blast_bonus = 0
        self.weapon_beam_width_bonus = 0
        self.weapon_beam_life_bonus = 0
        self.weapon_spread_mult = 1.0
        self.weapon_ultimate = None
        self.weapon_ultimate_variant = None
        # Two ordinary weapon modules are required before the exclusive
        # ultimate module can enter the upgrade pool.
        self.weapon_upgrade_count = 0
        self.kill_counter = 0
        self.shoot_cd = 0
        self.reload_timer = 0
        self.is_reloading = False
        self.reload_key_down = False
        cfg = WEAPON_CONFIG[self.current_weapon]
        self.current_mag = int(cfg["mag_cap"] * self.mag_multi) + self.mag_add
        # The 38 px weapon starts at the edge of the 30 px player circle.
        self.weapon_length = 38
        self.muzzle_offset = 15 + self.weapon_length

    def calc_speed(self):
        return self.base_speed + self.speed_buff + (1.5 if self.adrenaline and self.hp <= 45 else 0)

    def calc_max_hp(self):
        return self.base_max_hp + self.hp_buff

    def calc_damage(self, base, weapon_key=None):
        # The laser is a continuous beam, so its balance is based on a fixed
        # per-tick damage value rather than stacking global damage upgrades.
        levels = (ACTIVE_PROFILE or {}).get("weapon_upgrades", {}).get(weapon_key or self.current_weapon, {})
        persistent_bonus = levels.get("damage", 0)
        if weapon_key == "laser":
            return base + persistent_bonus
        return base + self.weapon_damage_bonus + persistent_bonus

    def calc_mag(self, base):
        levels = (ACTIVE_PROFILE or {}).get("weapon_upgrades", {}).get(self.current_weapon, {})
        persistent_mag = levels.get("mag", 0) * 2
        fortress_mult = 1.5 if self.weapon_ultimate_variant == "weapon_ultimate_fortress" else 1.0
        return int(base * self.mag_multi * fortress_mult) + self.mag_add + persistent_mag

    def calc_reload(self, base):
        levels = (ACTIVE_PROFILE or {}).get("weapon_upgrades", {}).get(self.current_weapon, {})
        reload_time = base + self.reload_sec_buff
        reload_time *= max(0.70, 1 - levels.get("durability", 0) * 0.05)
        if self.weapon_ultimate_variant == "weapon_ultimate_storm":
            reload_time *= 0.6
        return max(0.4, reload_time)

    def calc_shot_cd(self, base):
        return max(2, base - self.shoot_cd_buff)

    def switch_weapon(self, w):
        self.current_weapon = w
        cfg = WEAPON_CONFIG[w]
        self.current_mag = self.calc_mag(cfg["mag_cap"])
        self.shoot_cd = 0
        self.is_reloading = False
        self.reload_timer = 0

    def apply_boss_effect(self, effect):
        if effect == "freeze":
            self.freeze_timer = max(self.freeze_timer, 100)
        elif effect == "burn":
            self.burn_timer = max(self.burn_timer, 180)
        elif effect == "shock":
            # A short punish rather than a long lockout (15 frames ≈ 0.25 s).
            self.stun_timer = max(self.stun_timer, 15)

    def apply_upgrade(self, perk):
        func = perk["func"]
        if func.startswith("weapon_") and not func.startswith("weapon_ultimate"):
            self.weapon_upgrade_count += 1
        if func == "buff_speed":
            self.speed_buff += 1
        elif func == "buff_speed_big":
            self.speed_buff += 2
        elif func == "buff_hp_25":
            self.hp_buff += 25
            self.hp += 25
        elif func == "buff_hp_50":
            self.hp_buff += 50
            self.hp += 50
        elif func == "buff_hp_100":
            self.hp_buff += 100
            self.hp += 100
        elif func == "buff_mag_5":
            self.mag_add += 5
        elif func == "buff_mag_half":
            self.mag_multi += 0.5
        elif func == "buff_mag_double":
            self.mag_multi *= 2
        elif func == "buff_reload_fast":
            self.reload_sec_buff -= 0.3
        elif func == "buff_fire_rate":
            self.shoot_cd_buff += 1
        elif func == "heal_30":
            self.hp = min(self.calc_max_hp(), self.hp + 30)
        elif func == "heal_60":
            self.hp = min(self.calc_max_hp(), self.hp + 60)
        elif func == "gold_20":
            global gold_total
            gold_total += 20
        elif func == "buff_accuracy":
            self.spread_mod -= 0.04
        elif func == "buff_particle":
            self.particle_boost += 1.2
        elif func == "buff_slow_enemy":
            self.slow_enemy_mod *= 0.85
        elif func == "perk_pierce":
            self.pierce_bonus = min(2, self.pierce_bonus + 2)
        elif func == "perk_chain":
            self.chain_chance = min(0.30, self.chain_chance + 0.30)
        elif func == "perk_chill":
            self.chill_chance = min(0.35, self.chill_chance + 0.35)
        elif func == "perk_push":
            self.push_chance = min(0.25, self.push_chance + 0.25)
        elif func == "perk_leech":
            self.kill_leech_enabled = True
        elif func == "perk_adrenaline":
            self.adrenaline = True
        elif func == "perk_compass":
            self.boss_compass = True
        elif func == "perk_autoload":
            self.auto_loader = True
        elif func == "perk_reserve":
            self.reserve_reload = 1
        elif func == "perk_shield":
            self.shield_ready = True
        elif func == "perk_dash":
            self.dash_enabled = True
        elif func == "perk_armor":
            self.armor = 2
        elif func == "perk_coin":
            self.coin_finder = True
        elif func == "perk_medic":
            self.field_medic = True
        elif func == "perk_decoy":
            self.decoy_enabled = True
        elif func == "perk_drone":
            self.drone_enabled = True
        elif func == "perk_mine":
            self.mine_enabled = True
        elif func == "perk_time":
            self.time_ripple = True
        elif func == "perk_ration":
            self.ration_enabled = True
        elif func == "perk_scavenge":
            self.scavenge = True
        elif func == "weapon_damage_1":
            self.weapon_damage_bonus = min(4, self.weapon_damage_bonus + 1)
        elif func == "weapon_mag_8":
            self.mag_add += 8
        elif func == "weapon_fire_rate_2":
            self.shoot_cd_buff += 2
        elif func == "weapon_reload_05":
            self.reload_sec_buff -= 1.0
        elif func == "weapon_pellet_1":
            self.weapon_pellet_bonus = min(4, self.weapon_pellet_bonus + 1)
        elif func == "weapon_pierce_1":
            self.weapon_pierce_bonus = min(4, self.weapon_pierce_bonus + 1)
        elif func == "weapon_range_20":
            self.weapon_range_bonus = min(80, self.weapon_range_bonus + 20)
        elif func == "weapon_blast_15":
            self.weapon_blast_bonus = min(45, self.weapon_blast_bonus + 15)
        elif func == "weapon_beam_width":
            self.weapon_beam_width_bonus = min(8, self.weapon_beam_width_bonus + 2)
        elif func == "weapon_beam_life":
            self.weapon_beam_life_bonus = min(3, self.weapon_beam_life_bonus + 1)
        elif func == "weapon_stability":
            self.weapon_spread_mult = max(0.55, self.weapon_spread_mult * 0.85)
        elif func.startswith("weapon_ultimate_"):
            self.weapon_ultimate = self.current_weapon
            self.weapon_ultimate_variant = func
            if func == "weapon_ultimate_fortress":
                self.armor = max(self.armor, 2)
        # Upgrades may raise the magazine ceiling, but must never refill the
        # magazine. Keep the rounds already loaded and only clamp if needed.
        cfg = WEAPON_CONFIG[self.current_weapon]
        self.current_mag = min(self.current_mag, self.calc_mag(cfg["mag_cap"]))

    def update(self, keys, mx, my, game_over_flag):
        if self.freeze_timer > 0:
            self.freeze_timer -= 1
        if self.stun_timer > 0:
            self.stun_timer -= 1
        if self.shield_timer > 0:
            self.shield_timer -= 1
        if self.dash_cd > 0:
            self.dash_cd -= 1
        if self.dash_frames > 0:
            self.dash_frames -= 1
        if self.ration_enabled:
            self.ration_timer += 1
            if self.ration_timer >= 8 * 60:
                self.ration_timer = 0
                self.hp = min(self.calc_max_hp(), self.hp + 10)
        if self.burn_timer > 0:
            self.burn_timer -= 1
            self.burn_tick += 1
            if self.burn_tick >= 30:
                self.burn_tick = 0
                self.hp -= 2
        else:
            self.burn_tick = 0
        if not game_over_flag:
            spd = self.calc_speed()
            if self.freeze_timer > 0:
                spd *= 0.45
            if self.stun_timer > 0:
                spd = 0
            move_x = int(keys[pygame.K_d]) - int(keys[pygame.K_a])
            move_y = int(keys[pygame.K_s]) - int(keys[pygame.K_w])
            if (move_x or move_y) and spd > 0:
                self.move_angle = math.atan2(move_y, move_x)
                length = math.hypot(move_x, move_y)
                self.dash_dir_x, self.dash_dir_y = move_x / length, move_y / length
            if self.dash_frames > 0:
                # Ten short movement frames feel like an actual roll, rather
                # than a teleport directly onto (or away from) an enemy.
                self.x = max(15, min(WORLD_W - 15, self.x + self.dash_dir_x * spd * 3.1))
                self.y = max(15, min(WORLD_H - 15, self.y + self.dash_dir_y * spd * 3.1))
            else:
                if keys[pygame.K_w] and self.y > 15:
                    self.y -= spd
                if keys[pygame.K_s] and self.y < WORLD_H - 15:
                    self.y += spd
                if keys[pygame.K_a] and self.x > 15:
                    self.x -= spd
                if keys[pygame.K_d] and self.x < WORLD_W - 15:
                    self.x += spd
            if self.dash_enabled and keys[pygame.K_SPACE] and self.dash_cd == 0:
                self.dash_frames = 10
                self.dash_cd = 90
        if self.shoot_cd > 0:
            self.shoot_cd -= 1
        cfg = WEAPON_CONFIG[self.current_weapon]
        real_reload = self.calc_reload(cfg["reload_sec"])
        if self.is_reloading:
            self.reload_timer -= 1
            if self.reload_timer <= 0:
                self.current_mag = self.calc_mag(cfg["mag_cap"])
                self.is_reloading = False
        # Reload is edge-triggered. Holding R used to start another reload the
        # instant the previous one ended, which could feel like firing stopped.
        reload_pressed = bool(keys[pygame.K_r]) and not self.reload_key_down
        self.reload_key_down = bool(keys[pygame.K_r])
        if reload_pressed and not self.is_reloading and not game_over_flag:
            self.start_reload()
        if self.current_mag <= 0 and not self.is_reloading and not game_over_flag:
            self.start_reload()
        dx = mx - self.x
        dy = my - self.y
        self.angle = math.atan2(dy, dx)
        if self.hit_flash > 0:
            self.hit_flash -= 1

    def start_reload(self):
        cfg = WEAPON_CONFIG[self.current_weapon]
        if self.current_mag <= 0 and self.reserve_reload > 0:
            self.reserve_reload -= 1
            self.current_mag = self.calc_mag(cfg["mag_cap"])
            return
        real_reload = self.calc_reload(cfg["reload_sec"])
        self.is_reloading = True
        self.reload_timer = real_reload * 60

    def can_shoot(self, game_over_flag):
        if game_over_flag:
            return False
        cfg = WEAPON_CONFIG[self.current_weapon]
        real_cd = self.calc_shot_cd(cfg["shot_cd"])
        return not self.is_reloading and self.current_mag > 0 and self.shoot_cd == 0

    def fire(self, mx, my):
        cfg = WEAPON_CONFIG[self.current_weapon]
        real_cd = self.calc_shot_cd(cfg["shot_cd"])
        base_dmg = self.calc_damage(cfg["damage"], self.current_weapon)
        ultimate_active = self.weapon_ultimate == self.current_weapon
        ultimate_variant = self.weapon_ultimate_variant if ultimate_active else None
        if ultimate_variant == "weapon_ultimate_storm":
            real_cd = max(1, int(real_cd * 0.6))
        elif ultimate_variant == "weapon_ultimate_barrage":
            barrage_penalty = {
                "shotgun": 4, "laser": 1, "flamethrower": 1, "grenade": 10,
                "rifle": 2, "smg": 1, "pistol": 2, "sniper": 22, "crossbow": 4,
            }[self.current_weapon]
            base_dmg = max(1, base_dmg - barrage_penalty)
        elif ultimate_variant == "weapon_ultimate_overcharge":
            base_dmg += 3 if self.current_weapon == "laser" else 8
        bullet_cfg = dict(cfg)
        bullet_cfg["pierce"] = cfg.get("pierce", 1) + self.pierce_bonus + self.weapon_pierce_bonus
        bullet_cfg["range"] = cfg.get("range", 90) + self.weapon_range_bonus
        bullet_cfg["beam_life"] = 2 + self.weapon_beam_life_bonus
        if ultimate_variant == "weapon_ultimate_ranger":
            bullet_cfg["pierce"] += 3
            bullet_cfg["range"] += 80
            bullet_cfg["beam_life"] += 2
        self.current_mag -= 1
        self.shoot_cd = real_cd
        mz_x = self.x + math.cos(self.angle) * self.muzzle_offset
        mz_y = self.y + math.sin(self.angle) * self.muzzle_offset
        pellets = []
        cnt = cfg["pellet_count"] + self.weapon_pellet_bonus
        if ultimate_variant == "weapon_ultimate_barrage":
            barrage_count = {
                "shotgun": 6, "laser": 2, "flamethrower": 3, "grenade": 2,
                "rifle": 3, "smg": 3, "pistol": 2, "sniper": 1, "crossbow": 1,
            }[self.current_weapon]
            cnt += barrage_count
        base_spread = 0.18 * self.spread_mod * self.weapon_spread_mult
        step = base_spread / (cnt - 1) if cnt > 1 else 0
        offset = -base_spread / 2
        for _ in range(cnt):
            b = Bullet(mz_x, mz_y, mx, my, offset, base_dmg, self.current_weapon, bullet_cfg)
            if self.current_weapon == "grenade":
                b.explosion_radius += self.weapon_blast_bonus
            elif self.current_weapon == "laser":
                b.radius += self.weapon_beam_width_bonus
            if ultimate_variant == "weapon_ultimate_overcharge":
                if self.current_weapon == "laser":
                    b.radius += 5
                elif self.current_weapon == "grenade":
                    b.explosion_radius = max(b.explosion_radius, 145)
                elif self.current_weapon == "flamethrower":
                    b.dmg_mod = max(1, int(b.dmg_mod * 1.8))
                else:
                    b.pierce_left += 5
            pellets.append(b)
            offset += step
        play_weapon_sound(self.current_weapon)
        return pellets

    def get_muzzle(self):
        x = self.x + math.cos(self.angle) * self.muzzle_offset
        y = self.y + math.sin(self.angle) * self.muzzle_offset
        return x, y

    def get_weapon_center(self):
        # Place the rear of the image against the player, with its muzzle forward.
        offset = 15 + self.weapon_length / 2
        return (
            self.x + math.cos(self.angle) * offset,
            self.y + math.sin(self.angle) * offset,
        )

    def draw(self, mx, my):
        col = GREEN
        if self.hit_flash > 0:
            col = RED
        sx, sy = world_to_screen(self.x, self.y)
        bob = round(math.sin(pygame.time.get_ticks() * 0.014 + self.anim_phase) * 1.5)
        sprite = directional_sprite("player", self.move_angle)
        if sprite:
            if self.hit_flash > 0:
                sprite = sprite.copy()
                sprite.fill((110, 30, 30), special_flags=pygame.BLEND_RGB_ADD)
            screen.blit(sprite, sprite.get_rect(center=(int(sx), int(sy + bob))))
        else:
            pygame.draw.circle(screen, col, (int(sx), int(sy)), 15)
            pygame.draw.circle(screen, BLACK, (int(sx), int(sy)), 15, 2)
        if self.freeze_timer > 0:
            pygame.draw.circle(screen, (120, 210, 255), (int(sx), int(sy)), 19, 2)
        if self.burn_timer > 0:
            pygame.draw.circle(screen, (255, 120, 0), (int(sx), int(sy)), 22, 2)
        if self.stun_timer > 0:
            pygame.draw.circle(screen, (255, 235, 80), (int(sx), int(sy)), 25, 2)
        gun = WEAPON_SPRITES[self.current_weapon]
        rot = rotated_weapon_sprite(self.current_weapon, gun, self.angle)
        rect = rot.get_rect(center=world_to_screen(*self.get_weapon_center()))
        screen.blit(rot, rect)
        if self.shoot_cd > 2:
            # Transform the actual barrel-tip point in the sprite, not just its center.
            local_x = gun.get_width() / 2
            local_y = (WEAPON_MUZZLE_Y[self.current_weapon] - 0.5) * gun.get_height()
            mxz = rect.centerx + local_x * math.cos(self.angle) - local_y * math.sin(self.angle)
            myz = rect.centery + local_x * math.sin(self.angle) + local_y * math.cos(self.angle)
            pygame.draw.circle(screen, ORANGE_FLASH, (int(mxz), int(myz)), 5)
            pygame.draw.circle(screen, WHITE, (int(mxz), int(myz)), 2)

# Upgrade Menu Popup
def draw_upgrade_menu(card_list, refresh_left, mouse, intro_timer=0):
    overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 210))
    screen.blit(overlay, (0, 0))
    is_ultimate_choice = bool(card_list) and all(
        perk["func"].startswith("weapon_ultimate_") for perk in card_list
    )
    title = font_menu_large.render("终极分支选择" if is_ultimate_choice else "战术强化终端", True, CARD_EPIC if is_ultimate_choice else UI_AMBER)
    screen.blit(title, title.get_rect(center=(W // 2, 90)))
    sub_text = "高压核心正在展开：仅可锁定一个终极分支" if is_ultimate_choice else "从废土补给中选择一项作战模块"
    sub = font_small.render(sub_text, True, UI_TEXT_DIM)
    screen.blit(sub, sub.get_rect(center=(W // 2, 124)))
    card_w, card_h = 240, 340
    gap = 50
    total_w = card_w * 3 + gap * 2
    start_x = (W - total_w) // 2
    refresh_rect = pygame.Rect(W // 2 - 110, H - 110, 220, 60)

    # Every upgrade reveal fans out from the centre. Ultimate choices first
    # charge an electric core, then the core dissipates as the three cards open.
    if is_ultimate_choice and intro_timer > 15:
        pulse = (intro_timer - 15) / 15
        cx, cy = W // 2, H // 2 - 20
        glow = pygame.Surface((260, 260), pygame.SRCALPHA)
        alpha = int(105 + 90 * pulse)
        pygame.draw.circle(glow, (100, 185, 255, alpha // 3), (130, 130), int(92 + pulse * 25))
        pygame.draw.circle(glow, (185, 105, 255, alpha), (130, 130), int(26 + pulse * 12), 3)
        pygame.draw.circle(glow, (238, 245, 255, alpha), (130, 130), 10)
        screen.blit(glow, glow.get_rect(center=(cx, cy)))
        for bolt in range(9):
            angle = bolt * math.tau / 9 + pygame.time.get_ticks() * 0.009
            points = [(cx, cy)]
            for step in range(1, 5):
                radius = step * 24
                jitter = math.sin(pygame.time.get_ticks() * 0.04 + bolt * 3 + step) * 10
                points.append((cx + math.cos(angle) * radius + jitter, cy + math.sin(angle) * radius + jitter))
            pygame.draw.lines(screen, (216, 235, 255), False, points, 2)
        charge = font_menu_small.render("终极核心充能", True, CARD_EPIC)
        screen.blit(charge, charge.get_rect(center=(cx, cy + 145)))
        draw_wasteland_scanlines(14)
        return [], refresh_rect

    spread_progress = 1.0 if intro_timer <= 0 else max(0, 1 - intro_timer / 15)
    # Smoothstep starts and ends gently, so the reveal is continuous rather
    # than feeling like three cards jump between fixed positions.
    spread_progress = spread_progress * spread_progress * (3 - 2 * spread_progress)
    card_rects = []
    for i, perk in enumerate(card_list):
        final_x = start_x + i * (card_w + gap)
        final_y = 160
        cx = int((W - card_w) / 2 + (final_x - (W - card_w) / 2) * spread_progress)
        cy = int(H // 2 - card_h // 2 + (final_y - (H // 2 - card_h // 2)) * spread_progress)
        rect = pygame.Rect(cx, cy, card_w, card_h)
        card_rects.append((rect, perk))
        if perk["tier"] == "史诗":
            brd = CARD_EPIC
        elif perk["tier"] == "稀有":
            brd = CARD_RARE
        else:
            brd = CARD_COMMON
        card_offset = draw_image_card_base(rect, mouse)
        pygame.draw.line(screen, brd, (cx + 28, cy + 44), (cx + card_w - 28, cy + 44), 2)
        index = font_small.render(f"MOD-{i + 1:02d}", True, UI_TEXT_DIM)
        screen.blit(index, (cx + 34 + card_offset[0], cy + 24 + card_offset[1]))
        name_lines = card_text_lines(perk["name"], WHITE, rect, 22, 16, 2)
        draw_centered_card_lines(name_lines, cx + card_w // 2 + card_offset[0], cy + 80 + card_offset[1], 3)
        desc_lines = card_text_lines(perk["desc"], LIGHT_GRAY, rect, 16, 13, 2)
        draw_centered_card_lines(desc_lines, cx + card_w // 2 + card_offset[0], cy + 138 + card_offset[1], 5)
        tier_lines = card_text_lines(f"[{perk['tier']} 模组]", brd, rect, 20, 14, 1)
        draw_centered_card_lines(tier_lines, cx + card_w // 2 + card_offset[0], cy + 270 + card_offset[1])
    txt = f"刷新（剩余 {refresh_left}/2）"
    draw_wasteland_button(refresh_rect, txt, mouse, refresh_left > 0, font_menu_mid)
    draw_wasteland_scanlines(14)
    return card_rects, refresh_rect

def generate_upgrade_cards(player=None):
    pool = []
    for p in UPGRADE_LIST:
        if p["tier"] == "普通":
            pool += [p] * 6
        elif p["tier"] == "稀有":
            pool += [p] * 3
        else:
            pool.append(p)
    # Weapon modules are generated for the currently equipped weapon. High
    # damage weapons trade raw damage for handling, while low damage weapons
    # may receive restrained damage increases. Laser damage stays fixed.
    if player:
        cfg = WEAPON_CONFIG[player.current_weapon]
        weapon_name = cfg["name"]
        handling_modules = [
            {"id": 101, "name": f"{weapon_name}：快速机件", "desc": "当前武器射击间隔进一步缩短", "tier": "普通", "func": "weapon_fire_rate_2"},
            {"id": 102, "name": f"{weapon_name}：扩容组件", "desc": "当前武器弹匣容量增加 8 发", "tier": "普通", "func": "weapon_mag_8"},
            {"id": 103, "name": f"{weapon_name}：速装机构", "desc": "当前武器装填时间减少 1 秒", "tier": "稀有", "func": "weapon_reload_05"},
        ]
        specific_modules = {
            "pistol": [
                {"id": 110, "name": "手枪：穿甲套件", "desc": "手枪额外穿透 1 个目标", "tier": "普通", "func": "weapon_pierce_1"},
                {"id": 111, "name": "手枪：稳定握把", "desc": "手枪弹道散布降低 15%", "tier": "普通", "func": "weapon_stability"},
                {"id": 112, "name": "手枪：长程枪管", "desc": "手枪有效射程增加 20", "tier": "稀有", "func": "weapon_range_20"},
            ],
            "rifle": [
                {"id": 113, "name": "突击步枪：穿甲弹芯", "desc": "突击步枪额外穿透 1 个目标", "tier": "普通", "func": "weapon_pierce_1"},
                {"id": 114, "name": "突击步枪：平衡枪托", "desc": "突击步枪弹道散布降低 15%", "tier": "普通", "func": "weapon_stability"},
                {"id": 115, "name": "突击步枪：延程组件", "desc": "突击步枪有效射程增加 20", "tier": "稀有", "func": "weapon_range_20"},
            ],
            "smg": [
                {"id": 116, "name": "冲锋枪：高速弹芯", "desc": "冲锋枪额外穿透 1 个目标", "tier": "普通", "func": "weapon_pierce_1"},
                {"id": 117, "name": "冲锋枪：控枪模组", "desc": "冲锋枪弹道散布降低 15%", "tier": "普通", "func": "weapon_stability"},
                {"id": 118, "name": "冲锋枪：长程机匣", "desc": "冲锋枪有效射程增加 20", "tier": "稀有", "func": "weapon_range_20"},
            ],
            "shotgun": [
                {"id": 119, "name": "霰弹枪：簇射供弹", "desc": "霰弹枪每次额外发射 1 枚弹丸", "tier": "稀有", "func": "weapon_pellet_1"},
                {"id": 120, "name": "霰弹枪：收束器", "desc": "霰弹枪弹道散布降低 15%", "tier": "普通", "func": "weapon_stability"},
                {"id": 121, "name": "霰弹枪：破障弹", "desc": "霰弹枪额外穿透 1 个目标", "tier": "普通", "func": "weapon_pierce_1"},
            ],
            "sniper": [
                {"id": 122, "name": "狙击枪：高穿深弹", "desc": "狙击枪额外穿透 1 个目标", "tier": "稀有", "func": "weapon_pierce_1"},
                {"id": 123, "name": "狙击枪：精密导轨", "desc": "狙击枪弹道散布降低 15%", "tier": "普通", "func": "weapon_stability"},
                {"id": 124, "name": "狙击枪：超程弹体", "desc": "狙击枪有效射程增加 20", "tier": "普通", "func": "weapon_range_20"},
            ],
            "crossbow": [
                {"id": 125, "name": "弩：重型箭簇", "desc": "弩箭额外穿透 1 个目标", "tier": "稀有", "func": "weapon_pierce_1"},
                {"id": 126, "name": "弩：稳固弓臂", "desc": "弩箭弹道散布降低 15%", "tier": "普通", "func": "weapon_stability"},
                {"id": 127, "name": "弩：延程箭杆", "desc": "弩箭有效射程增加 20", "tier": "普通", "func": "weapon_range_20"},
            ],
            "flamethrower": [
                {"id": 128, "name": "喷火枪：增压喷口", "desc": "火焰有效射程增加 20", "tier": "稀有", "func": "weapon_range_20"},
                {"id": 129, "name": "喷火枪：分流喷嘴", "desc": "每次额外喷出 1 团火焰", "tier": "普通", "func": "weapon_pellet_1"},
                {"id": 130, "name": "喷火枪：收束火焰", "desc": "火焰散布降低 15%", "tier": "普通", "func": "weapon_stability"},
            ],
            "grenade": [
                {"id": 131, "name": "榴弹发射器：破片外壳", "desc": "爆炸半径增加 15", "tier": "稀有", "func": "weapon_blast_15"},
                {"id": 132, "name": "榴弹发射器：延程装药", "desc": "榴弹有效射程增加 20", "tier": "普通", "func": "weapon_range_20"},
                {"id": 133, "name": "榴弹发射器：集束装填", "desc": "每次额外发射 1 枚榴弹", "tier": "普通", "func": "weapon_pellet_1"},
            ],
            "laser": [
                {"id": 134, "name": "激光枪：棱镜扩束", "desc": "激光束宽度增加 2", "tier": "稀有", "func": "weapon_beam_width"},
                {"id": 135, "name": "激光枪：持续电容", "desc": "激光束持续时间增加 1 帧", "tier": "普通", "func": "weapon_beam_life"},
                {"id": 136, "name": "激光枪：折射镜组", "desc": "激光束弹道散布降低 15%", "tier": "普通", "func": "weapon_stability"},
            ],
        }[player.current_weapon]
        # Weapon cards are deliberately weighted above generic survivor perks,
        # so the equipped gun forms a recognisable build more often.
        pool += handling_modules * 5
        pool += specific_modules * 5
        if cfg["damage"] <= 12 and player.current_weapon != "laser":
            pool += [{"id": 104, "name": f"{weapon_name}：强化弹头", "desc": "当前武器单次伤害增加 1", "tier": "稀有", "func": "weapon_damage_1"}] * 4
        if player.weapon_ultimate is None and player.weapon_upgrade_count >= 2:
            # This milestone is a true three-way branch. Picking one variant
            # records it permanently and removes the other two from the run.
            ultimate_text = {
                "pistol": (
                    ("终极 I｜双重速射", "额外发射 2 发手枪弹；每发伤害降低 2 点。"),
                    ("终极 II｜穿甲超载", "伤害增加 8 点，并额外穿透 5 个目标。"),
                    ("终极 III｜疾速扳机", "射击间隔与装填时间均缩短 40%。"),
                ),
                "rifle": (
                    ("终极 I｜三连火网", "额外发射 3 发步枪弹；每发伤害降低 2 点。"),
                    ("终极 II｜战术超穿", "伤害增加 8 点，并额外穿透 5 个目标。"),
                    ("终极 III｜突击回路", "射击间隔与装填时间均缩短 40%。"),
                ),
                "smg": (
                    ("终极 I｜密集弹幕", "额外发射 3 发冲锋枪弹；每发伤害降低 1 点。"),
                    ("终极 II｜高速穿甲", "伤害增加 8 点，并额外穿透 5 个目标。"),
                    ("终极 III｜狂飙机匣", "射击间隔与装填时间均缩短 40%。"),
                ),
                "shotgun": (
                    ("终极 I｜分裂弹幕", "额外发射 6 枚霰弹；每枚伤害降低 4 点。"),
                    ("终极 II｜破障超载", "伤害增加 8 点，并额外穿透 5 个目标。"),
                    ("终极 III｜暴风供弹", "射击间隔与装填时间均缩短 40%。"),
                ),
                "sniper": (
                    ("终极 I｜双重狙击", "额外发射 1 枚狙击弹；每枚伤害降低 22 点。"),
                    ("终极 II｜反器材超载", "伤害增加 8 点，并额外穿透 5 个目标。"),
                    ("终极 III｜迅捷枪机", "射击间隔与装填时间均缩短 40%。"),
                ),
                "crossbow": (
                    ("终极 I｜双矢齐发", "额外发射 1 支弩箭；每支伤害降低 4 点。"),
                    ("终极 II｜贯穿箭簇", "伤害增加 8 点，并额外穿透 5 个目标。"),
                    ("终极 III｜滑轮回路", "射击间隔与装填时间均缩短 40%。"),
                ),
                "flamethrower": (
                    ("终极 I｜三重喷流", "额外喷出 3 团火焰；每团伤害降低 1 点。"),
                    ("终极 II｜高温超载", "火焰伤害显著提升，并扩大灼烧范围。"),
                    ("终极 III｜涡轮供油", "射击间隔与装填时间均缩短 40%。"),
                ),
                "grenade": (
                    ("终极 I｜集束榴弹", "额外发射 2 枚榴弹；每枚伤害降低 10 点。"),
                    ("终极 II｜重爆超载", "伤害增加 8 点，爆炸半径至少提升至 145。"),
                    ("终极 III｜自动装填", "射击间隔与装填时间均缩短 40%。"),
                ),
                "laser": (
                    ("终极 I｜三棱折射", "额外释放 2 道激光束；每道伤害降低 1 点。"),
                    ("终极 II｜聚焦超载", "激光伤害增加 3 点，并显著加宽光束。"),
                    ("终极 III｜脉冲回路", "射击间隔与装填时间均缩短 40%。"),
                ),
            }[player.current_weapon]
            ultimate_options = [
                {"id": 105, "name": f"{weapon_name}：{ultimate_text[0][0]}", "desc": ultimate_text[0][1], "tier": "史诗", "func": "weapon_ultimate_barrage"},
                {"id": 106, "name": f"{weapon_name}：{ultimate_text[1][0]}", "desc": ultimate_text[1][1], "tier": "史诗", "func": "weapon_ultimate_overcharge"},
                {"id": 107, "name": f"{weapon_name}：{ultimate_text[2][0]}", "desc": ultimate_text[2][1], "tier": "史诗", "func": "weapon_ultimate_storm"},
                {"id": 108, "name": f"{weapon_name}：终极 IV｜堡垒弹仓", "desc": "弹匣容量提升 50%，并获得 2 点护甲。", "tier": "史诗", "func": "weapon_ultimate_fortress"},
                {"id": 109, "name": f"{weapon_name}：终极 V｜远征穿透", "desc": "额外穿透 3 个目标，射程增加 80。", "tier": "史诗", "func": "weapon_ultimate_ranger"},
            ]
            # Five total ultimate types exist; the terminal presents a fresh
            # three-card branch, preserving the one-choice-only rule.
            return random.sample(ultimate_options, 3)
    res = []
    while len(res) < 3:
        pick = random.choice(pool)
        if pick not in res:
            res.append(pick)
    return res

# Weapon Shop UI
def draw_shop(gold, owned, mouse):
    overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 200))
    screen.blit(overlay, (0, 0))
    box_w, box_h = 920, 600
    bx = (W - box_w) // 2
    by = (H - box_h) // 2
    draw_wasteland_panel((bx, by, box_w, box_h), UI_ORANGE, (20, 27, 28), 4)
    title = font_menu_large.render("废土军械库", True, UI_AMBER)
    screen.blit(title, title.get_rect(center=(W // 2, by + 50)))
    gold_txt = font_menu_small.render(f"可用废料：{gold}", True, UI_CYAN)
    screen.blit(gold_txt, (bx + 35, by + 82))
    back_rect = pygame.Rect(W - 180, by + 30, 140, 55)
    draw_wasteland_button(back_rect, "返回终端", mouse, True, font_menu_mid)
    btns = []
    shop_list = [weapon for weapon in ALL_WEAPON_LIST if weapon != "pistol"]
    cw, ch, gap = 200, 180, 20
    total = cw * 4 + gap * 3
    sx = (W - total) // 2
    sy = by + 130
    for idx, w in enumerate(shop_list):
        cfg = WEAPON_CONFIG[w]
        cx = sx + (idx % 4) * (cw + gap)
        cy = sy + (idx // 4) * (ch + 25)
        rect = pygame.Rect(cx, cy, cw, ch)
        btns.append((rect, w))
        if w in owned:
            bg = (34, 39, 38)
            tcol = BTN_LOCKED_TEXT
            tip = "已拥有"
        else:
            if gold >= cfg["cost"]:
                bg = UI_METAL_HOVER if rect.collidepoint(mouse) else UI_METAL
                tcol = WHITE
                tip = "点击购买"
            else:
                bg = (34, 39, 38)
                tcol = BTN_LOCKED_TEXT
                tip = "金币不足"
        card_offset = draw_image_card_base(rect, mouse, w not in owned and gold >= cfg["cost"])
        name_t = fit_card_text(cfg["name"], tcol, rect, 20)
        screen.blit(name_t, name_t.get_rect(center=(cx + cw // 2 + card_offset[0], cy + 35 + card_offset[1])))
        icon = WEAPON_SELECT_SPRITES[w]
        screen.blit(icon, icon.get_rect(center=(cx + cw // 2 + card_offset[0], cy + 72 + card_offset[1])))
        cost_t = fit_card_text(f"{cfg['cost']} 废料", UI_AMBER, rect, 24)
        screen.blit(cost_t, cost_t.get_rect(center=(cx + cw // 2 + card_offset[0], cy + 104 + card_offset[1])))
        tip_t = fit_card_text(tip, tcol, rect, 17)
        screen.blit(tip_t, tip_t.get_rect(center=(cx + cw // 2 + card_offset[0], cy + 145 + card_offset[1])))
    draw_wasteland_scanlines(10)
    return btns, back_rect

# Weapon Select Modal
def draw_weapon_select(gold, owned, equip, mouse):
    overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 200))
    screen.blit(overlay, (0, 0))
    box_w, box_h = 920, 650
    bx = (W - box_w) // 2
    by = (H - box_h) // 2
    draw_wasteland_panel((bx, by, box_w, box_h), UI_CYAN, (20, 27, 28), 4)
    title = font_menu_mid.render("装备配置终端", True, UI_AMBER)
    screen.blit(title, title.get_rect(center=(W // 2, by + 30)))
    gold_t = font_menu_small.render(f"库存废料：{gold}", True, UI_CYAN)
    screen.blit(gold_t, (bx + 30, by + 55))
    back_rect = pygame.Rect(W - 180, by + 18, 140, 45)
    draw_wasteland_button(back_rect, "返回", mouse, True, font_menu_mid)
    btns = []
    cw, ch, gap = 200, 155, 20
    total_w = cw * 4 + gap * 3
    start_x = bx + (box_w - total_w) // 2
    start_y = by + 90
    for idx, wid in enumerate(ALL_WEAPON_LIST):
        cfg = WEAPON_CONFIG[wid]
        x = start_x + (idx % 4) * (cw + gap)
        y = start_y + (idx // 4) * (ch + 16)
        rect = pygame.Rect(x, y, cw, ch)
        btns.append((rect, wid))
        card_offset = draw_image_card_base(rect, mouse, wid in owned, wid == equip)
        name_t = fit_card_text(cfg["name"], WHITE, rect, 18)
        screen.blit(name_t, name_t.get_rect(center=(x + cw // 2 + card_offset[0], y + 28 + card_offset[1])))
        gun = WEAPON_SELECT_SPRITES[wid]
        screen.blit(gun, gun.get_rect(center=(x + cw // 2 + card_offset[0], y + 78 + card_offset[1])))
        if wid == equip:
            stat = "已装备"
            sc = UI_CYAN
        elif wid in owned:
            stat = "点击装备"
            sc = WHITE
        else:
            stat = "未解锁（商店购买）"
            sc = BTN_LOCKED_TEXT
        stat_t = fit_card_text(stat, sc, rect, 16)
        screen.blit(stat_t, stat_t.get_rect(center=(x + cw // 2 + card_offset[0], y + 126 + card_offset[1])))
    draw_wasteland_scanlines(10)
    return btns, back_rect

# Main Menu Screen
def draw_menu(max_unlock, gold, mouse):
    if MENU_COMMAND_BG:
        screen.blit(MENU_COMMAND_BG, (0, 0))
    else:
        screen.fill(UI_VOID)
    veil = pygame.Surface((W, H), pygame.SRCALPHA)
    # Keep the illustrated sunset atmospheric rather than dazzling.
    veil.fill((5, 8, 8, 148))
    screen.blit(veil, (0, 0))
    header = pygame.Rect(25, 22, W - 50, 76)
    draw_wasteland_panel(header, UI_AMBER, (15, 21, 20), 3)
    badge = pygame.Rect(43, 38, 62, 43)
    draw_wasteland_panel(badge, UI_CYAN, (22, 54, 52), 2)
    badge_t = font_small.render("WZ", True, WHITE)
    screen.blit(badge_t, badge_t.get_rect(center=badge.center))
    title = font_menu_large.render("废土火线", True, UI_AMBER)
    screen.blit(title, title.get_rect(midleft=(125, 60)))
    title_sub = font_menu_small.render("作战指挥终端  /  WASTELAND COMMAND", True, UI_TEXT_DIM)
    screen.blit(title_sub, title_sub.get_rect(midleft=(350, 61)))
    gold_box = pygame.Rect(W - 215, 38, 150, 43)
    draw_wasteland_panel(gold_box, UI_CYAN, (16, 40, 39), 2)
    gold_t = font_small.render(f"废料 {gold}", True, WHITE)
    screen.blit(gold_t, gold_t.get_rect(center=gold_box.center))

    mission_box = pygame.Rect(44, 145, 570, 410)
    draw_wasteland_panel(mission_box, UI_ORANGE, (12, 18, 18), 3)
    section = font_menu_mid.render("战区部署", True, UI_AMBER)
    screen.blit(section, (72, 168))
    info = font_small.render("选择作战区域，清除威胁后解锁后续区域", True, UI_TEXT_DIM)
    screen.blit(info, (74, 211))
    pygame.draw.line(screen, UI_RUST, (72, 247), (586, 247), 2)
    # Ten region cards sit fully inside the deployment panel in two rows.
    # The text uses the original readable sizes; only unused horizontal space
    # was tightened so neither cards nor labels spill out of their frame.
    bw, bh, gap = 96, 78, 9
    sx = 72
    stage_btns = []
    for i in range(len(STAGE_LIVE_LIMIT)):
        st = i + 1
        bx = sx + (i % 5) * (bw + gap)
        by = 270 + (i // 5) * 105
        rect = pygame.Rect(bx, by, bw, bh)
        stage_btns.append((rect, st))
        if st <= max_unlock:
            bg = UI_METAL_HOVER if rect.collidepoint(mouse) else UI_METAL
            tcol = WHITE
        else:
            bg = (34, 39, 38)
            tcol = BTN_LOCKED_TEXT
        text_offset = draw_image_button_base(rect, mouse, st <= max_unlock)
        code_t = font_card_desc.render(f"区域 {st:02d}", True, UI_TEXT_DIM if st <= max_unlock else BTN_LOCKED_TEXT)
        screen.blit(code_t, code_t.get_rect(center=(bx + bw // 2 + text_offset[0], by + 22 + text_offset[1])))
        if st <= max_unlock:
            st_t = font_small.render(f"第{st}关", True, tcol)
            stage_rect = st_t.get_rect(center=(bx + bw // 2 + text_offset[0], by + 54 + text_offset[1]))
            screen.blit(st_t, stage_rect)
        else:
            # A locked card uses a single short state label.  The former
            # two-label layout was what caused text to overlap and spill.
            lock_t = font_small.render("未解锁", True, BTN_LOCKED_TEXT)
            screen.blit(lock_t, lock_t.get_rect(center=(bx + bw // 2, by + 54)))

    ops_box = pygame.Rect(652, 145, 304, 410)
    draw_wasteland_panel(ops_box, UI_CYAN, (12, 18, 18), 3)
    ops_title = font_menu_mid.render("行动控制", True, UI_CYAN)
    screen.blit(ops_title, (682, 168))
    ops_tip = font_small.render("整备、记录与军械管理", True, UI_TEXT_DIM)
    screen.blit(ops_tip, (683, 212))
    button_specs = [
        ("装备配置", "weapons"),
        ("军械库", "shop"),
        ("天赋升级", "talents"),
        ("武器改造", "weapon_lab"),
        ("成就档案", "achievement"),
        ("敌情图鉴", "codex"),
        ("退出终端", "quit"),
    ]
    operation_rects = {}
    for index, (label, action) in enumerate(button_specs):
        rect = pygame.Rect(682, 239 + index * 43, 244, 39)
        operation_rects[action] = rect
        draw_wasteland_button(rect, label, mouse, True, font_menu_small)
    footer = font_small.render("系统状态：在线  ·  生存者协议 v1.0", True, UI_TEXT_DIM)
    screen.blit(footer, footer.get_rect(center=(W // 2, H - 34)))
    return stage_btns, operation_rects


def draw_collection_page(profile, page_kind, mouse):
    """Homepage pages for persistent achievement and enemy-record progress."""
    if MENU_COMMAND_BG:
        screen.blit(MENU_COMMAND_BG, (0, 0))
    else:
        screen.fill(UI_VOID)
    veil = pygame.Surface((W, H), pygame.SRCALPHA)
    veil.fill((5, 8, 8, 174))
    screen.blit(veil, (0, 0))
    box = pygame.Rect(90, 72, W - 180, H - 144)
    draw_wasteland_panel(box, UI_CYAN if page_kind == "codex" else UI_AMBER, (12, 18, 18), 4)
    title_text = "敌情图鉴" if page_kind == "codex" else "行动成就"
    title = font_menu_large.render(title_text, True, UI_CYAN if page_kind == "codex" else UI_AMBER)
    screen.blit(title, title.get_rect(center=(W // 2, 122)))
    subtitle = font_small.render("记录会在本次运行期间持续更新", True, UI_TEXT_DIM)
    screen.blit(subtitle, subtitle.get_rect(center=(W // 2, 158)))
    back_rect = pygame.Rect(W - 238, 96, 110, 44)
    draw_wasteland_button(back_rect, "返回主页", mouse, True, font_menu_small)

    if page_kind == "achievement":
        entries = [
            ("first_elite", "精英清除者", "首次击败任意带词缀的精英敌人。"),
            ("combo_10", "十连清除", "在连杀倒计时结束前连续击败 10 个目标。"),
            ("stage_sweeper", "战区清扫者", "在任意战区清除全部规定数量的普通敌人。"),
            ("boss_hunter", "首领猎手", "击败任意一名首领。"),
        ]
    else:
        entries = [
            ("basic", "普通感染者", "基础单位，成群接近玩家。"),
            ("fast", "快速感染者", "移动速度更高的追击单位。"),
            ("tank", "肉盾感染者", "高生命值、高接触威胁单位。"),
            ("scout", "侦察感染者", "装有扫描器的敏捷单位，速度与耐久均衡。"),
            ("brute", "蛮力感染者", "披覆重甲的中型突击单位。"),
            ("精英感染者", "精英感染者", "装甲、迅捷或狂暴词缀单位。"),
            ("首领召唤体", "首领召唤体", "由首领召唤的干扰单位。"),
            ("首领猫王", "首领猫王", "各战区的高威胁首领目标。"),
        ]
    card_w, card_h = 370, 90
    start_x, start_y = 125, 188
    for index, (key, name, desc) in enumerate(entries):
        x = start_x + (index % 2) * (card_w + 42)
        y = start_y + (index // 2) * (card_h + 14)
        rect = pygame.Rect(x, y, card_w, card_h)
        unlocked = key in (profile["achievements"] if page_kind == "achievement" else profile["codex"])
        edge = UI_CYAN if unlocked else (72, 78, 76)
        fill = (20, 46, 44) if unlocked else (28, 31, 30)
        draw_wasteland_panel(rect, edge, fill, 2)
        status = "已完成" if page_kind == "achievement" and unlocked else ("已记录" if unlocked else "未解锁")
        status_color = UI_CYAN if unlocked else BTN_LOCKED_TEXT
        name_t = font_menu_small.render(name, True, WHITE if unlocked else LIGHT_GRAY)
        screen.blit(name_t, (x + 20, y + 18))
        status_t = font_small.render(status, True, status_color)
        screen.blit(status_t, status_t.get_rect(topright=(x + card_w - 18, y + 20)))
        desc_t = fit_text(desc, UI_TEXT_DIM if unlocked else BTN_LOCKED_TEXT, card_w - 40, 15)
        screen.blit(desc_t, (x + 20, y + 53))
    return back_rect


def draw_material_icon(surface, key, center, size=14):
    """Draw a polished material sprite, retaining geometry as a safe fallback."""
    if key in MATERIAL_ICON_SPRITES:
        dimension = max(26, int(size * 2.4))
        cache_key = (key, dimension)
        if cache_key not in MATERIAL_ICON_CACHE:
            MATERIAL_ICON_CACHE[cache_key] = pygame.transform.smoothscale(
                MATERIAL_ICON_SPRITES[key], (dimension, dimension)
            )
        icon = MATERIAL_ICON_CACHE[cache_key]
        surface.blit(icon, icon.get_rect(center=center))
        return
    color = MATERIAL_INFO[key][1]
    x, y = center
    if key == "alloy":
        pygame.draw.polygon(surface, color, [(x, y-size), (x+size, y-5), (x+10, y+size), (x-10, y+size), (x-size, y-5)])
        pygame.draw.polygon(surface, (55, 66, 72), [(x, y-7), (x+7, y-2), (x+4, y+7), (x-5, y+7), (x-7, y-2)])
    elif key == "energy":
        pygame.draw.circle(surface, color, (x, y), size)
        pygame.draw.circle(surface, WHITE, (x, y), max(3, size // 3))
        pygame.draw.circle(surface, (24, 70, 82), (x, y), size, 2)
    else:
        pygame.draw.ellipse(surface, color, (x-size, y-size, size*2, size*2))
        pygame.draw.line(surface, (25, 95, 42), (x, y-size+3), (x, y+size-3), 3)


def draw_progression_page(profile, page_kind, equipped_weapon, mouse):
    if MENU_COMMAND_BG:
        screen.blit(MENU_COMMAND_BG, (0, 0))
    else:
        screen.fill(UI_VOID)
    veil = pygame.Surface((W, H), pygame.SRCALPHA)
    veil.fill((4, 8, 8, 188))
    screen.blit(veil, (0, 0))
    panel = pygame.Rect(110, 65, 780, 570)
    draw_wasteland_panel(panel, UI_CYAN if page_kind == "weapon_lab" else UI_AMBER, (12, 19, 19), 4)
    title = "武器改造台" if page_kind == "weapon_lab" else "生存者天赋"
    title_t = font_menu_large.render(title, True, UI_CYAN if page_kind == "weapon_lab" else UI_AMBER)
    screen.blit(title_t, title_t.get_rect(center=(W // 2, 108)))
    back = pygame.Rect(735, 87, 120, 44)
    draw_wasteland_button(back, "返回", mouse, True, font_menu_small)

    # Inventory strip.
    for index, key in enumerate(("alloy", "energy", "bio")):
        x = 245 + index * 220
        draw_material_icon(screen, key, (x, 164), 13)
        txt = font_small.render(f"{MATERIAL_INFO[key][0]} × {profile['materials'][key]}", True, WHITE)
        screen.blit(txt, (x + 22, 153))

    if page_kind == "weapon_lab":
        weapon = equipped_weapon
        levels = profile["weapon_upgrades"][weapon]
        material = WEAPON_MATERIAL[weapon]
        header = font_menu_mid.render(f"当前武器：{WEAPON_CONFIG[weapon]['name']}  ·  专用材料：{MATERIAL_INFO[material][0]}", True, WHITE)
        screen.blit(header, header.get_rect(center=(W // 2, 215)))
        rows = [
            ("damage", "基础攻击", "每级基础伤害 +1"),
            ("mag", "基础弹匣", "每级弹匣容量 +2"),
            ("durability", "武器耐久", "每级装填时间缩短 5%"),
        ]
    else:
        levels = profile["talents"]
        rows = [
            ("hp", "强健体魄", "每级基础生命值 +10", "bio"),
            ("speed", "机动训练", "每级基础移速 +0.15", "energy"),
            ("armor", "防护训练", "每级接触伤害减免 +1", "alloy"),
        ]

    buttons = []
    max_level = 5 if page_kind == "weapon_lab" else 10
    for index, row in enumerate(rows):
        key, name, desc = row[:3]
        material = material if page_kind == "weapon_lab" else row[3]
        level = levels[key]
        cost = 2 + level
        y = 260 + index * 105
        rect = pygame.Rect(175, y, 650, 82)
        draw_wasteland_panel(rect, MATERIAL_INFO[material][1], (24, 31, 31), 2)
        name_t = font_menu_small.render(f"{name}  Lv.{level}/{max_level}", True, WHITE)
        screen.blit(name_t, (198, y + 14))
        desc_t = font_small.render(desc, True, UI_TEXT_DIM)
        screen.blit(desc_t, (198, y + 48))
        upgrade_rect = pygame.Rect(650, y + 17, 150, 48)
        can_buy = level < max_level and profile["materials"][material] >= cost
        label = "已满级" if level >= max_level else f"升级 ×{cost}"
        draw_wasteland_button(upgrade_rect, label, mouse, can_buy, font_menu_small)
        buttons.append((upgrade_rect, key, material, cost))
    return buttons, back

# Original Victory Popup Modal
def draw_win_pop(next_exist, profile, gained):
    overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    screen.blit(overlay, (0, 0))
    box_w, box_h = 700, 480
    bx = (W - box_w) // 2
    by = (H - box_h) // 2
    rect = pygame.Rect(bx, by, box_w, box_h)
    draw_wasteland_panel(rect, UI_AMBER, (22, 42, 34), 4)
    win_t = font_menu_large.render("区域已净化", True, UI_AMBER)
    screen.blit(win_t, win_t.get_rect(center=(W // 2, by + 48)))
    desc = fit_text("作战目标已完成，等待下一条指令。", WHITE, box_w - 50, 26)
    screen.blit(desc, desc.get_rect(center=(W // 2, by + 96)))
    reward_t = font_menu_small.render("本次行动材料", True, UI_CYAN)
    screen.blit(reward_t, reward_t.get_rect(center=(W // 2, by + 138)))
    reward_card_w, reward_gap = 188, 14
    reward_start_x = bx + (box_w - (reward_card_w * 3 + reward_gap * 2)) // 2
    for index, key in enumerate(("alloy", "energy", "bio")):
        card_x = reward_start_x + index * (reward_card_w + reward_gap)
        draw_material_icon(screen, key, (card_x + 27, by + 178), 12)
        gained_t = font_menu_small.render(f"+{gained.get(key, 0)}", True, WHITE)
        owned_t = font_card_desc.render(f"持有 {profile['materials'][key]}", True, UI_TEXT_DIM)
        screen.blit(gained_t, (card_x + 52, by + 158))
        screen.blit(owned_t, (card_x + 52, by + 184))
    btn_w, btn_h = 250, 62
    gap = 30
    total_btn = btn_w * 2 + gap
    sx = (W - total_btn) // 2
    sy = by + 225
    btns = []
    menu_rect = pygame.Rect(sx, sy, btn_w, btn_h)
    btns.append((menu_rect, "menu"))
    mx, my = pygame.mouse.get_pos()
    draw_wasteland_button(menu_rect, "返回终端", (mx, my), True, font_menu_mid)
    nx = sx + btn_w + gap
    next_rect = pygame.Rect(nx, sy, btn_w, btn_h)
    btns.append((next_rect, "next"))
    draw_wasteland_button(next_rect, "进入下一战区", (mx, my), next_exist, font_menu_mid)
    talent_rect = pygame.Rect(sx, sy + 82, btn_w, btn_h)
    weapon_lab_rect = pygame.Rect(nx, sy + 82, btn_w, btn_h)
    btns.append((talent_rect, "talents"))
    btns.append((weapon_lab_rect, "weapon_lab"))
    draw_wasteland_button(talent_rect, "天赋升级", (mx, my), True, font_menu_mid)
    draw_wasteland_button(weapon_lab_rect, "武器改造", (mx, my), True, font_menu_mid)
    return btns

# Original Game Over Modal Window
def draw_game_over_pop():
    overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    screen.blit(overlay, (0, 0))
    box_w, box_h = 600, 320
    bx = (W - box_w) // 2
    by = (H - box_h) // 2
    rect = pygame.Rect(bx, by, box_w, box_h)
    draw_wasteland_panel(rect, (226, 62, 45), (55, 18, 18), 4)
    over_t = font_menu_large.render("信号中断", True, (255, 92, 70))
    screen.blit(over_t, over_t.get_rect(center=(W // 2, by + 60)))
    desc = fit_text("作战员失去行动能力。按 G 重整，按 H 返回终端。", WHITE, box_w - 50, 26)
    screen.blit(desc, desc.get_rect(center=(W // 2, by + 120)))
    btn_w, btn_h = 220, 70
    gap = 40
    total_btn = btn_w * 2 + gap
    sx = (W - total_btn) // 2
    sy = by + 180
    btns = []
    restart_rect = pygame.Rect(sx, sy, btn_w, btn_h)
    btns.append((restart_rect, "restart"))
    menu_rect = pygame.Rect(sx + btn_w + gap, sy, btn_w, btn_h)
    btns.append((menu_rect, "menu"))
    mx, my = pygame.mouse.get_pos()
    draw_wasteland_button(restart_rect, "重新整备（G）", (mx, my), True, font_menu_mid)
    draw_wasteland_button(menu_rect, "返回终端（H）", (mx, my), True, font_menu_mid)
    return btns

# Reset All Stage Data Function
def reset_stage(st_num, max_unlock, gold, owned, equip):
    pl = Player(equip)
    bullets = []
    enemies = []
    mini = []
    boss = None
    spawn_t = 0
    game_over = False
    kill_cnt = 0
    particles = []
    damage_popups = []
    score = 0
    up_cards = []
    refresh_left = 2
    return {
        "player": pl, "bullets": bullets, "enemies": enemies, "mini": mini, "mines": [],
        "boss": boss, "spawn_t": spawn_t, "game_over": game_over,
        "kill_cnt": kill_cnt, "particles": particles, "damage_popups": damage_popups,
        "focus_target": None, "focus_timer": 0, "score": score,
        "up_cards": up_cards, "refresh_left": refresh_left, "upgrade_intro_timer": 0,
        # Experience starts quickly, then asks for more blocks each level.
        "xp": 0, "xp_need": 5, "upgrade_level": 0,
        "boss_defeated": False, "boss_spawned": False,
        "normal_spawned": 0, "normal_kills": 0,
        "combo": 0, "combo_timer": 0,
        "achievement_notice": "", "achievement_notice_desc": "", "achievement_notice_timer": 0,
        "boss_buff_timer": 0, "boss_buff_notice": "", "boss_buff_notice_timer": 0,
        "materials_gained": {"alloy": 0, "energy": 0, "bio": 0},
        "preboss_upgrades_left": 5, "preboss_upgrade_sequence": False,
        "boss_alert_timer": 0,
    }


def draw_game_background(stage):
    base = STAGE_BG_COLORS[stage - 1]
    accent = STAGE_GROUND_ACCENTS[stage - 1]
    if BATTLEFIELD_CITY_BG:
        # The illustrated overhead city is intentionally distinct from the
        # command-menu background.  A restrained stage tint preserves clear
        # enemy, bullet and HUD visibility across all ten zones.
        screen.blit(BATTLEFIELD_CITY_BG, (0, 0))
        stage_tint = pygame.Surface((W, H), pygame.SRCALPHA)
        stage_tint.fill((*base, 54))
        screen.blit(stage_tint, (0, 0))
        # Fine tactical corner marks provide motion and stage identity without
        # laying old road rectangles over the illustrated city background.
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        edge = (*accent, 92)
        for x, y, sx, sy in ((26, 26, 1, 1), (W - 26, 26, -1, 1), (26, H - 26, 1, -1), (W - 26, H - 26, -1, -1)):
            pygame.draw.line(overlay, edge, (x, y), (x + sx * 52, y), 2)
            pygame.draw.line(overlay, edge, (x, y), (x, y + sy * 52), 2)
        screen.blit(overlay, (0, 0))
        vignette = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.rect(vignette, (0, 0, 0, 42), vignette.get_rect(), 16)
        screen.blit(vignette, (0, 0))
        return
    else:
        screen.fill(base)

    ground = pygame.Surface((W, H), pygame.SRCALPHA)
    # Broken tar, oil stains and cracks add texture without producing a grid.
    detail_step = 36
    detail_x = -int(CAMERA_X) % detail_step - detail_step
    detail_y = -int(CAMERA_Y) % detail_step - detail_step
    for sy in range(detail_y, H + detail_step, detail_step):
        world_y = int(CAMERA_Y + sy)
        for sx in range(detail_x, W + detail_step, detail_step):
            world_x = int(CAMERA_X + sx)
            seed = ((world_x // detail_step) * 92821 + (world_y // detail_step) * 68917) & 0xFFFF
            if seed % 4 == 0:
                width = 8 + seed % 22
                pygame.draw.ellipse(ground, (4, 6, 7, 58), (sx - width // 2, sy - 4, width, 8))
            if seed % 9 == 0:
                crack = [(sx - 13, sy - 6), (sx - 3, sy - 2), (sx + 4, sy - 8), (sx + 14, sy - 3)]
                pygame.draw.lines(ground, (8, 10, 10, 145), False, crack, 2)
            if seed % 13 == 0:
                pygame.draw.rect(ground, (*accent, 38), (sx - 4, sy - 9, 8, 18))
    # Broad worn transport lanes break up the surface without obscuring play.
    for lane_x in (480, 1200, 2000, 2800, 3600):
        sx, _ = world_to_screen(lane_x, 0)
        pygame.draw.rect(ground, (9, 12, 13, 118), (int(sx - 74), 0, 148, H))
        pygame.draw.line(ground, (*accent, 70), (int(sx - 74), 0), (int(sx - 74), H), 2)
        pygame.draw.line(ground, (*accent, 55), (int(sx + 74), 0), (int(sx + 74), H), 2)
        dash_y = -int(CAMERA_Y) % 110 - 65
        while dash_y < H:
            pygame.draw.rect(ground, (180, 155, 92, 45), (int(sx - 3), dash_y, 6, 36))
            dash_y += 110
    for lane_y in (600, 1300, 2100):
        _, sy = world_to_screen(0, lane_y)
        pygame.draw.rect(ground, (9, 12, 13, 100), (0, int(sy - 62), W, 124))
        pygame.draw.line(ground, (*accent, 55), (0, int(sy - 62)), (W, int(sy - 62)), 2)
        pygame.draw.line(ground, (*accent, 42), (0, int(sy + 62)), (W, int(sy + 62)), 2)

    # Static wreckage and blast scars provide landmarks across the large map.
    for x, y, rw, rh in BATTLEFIELD_DEBRIS:
        sx, sy = world_to_screen(x, y)
        if -80 < sx < W + 80 and -80 < sy < H + 80:
            pygame.draw.ellipse(ground, (4, 6, 7, 145), (int(sx - rw), int(sy - rh), rw * 2, rh * 2))
            pygame.draw.rect(ground, (*accent, 105), (int(sx - rw // 2), int(sy - rh // 3), rw, max(4, rh // 2)))
            pygame.draw.line(ground, (195, 102, 55, 105), (int(sx - rw // 2), int(sy - rh // 3)), (int(sx + rw // 2), int(sy + rh // 3)), 2)
    # Stage-specific signal beacons give the arena a deliberately designed
    # command-zone look, without reusing the homepage artwork.
    pulse = 0.55 + 0.45 * math.sin(pygame.time.get_ticks() * 0.002 + stage)
    for idx, (wx, wy, size) in enumerate(BACKGROUND_TRIANGLES):
        sx, sy = world_to_screen(wx, wy)
        if -size < sx < W + size and -size < sy < H + size:
            alpha = int((18 + 18 * pulse) if idx % 2 == stage % 2 else 13)
            pts = [(int(sx), int(sy - size)), (int(sx - size * .82), int(sy + size * .65)), (int(sx + size * .82), int(sy + size * .65))]
            pygame.draw.polygon(ground, (*accent, alpha), pts)
            pygame.draw.polygon(ground, (*accent, min(95, alpha * 3)), pts, 2)
    for wx, wy, scale in BACKGROUND_CLOUDS:
        sx, sy = world_to_screen(wx, wy)
        if -160 < sx < W + 160 and -120 < sy < H + 120:
            cloud_w, cloud_h = int(135 * scale), int(26 * scale)
            pygame.draw.ellipse(ground, (*accent, 16), (int(sx - cloud_w / 2), int(sy - cloud_h / 2), cloud_w, cloud_h))
    screen.blit(ground, (0, 0))

    # A subtle vignette pushes attention toward the active combat space.
    vignette = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.rect(vignette, (0, 0, 0, 42), vignette.get_rect(), 16)
    screen.blit(vignette, (0, 0))


def draw_hud(player, stage, normal_kills, normal_total, boss_spawned, score, xp, xp_need, upgrade_level, combo=0):
    max_hp = player.calc_max_hp()
    status_rect = pygame.Rect(14, 14, 300, 76)
    draw_wasteland_panel(status_rect, UI_CYAN, (16, 25, 25), 2)
    label = font_small.render("生命状态", True, UI_TEXT_DIM)
    screen.blit(label, (30, 27))
    bar_rect = pygame.Rect(30, 50, 248, 16)
    pygame.draw.rect(screen, (72, 28, 24), bar_rect)
    pygame.draw.rect(screen, (76, 213, 138), (bar_rect.x, bar_rect.y, int(bar_rect.width * max(0, player.hp) / max_hp), bar_rect.height))
    pygame.draw.rect(screen, UI_AMBER, bar_rect, 1)
    hp_text = font_small.render(f"{max(0, int(player.hp))} / {max_hp}", True, WHITE)
    screen.blit(hp_text, hp_text.get_rect(midright=(278, 35)))
    cfg = WEAPON_CONFIG[player.current_weapon]
    ammo = "装填中" if player.is_reloading else f"弹药：{player.current_mag}/{player.calc_mag(cfg['mag_cap'])}"
    ammo_rect = pygame.Rect(14, H - 60, 360, 46)
    draw_wasteland_panel(ammo_rect, UI_ORANGE, (16, 25, 25), 2)
    info = font_small.render(f"装备：{cfg['name']}  |  {ammo}", True, WHITE)
    screen.blit(info, info.get_rect(midleft=(30, H - 37)))
    xp_rect = pygame.Rect(388, H - 60, 300, 46)
    draw_wasteland_panel(xp_rect, UI_CYAN, (16, 25, 25), 2)
    xp_label = font_small.render(f"战术等级 {upgrade_level + 1}  |  经验块 {xp}/{xp_need}", True, WHITE)
    screen.blit(xp_label, xp_label.get_rect(midleft=(404, H - 38)))
    xp_bar = pygame.Rect(404, H - 24, 266, 6)
    pygame.draw.rect(screen, (28, 48, 48), xp_bar)
    pygame.draw.rect(screen, UI_CYAN, (xp_bar.x, xp_bar.y, int(xp_bar.width * min(1, xp / xp_need)), xp_bar.height))
    if boss_spawned:
        stage_label = f"战区 {stage:02d}  |  首领威胁：清除猫王  |  战绩：{score}"
    else:
        stage_label = f"战区 {stage:02d}  |  威胁清除：{normal_kills}/{normal_total}  |  战绩：{score}"
    mission_rect = pygame.Rect(W - 405, 14, 390, 48)
    draw_wasteland_panel(mission_rect, UI_ORANGE, (16, 25, 25), 2)
    stage_text = fit_text(stage_label, WHITE, mission_rect.width - 28, 18)
    screen.blit(stage_text, stage_text.get_rect(center=mission_rect.center))
    if combo >= 2:
        multiplier = 1 + min(2, combo // 10)
        combo_text = font_menu_small.render(f"连杀 ×{combo}   积分倍率 ×{multiplier}", True, UI_AMBER)
        screen.blit(combo_text, combo_text.get_rect(midbottom=(W // 2, H - 18)))


def draw_achievement_toast(title, desc, timer):
    """Slide an achievement badge down from the combat HUD's top edge."""
    total, edge = 180, 18
    if timer > total - edge:
        progress = (total - timer) / edge
    elif timer < edge:
        progress = timer / edge
    else:
        progress = 1.0
    progress = max(0.0, min(1.0, progress))
    box_w, box_h = 430, 94
    x = W // 2 - box_w // 2
    y = int(-box_h + (16 + box_h) * (progress * progress * (3 - 2 * progress)))
    rect = pygame.Rect(x, y, box_w, box_h)
    draw_wasteland_panel(rect, UI_AMBER, (24, 29, 24), 3)
    # An in-game badge icon: a shield, star, and ribbon rather than text alone.
    icon_x, icon_y = x + 48, y + 47
    pygame.draw.polygon(screen, (53, 94, 100), [(icon_x, icon_y - 28), (icon_x + 24, icon_y - 16), (icon_x + 18, icon_y + 22), (icon_x, icon_y + 32), (icon_x - 18, icon_y + 22), (icon_x - 24, icon_y - 16)])
    pygame.draw.polygon(screen, UI_AMBER, [(icon_x, icon_y - 17), (icon_x + 6, icon_y - 5), (icon_x + 19, icon_y - 3), (icon_x + 9, icon_y + 6), (icon_x + 12, icon_y + 19), (icon_x, icon_y + 11), (icon_x - 12, icon_y + 19), (icon_x - 9, icon_y + 6), (icon_x - 19, icon_y - 3), (icon_x - 6, icon_y - 5)])
    heading = font_small.render("成就解锁", True, UI_CYAN)
    name = font_menu_small.render(title, True, WHITE)
    detail = fit_text(desc, UI_TEXT_DIM, box_w - 110, 16)
    screen.blit(heading, (x + 92, y + 14))
    screen.blit(name, (x + 92, y + 34))
    screen.blit(detail, (x + 92, y + 63))


def hit_target(target, damage, particles, damage_popups, focus_state):
    global HIT_SHAKE_TIMER, HIT_SHAKE_POWER
    target.hp -= damage
    defeated = target.hp <= 0
    target.hit_flash = 8 if defeated else 6
    burst = 20 if defeated else 10
    if IS_WEB:
        burst = max(4, int(burst * 0.60))
    impact_colors = (WHITE, YELLOW, ORANGE_FLASH) if defeated else (YELLOW, ORANGE_FLASH)
    for _ in range(burst):
        particles.append(Particle(
            target.x, target.y, random.choice(impact_colors),
            2.4 if defeated else 1.3,
            random.randint(4, 8) if defeated else random.randint(3, 6),
            random.randint(22, 34),
        ))
    emphasized = defeated or focus_state["timer"] <= 0
    popup_color = (255, 132, 58) if defeated else (255, 224, 82)
    damage_popups.append(DamagePopup(target.x, target.y, damage, emphasized, popup_color))
    if emphasized:
        HIT_SHAKE_TIMER = max(HIT_SHAKE_TIMER, 10 if defeated else 5)
        HIT_SHAKE_POWER = max(HIT_SHAKE_POWER, 8.0 if defeated else min(5.0, 2.2 + damage * 0.035))
    # The short focus pulse is throttled so high-rate weapons remain readable.
    if emphasized:
        focus_state["target"] = target
        focus_state["timer"] = 10
    return defeated


def draw_hit_focus(target, timer):
    """Give a successful hit a compact, screen-space close-up without moving the camera."""
    if target is None or timer <= 0:
        return
    sx, sy = world_to_screen(target.x, target.y)
    if not (-120 < sx < W + 120 and -120 < sy < H + 120):
        return
    progress = timer / 10
    pulse_r = int(getattr(target, "r", 18) * (1.55 + (1 - progress) * 0.4))
    ring = pygame.Surface((pulse_r * 2 + 12, pulse_r * 2 + 12), pygame.SRCALPHA)
    pygame.draw.circle(ring, (255, 207, 72, int(135 * progress)), ring.get_rect().center, pulse_r, 3)
    screen.blit(ring, ring.get_rect(center=(int(sx), int(sy))))

    if isinstance(target, BossCat):
        kind = "boss"
    elif isinstance(target, MiniCat):
        kind = "mini"
    else:
        kind = getattr(target, "type", "basic")
    sprite = directional_sprite(kind, getattr(target, "facing", math.pi / 2))
    if sprite:
        zoom = 1.18 + (1 - progress) * 0.20
        scaler = pygame.transform.scale if IS_WEB else pygame.transform.smoothscale
        enlarged = scaler(sprite, (int(sprite.get_width() * zoom), int(sprite.get_height() * zoom)))
        enlarged.set_alpha(int(190 * progress))
        screen.blit(enlarged, enlarged.get_rect(center=(int(sx), int(sy))))
    else:
        pygame.draw.circle(screen, (255, 222, 90), (int(sx), int(sy)), max(4, int(getattr(target, "r", 12) * 1.2)), 2)


async def run_game(test_mode=False):
    global gold_total, mini_enemies, CAMERA_X, CAMERA_Y, UI_MOUSE_DOWN, ACTIVE_PROFILE
    gold_total = 0
    owned_weapons = set(ALL_WEAPON_LIST) if test_mode else {"pistol"}
    equipped_weapon = "pistol"
    max_unlocked = len(STAGE_LIVE_LIMIT) if test_mode else 1
    pygame.display.set_caption("测试版枪战游戏" if test_mode else "枪战游戏")
    stage = 1
    state = "menu"
    world = None
    # Session records are deliberately kept outside a stage reset: the player
    # can build an encyclopedia and achievement count across the whole run.
    profile = {
        "codex": set(), "achievements": set(),
        "materials": {"alloy": 99 if test_mode else 0, "energy": 99 if test_mode else 0, "bio": 99 if test_mode else 0},
        "talents": {"hp": 0, "speed": 0, "armor": 0},
        "weapon_upgrades": {weapon: {"damage": 0, "mag": 0, "durability": 0} for weapon in ALL_WEAPON_LIST},
    }
    ACTIVE_PROFILE = profile
    menu_controls = ([], {})
    collection_back = None
    progression_controls = ([], None)
    progression_return_state = "win"
    shop_controls = ([], None)
    select_controls = ([], None)
    upgrade_controls = ([], None)
    win_controls = []
    over_controls = []
    running = True
    # Event-based tracking is reliable on macOS even when get_pressed() does
    # not report a held mouse button to Pygame.
    mouse_fire_held = False
    fire_pressed_this_frame = False
    UI_MOUSE_DOWN = False

    def unlock_achievement(key, title):
        if key in profile["achievements"]:
            return
        profile["achievements"].add(key)
        if world is not None:
            notice_title, notice_desc = ACHIEVEMENT_DETAILS.get(key, (title, "完成一项战术行动成就。"))
            world["achievement_notice"] = notice_title
            world["achievement_notice_desc"] = notice_desc
            world["achievement_notice_timer"] = 180

    def hurt_player(amount, contact=False):
        """Apply player damage while respecting the small defensive perks."""
        player = world["player"]
        if player.shield_timer > 0:
            return
        if contact:
            amount = max(1, amount - player.armor)
        if player.shield_ready and player.hp - amount <= 35:
            player.shield_ready = False
            player.shield_timer = 120
            return
        player.hp -= amount
        player.hit_flash = 8
        world["damage_popups"].append(DamagePopup(player.x, player.y, amount, True, (255, 78, 78)))
        # Clear local hit feedback: a short red flash already tints the
        # survivor sprite; these particles make the impact readable even
        # when the player is moving at speed during a roll.
        for _ in range(12):
            world["particles"].append(Particle(player.x, player.y, (255, 72, 72), 1.0))
        player.ration_timer = 0

    def damage_target(target, target_group, damage):
        """Apply damage and grant the standard reward when a target dies."""
        global gold_total
        focus_state = {"target": world["focus_target"], "timer": world["focus_timer"]}
        defeated = hit_target(target, damage, world["particles"], world["damage_popups"], focus_state)
        world["focus_target"] = focus_state["target"]
        world["focus_timer"] = focus_state["timer"]
        if not defeated:
            return
        reward_score = 0
        xp_gain = 1
        if target_group == "normal":
            world["enemies"].remove(target)
            world["normal_kills"] += 1
            reward_score = 10
            profile["codex"].add(getattr(target, "type", "普通感染者"))
            if getattr(target, "elite_affix", None):
                profile["codex"].add("精英感染者")
                unlock_achievement("first_elite", "精英清除者")
                xp_gain = 2
            elif getattr(target, "type", "") in ("fast", "tank"):
                xp_gain = 2
            # Small field drops keep materials valuable without flooding the
            # inventory.  Each stage has a primary resource identity.
            if random.random() < 0.16:
                material = STAGE_MATERIAL[stage - 1]
                profile["materials"][material] += 1
                world["materials_gained"][material] += 1
        elif target_group == "mini":
            world["mini"].remove(target)
            reward_score = 15
            xp_gain = 2
            profile["codex"].add("首领召唤体")
        else:
            if target.is_final_phase_one:
                phase_two = BossCat(5, phase=2)
                phase_two.x, phase_two.y = target.x, target.y
                world["boss"] = phase_two
                world["boss_buff_notice"] = "最终首领：第二阶段"
                world["boss_buff_notice_timer"] = 150
                profile["codex"].add("最终首领第一阶段")
                return
            world["boss"] = None
            world["boss_defeated"] = True
            reward_score = 500
            xp_gain = 2
            profile["codex"].add("首领猫王")
            unlock_achievement("boss_hunter", "首领猎手")
            material = STAGE_MATERIAL[stage - 1]
            amount = 2 + stage // 3
            profile["materials"][material] += amount
            world["materials_gained"][material] += amount
        world["kill_cnt"] += 1
        world["xp"] += xp_gain
        world["combo"] += 1
        world["combo_timer"] = 180
        multiplier = 1 + min(2, world["combo"] // 10)
        world["score"] += reward_score * multiplier
        if world["combo"] >= 10:
            unlock_achievement("combo_10", "十连清除")
        if world["normal_kills"] >= STAGE_KILL_QUOTA[stage - 1]:
            unlock_achievement("stage_sweeper", "战区清扫者")
        gold_total += 1
        player = world["player"]
        player.kill_counter += 1
        # This recovery module is kill-based, not hit-based: beam weapons can
        # no longer refill the player simply by keeping a laser on one target.
        if (player.kill_leech_enabled and player.kill_counter % 5 == 0
                and random.random() < 0.50):
            player.hp = min(player.calc_max_hp(), player.hp + 10)
        if player.auto_loader and player.kill_counter % 8 == 0:
            player.current_mag = min(player.calc_mag(WEAPON_CONFIG[player.current_weapon]["mag_cap"]), player.current_mag + 2)
        if player.coin_finder and player.kill_counter % 5 == 0:
            gold_total += 2
        if player.scavenge and random.random() < 0.15:
            player.current_mag = min(player.calc_mag(WEAPON_CONFIG[player.current_weapon]["mag_cap"]), player.current_mag + 2)
        if player.field_medic and target_group == "normal" and getattr(target, "type", "") == "tank":
            player.hp = min(player.calc_max_hp(), player.hp + 5)
        if player.time_ripple and player.kill_counter % 10 == 0:
            for enemy in world["enemies"] + world["mini"]:
                enemy.slow_timer = max(enemy.slow_timer, 180)
            if world["boss"]:
                world["boss"].slow_timer = max(world["boss"].slow_timer, 120)

    while running:
        clock.tick(TARGET_FPS)
        update_hit_shake()
        mouse = pygame.mouse.get_pos()
        fire_pressed_this_frame = False
        for event in pygame.event.get():
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Safari requires audio to be unlocked by a genuine click.
                ensure_audio_ready()
                # Preserve a quick single click even if the operating system
                # sends its matching release event in the same frame.
                if state == "play":
                    fire_pressed_this_frame = True
                else:
                    play_ui_button_sound()
                mouse_fire_held = True
                UI_MOUSE_DOWN = True
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                mouse_fire_held = False
                UI_MOUSE_DOWN = False
            elif event.type == pygame.MOUSEMOTION:
                # Motion events carry the reliable button state on macOS while
                # dragging, so held fire cannot silently drop out.
                mouse_fire_held = bool(event.buttons[0])
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if state == "play" and event.key == pygame.K_ESCAPE:
                    state = "menu"
                elif state == "gameover" and event.key == pygame.K_g:
                    world = reset_stage(stage, max_unlocked, gold_total, owned_weapons, equipped_weapon)
                    mini_enemies = world["mini"]
                    state = "play"
                elif state == "gameover" and event.key == pygame.K_h:
                    state = "menu"
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if state == "menu":
                    stage_btns, operation_rects = menu_controls
                    if operation_rects.get("weapons") and operation_rects["weapons"].collidepoint(event.pos):
                        state = "weapons"
                    elif operation_rects.get("shop") and operation_rects["shop"].collidepoint(event.pos):
                        state = "shop"
                    elif operation_rects.get("talents") and operation_rects["talents"].collidepoint(event.pos):
                        progression_return_state = "menu"
                        state = "talents"
                    elif operation_rects.get("weapon_lab") and operation_rects["weapon_lab"].collidepoint(event.pos):
                        progression_return_state = "menu"
                        state = "weapon_lab"
                    elif operation_rects.get("achievement") and operation_rects["achievement"].collidepoint(event.pos):
                        state = "achievement"
                    elif operation_rects.get("codex") and operation_rects["codex"].collidepoint(event.pos):
                        state = "codex"
                    elif operation_rects.get("quit") and operation_rects["quit"].collidepoint(event.pos):
                        running = False
                    else:
                        for rect, choice in stage_btns:
                            if rect.collidepoint(event.pos) and choice <= max_unlocked:
                                stage = choice
                                world = reset_stage(stage, max_unlocked, gold_total, owned_weapons, equipped_weapon)
                                mini_enemies = world["mini"]
                                state = "play"
                elif state == "shop":
                    btns, back = shop_controls
                    if back.collidepoint(event.pos):
                        state = "menu"
                    else:
                        for rect, weapon in btns:
                            cost = WEAPON_CONFIG[weapon]["cost"]
                            if rect.collidepoint(event.pos) and weapon not in owned_weapons and gold_total >= cost:
                                gold_total -= cost
                                owned_weapons.add(weapon)
                elif state == "weapons":
                    btns, back = select_controls
                    if back.collidepoint(event.pos):
                        state = "menu"
                    else:
                        for rect, weapon in btns:
                            if rect.collidepoint(event.pos) and weapon in owned_weapons:
                                equipped_weapon = weapon
                elif state in ("achievement", "codex"):
                    if collection_back and collection_back.collidepoint(event.pos):
                        state = "menu"
                elif state in ("talents", "weapon_lab"):
                    buttons, back = progression_controls
                    if back and back.collidepoint(event.pos):
                        state = progression_return_state
                    else:
                        levels = profile["talents"] if state == "talents" else profile["weapon_upgrades"][equipped_weapon]
                        for rect, key, material, cost in buttons:
                            max_level = 10 if state == "talents" else 5
                            if rect.collidepoint(event.pos) and levels[key] < max_level and profile["materials"][material] >= cost:
                                profile["materials"][material] -= cost
                                levels[key] += 1
                                break
                elif state == "upgrade":
                    cards, refresh = upgrade_controls
                    if world["upgrade_intro_timer"] > 0:
                        continue
                    if refresh.collidepoint(event.pos) and world["refresh_left"] > 0:
                        world["refresh_left"] -= 1
                        world["up_cards"] = generate_upgrade_cards(world["player"])
                        world["upgrade_intro_timer"] = 30 if all(perk["func"].startswith("weapon_ultimate_") for perk in world["up_cards"]) else 16
                    else:
                        for rect, perk in cards:
                            if rect.collidepoint(event.pos):
                                world["player"].apply_upgrade(perk)
                                if world["preboss_upgrade_sequence"]:
                                    world["preboss_upgrades_left"] -= 1
                                    if world["preboss_upgrades_left"] > 0:
                                        world["up_cards"] = generate_upgrade_cards(world["player"])
                                        world["refresh_left"] = 2
                                        world["upgrade_intro_timer"] = 30 if all(perk["func"].startswith("weapon_ultimate_") for perk in world["up_cards"]) else 16
                                    else:
                                        world["preboss_upgrade_sequence"] = False
                                        state = "play"
                                else:
                                    state = "play"
                                break
                elif state == "win":
                    for rect, action in win_controls:
                        if rect.collidepoint(event.pos):
                            if action == "menu":
                                state = "menu"
                            elif action in ("talents", "weapon_lab"):
                                progression_return_state = "win"
                                state = action
                            elif action == "next" and stage < len(STAGE_LIVE_LIMIT):
                                stage += 1
                                world = reset_stage(stage, max_unlocked, gold_total, owned_weapons, equipped_weapon)
                                mini_enemies = world["mini"]
                                state = "play"
                elif state == "gameover":
                    for rect, action in over_controls:
                        if rect.collidepoint(event.pos):
                            if action == "restart":
                                world = reset_stage(stage, max_unlocked, gold_total, owned_weapons, equipped_weapon)
                                mini_enemies = world["mini"]
                                state = "play"
                            else:
                                state = "menu"

        if state in ("win", "talents", "weapon_lab"):
            set_bgm("win")
        elif state == "gameover":
            set_bgm("gameover")
        elif world and state in ("play", "upgrade"):
            set_bgm("boss" if world["boss_spawned"] else "combat")
        else:
            set_bgm(None)

        if state == "upgrade" and world and world["upgrade_intro_timer"] > 0:
            world["upgrade_intro_timer"] -= 1

        if state == "play":
            player = world["player"]
            if world["focus_timer"] > 0:
                world["focus_timer"] -= 1
                if world["focus_timer"] == 0:
                    world["focus_target"] = None
            keys = pygame.key.get_pressed()
            update_camera(player)
            world_mouse = (mouse[0] + CAMERA_X, mouse[1] + CAMERA_Y)
            player.update(keys, *world_mouse, False)
            if world["boss"]:
                # The beam has no meaningful precision weak point: while a
                # laser is equipped, the exposed core is disabled for both
                # rendering and collision damage.
                world["boss"].weakpoint_suppressed = player.current_weapon == "laser"
            physical_left_held = bool(pygame.mouse.get_pressed(3)[0])
            if (fire_pressed_this_frame or mouse_fire_held or physical_left_held) and player.can_shoot(False):
                world["bullets"].extend(player.fire(*world_mouse))
            update_camera(player)

            # Every stage has a fixed number of normal enemies.  The boss only
            # appears after every one of those enemies has been defeated.
            normal_target = STAGE_KILL_QUOTA[stage - 1]
            if not world["boss_spawned"] and world["normal_spawned"] < normal_target:
                world["spawn_t"] += 1
                limits = STAGE_LIVE_LIMIT[stage - 1]
                live_limit = max(1, sum(limits.values()))
                if world["spawn_t"] >= NORMAL_SPAWN_INTERVAL and len(world["enemies"]) < live_limit:
                    world["spawn_t"] = 0
                    choices = [kind for kind, amount in limits.items() if amount] or ["basic"]
                    elite_affix = None
                    if stage >= 2 and random.random() < 0.12:
                        elite_affix = random.choice(("armored", "swift", "berserk"))
                    world["enemies"].append(NormalEnemy(
                        random.choice(choices), player.slow_enemy_mod, stage,
                        player.x, player.y, elite_affix,
                    ))
                    world["normal_spawned"] += 1
            elif (not world["boss_spawned"] and world["normal_kills"] >= normal_target
                  and not world["enemies"]):
                if stage == 5 and world["preboss_upgrades_left"] > 0:
                    world["preboss_upgrade_sequence"] = True
                    world["up_cards"] = generate_upgrade_cards(player)
                    world["refresh_left"] = 2
                    world["upgrade_intro_timer"] = 30 if all(perk["func"].startswith("weapon_ultimate_") for perk in world["up_cards"]) else 16
                    state = "upgrade"
                else:
                    world["boss"] = BossCat(stage, phase=1 if stage == 5 else 2, player_x=player.x, player_y=player.y)
                    world["boss_spawned"] = True
                    world["boss_alert_timer"] = 180
                    play_boss_alarm()

            for bullet in world["bullets"][:]:
                bullet.update()
                targets = ([(enemy, "normal") for enemy in world["enemies"]]
                           + [(enemy, "mini") for enemy in world["mini"]])
                if world["boss"]:
                    targets.append((world["boss"], "boss"))

                if bullet.weapon_key == "grenade":
                    impact = bullet.out() or any(
                        math.hypot(bullet.x - target.x, bullet.y - target.y) < target.r + bullet.radius
                        for target, _ in targets
                    )
                    if impact:
                        # The grenade damages every target in its explosion radius.
                        for target, group in targets:
                            if math.hypot(bullet.x - target.x, bullet.y - target.y) < target.r + bullet.explosion_radius:
                                damage_target(target, group, bullet.dmg_mod)
                        for _ in range(18):
                            world["particles"].append(Particle(bullet.x, bullet.y, ORANGE_FLASH, 2))
                        world["bullets"].remove(bullet)
                    continue

                consumed = bullet.out()
                for target, group in targets:
                    target_id = id(target)
                    hit_distance = (point_to_segment_distance(target.x, target.y, bullet.start_x, bullet.start_y, bullet.end_x, bullet.end_y)
                                    if bullet.is_beam else math.hypot(bullet.x - target.x, bullet.y - target.y))
                    if (not consumed and target_id not in bullet.hit_targets
                            and hit_distance < target.r + bullet.radius):
                        bullet.hit_targets.add(target_id)
                        hit_damage = bullet.dmg_mod
                        # Keep high sniper damage for normal enemies, but make
                        # boss fights take several well-timed shots instead of
                        # ending almost immediately.
                        if bullet.weapon_key == "sniper" and group == "boss":
                            hit_damage = max(1, int(hit_damage * 0.75))
                        if group == "boss" and target.weakpoint_active():
                            wx, wy = target.weakpoint_position()
                            weakpoint_distance = (
                                point_to_segment_distance(wx, wy, bullet.start_x, bullet.start_y, bullet.end_x, bullet.end_y)
                                if bullet.is_beam else math.hypot(bullet.x - wx, bullet.y - wy)
                            )
                            if weakpoint_distance < target.weakpoint_r + bullet.radius:
                                hit_damage = max(1, int(hit_damage * 1.8))
                                world["boss_buff_notice"] = "弱点命中：核心受创"
                                world["boss_buff_notice_timer"] = 36
                        damage_target(target, group, hit_damage)
                        if player.chill_chance and random.random() < player.chill_chance:
                            target.slow_timer = max(getattr(target, "slow_timer", 0), 120)
                        if player.push_chance and random.random() < player.push_chance:
                            dx, dy = target.x - player.x, target.y - player.y
                            distance = max(1, math.hypot(dx, dy))
                            target.x += dx / distance * 35
                            target.y += dy / distance * 35
                        # Each successful chain has its own 30% chance to jump
                        # again.  A fortunate shot can therefore travel across
                        # the entire battlefield, while an unlucky one stops
                        # immediately.
                        chain_source = target
                        chain_seen = {id(target)}
                        chain_damage = max(1, int(hit_damage * 0.50))
                        while player.chain_chance and random.random() < player.chain_chance:
                            candidates = [(other, other_group) for other, other_group in targets
                                          if id(other) not in chain_seen and other.hp > 0]
                            if not candidates:
                                break
                            chain_target, chain_group = min(
                                candidates,
                                key=lambda item: math.hypot(item[0].x - chain_source.x, item[0].y - chain_source.y),
                            )
                            chain_seen.add(id(chain_target))
                            damage_target(chain_target, chain_group, chain_damage)
                            chain_source = chain_target
                            chain_damage = max(1, int(chain_damage * 0.85))
                        bullet.pierce_left -= 1
                        if bullet.pierce_left <= 0:
                            consumed = True
                if consumed and bullet in world["bullets"]:
                    world["bullets"].remove(bullet)

            attackers = world["enemies"] + world["mini"]
            if world["boss"]:
                attackers.append(world["boss"])

            # Low-power utility upgrades run on long timers so they support a
            # build without replacing the player's weapon.
            if player.decoy_enabled:
                player.decoy_timer += 1
                if player.decoy_timer >= 8 * 60:
                    player.decoy_timer = 0
                    for enemy in world["enemies"] + world["mini"]:
                        if math.hypot(enemy.x - player.x, enemy.y - player.y) < 320:
                            enemy.slow_timer = max(enemy.slow_timer, 180)
            assist_targets = ([(enemy, "normal") for enemy in world["enemies"]]
                              + [(enemy, "mini") for enemy in world["mini"]]
                              + ([(world["boss"], "boss")] if world["boss"] else []))
            if player.drone_enabled:
                player.drone_timer += 1
                if player.drone_timer >= 2 * 60 and assist_targets:
                    player.drone_timer = 0
                    drone_target, drone_group = min(assist_targets, key=lambda item: math.hypot(item[0].x - player.x, item[0].y - player.y))
                    damage_target(drone_target, drone_group, 8)
            if player.mine_enabled:
                player.mine_timer += 1
                if player.mine_timer >= 5 * 60:
                    player.mine_timer = 0
                    world["mines"].append({"x": player.x, "y": player.y, "life": 180})
            for mine in world["mines"][:]:
                mine["life"] -= 1
                detonated = mine["life"] <= 0 or any(
                    math.hypot(target.x - mine["x"], target.y - mine["y"]) < target.r + 70
                    for target, _ in assist_targets
                )
                if detonated:
                    for mine_target, mine_group in assist_targets[:]:
                        if math.hypot(mine_target.x - mine["x"], mine_target.y - mine["y"]) < mine_target.r + 90:
                            damage_target(mine_target, mine_group, 24)
                    for _ in range(12):
                        world["particles"].append(Particle(mine["x"], mine["y"], ORANGE_FLASH, 1))
                    world["mines"].remove(mine)
            # An assist may have defeated an enemy, so use the fresh lists.
            attackers = world["enemies"] + world["mini"]
            if world["boss"]:
                attackers.append(world["boss"])
            for enemy in attackers:
                enemy.update(player.x, player.y)
                if isinstance(enemy, BossCat):
                    boss_distance = math.hypot(enemy.x - player.x, enemy.y - player.y)
                    # Boss auras apply while the player remains in their visible circles.
                    if enemy.has_ability("freeze") and boss_distance < enemy.freeze_radius:
                        player.apply_boss_effect("freeze")
                    if enemy.has_ability("burn") and boss_distance < enemy.burn_radius:
                        player.apply_boss_effect("burn")
                if (isinstance(enemy, BossCat) and enemy.shock_active > 0
                        and math.hypot(enemy.x - player.x, enemy.y - player.y) < 150):
                    if enemy.shock_hit_cd == 0:
                        hurt_player(6)
                        player.apply_boss_effect("shock")
                        enemy.shock_hit_cd = 45
                        if enemy.stage != 5:
                            enemy.shock_active = 0
                if math.hypot(enemy.x - player.x, enemy.y - player.y) < enemy.r + 15 and enemy.atk_cd == 0:
                    hurt_player(enemy.dmg, contact=True)
                    enemy.atk_cd = 35
            for particle in world["particles"][:]:
                particle.update()
                if particle.life <= 0:
                    world["particles"].remove(particle)
            if IS_WEB and len(world["particles"]) > 150:
                del world["particles"][:-150]
            for popup in world["damage_popups"][:]:
                popup.update()
                if popup.life <= 0:
                    world["damage_popups"].remove(popup)
            if IS_WEB and len(world["damage_popups"]) > 70:
                del world["damage_popups"][:-70]

            # A small assist in the final boss fight: grant one random common
            # upgrade every five seconds while the boss is alive.
            if stage == 5 and world["boss"] and not world["boss_defeated"]:
                world["boss_buff_timer"] += 1
                if world["boss_buff_timer"] >= 300:
                    world["boss_buff_timer"] = 0
                    common_perks = [perk for perk in UPGRADE_LIST if perk["tier"] == "普通"]
                    perk = random.choice(common_perks)
                    player.apply_upgrade(perk)
                    world["boss_buff_notice"] = f"首领援助：{perk['name']}"
                    world["boss_buff_notice_timer"] = 150
            if world["boss_buff_notice_timer"] > 0:
                world["boss_buff_notice_timer"] -= 1
            if world["achievement_notice_timer"] > 0:
                world["achievement_notice_timer"] -= 1
            if world["combo_timer"] > 0:
                world["combo_timer"] -= 1
            elif world["combo"]:
                world["combo"] = 0
            if world["boss_alert_timer"] > 0:
                world["boss_alert_timer"] -= 1

            if player.hp <= 0:
                state = "gameover"
            elif world["boss_defeated"]:
                max_unlocked = max(max_unlocked, min(len(STAGE_LIVE_LIMIT), stage + 1))
                state = "win"
            elif world["xp"] >= world["xp_need"]:
                world["xp"] -= world["xp_need"]
                world["upgrade_level"] += 1
                # The first two upgrades arrive quickly (5 then 8 blocks);
                # from the third onward, each level needs four more blocks.
                world["xp_need"] = 8 if world["upgrade_level"] == 1 else 8 + (world["upgrade_level"] - 1) * 4
                world["up_cards"] = generate_upgrade_cards(player)
                world["refresh_left"] = 2
                world["upgrade_intro_timer"] = 30 if all(perk["func"].startswith("weapon_ultimate_") for perk in world["up_cards"]) else 16
                state = "upgrade"

        if state == "menu":
            menu_controls = draw_menu(max_unlocked, gold_total, mouse)
        elif state == "achievement":
            collection_back = draw_collection_page(profile, "achievement", mouse)
        elif state == "codex":
            collection_back = draw_collection_page(profile, "codex", mouse)
        elif state in ("talents", "weapon_lab"):
            progression_controls = draw_progression_page(profile, state, equipped_weapon, mouse)
        elif state == "shop":
            draw_menu(max_unlocked, gold_total, mouse)
            shop_controls = draw_shop(gold_total, owned_weapons, mouse)
        elif state == "weapons":
            draw_menu(max_unlocked, gold_total, mouse)
            select_controls = draw_weapon_select(gold_total, owned_weapons, equipped_weapon, mouse)
        else:
            draw_game_background(stage)
            player = world["player"]
            for bullet in world["bullets"]:
                bullet.draw()
            for enemy in world["enemies"]:
                enemy.draw()
            for enemy in world["mini"]:
                enemy.draw()
            if world["boss"]:
                world["boss"].weakpoint_suppressed = player.current_weapon == "laser"
                world["boss"].draw()
            draw_hit_focus(world["focus_target"], world["focus_timer"])
            for particle in world["particles"]:
                particle.draw()
            for popup in world["damage_popups"]:
                popup.draw()
            mine_sprite = ENTITY_SPRITES.get("mine")
            if mine_sprite:
                for mine in world["mines"]:
                    mx, my = world_to_screen(mine["x"], mine["y"])
                    screen.blit(mine_sprite, mine_sprite.get_rect(center=(int(mx), int(my))))
            player.draw(*mouse)
            draw_damage_vignette(player)
            drone_sprite = ENTITY_SPRITES.get("drone")
            if player.drone_enabled and drone_sprite:
                orbit = pygame.time.get_ticks() * 0.003
                dx, dy = math.cos(orbit) * 42, math.sin(orbit) * 30
                drx, dry = world_to_screen(player.x + dx, player.y + dy)
                screen.blit(drone_sprite, drone_sprite.get_rect(center=(int(drx), int(dry))))
            if player.boss_compass and world["boss"]:
                boss = world["boss"]
                angle = math.atan2(boss.y - player.y, boss.x - player.x)
                cx, cy = W - 58, 70
                tip = (cx + math.cos(angle) * 20, cy + math.sin(angle) * 20)
                left = (cx + math.cos(angle + 2.5) * 13, cy + math.sin(angle + 2.5) * 13)
                right = (cx + math.cos(angle - 2.5) * 13, cy + math.sin(angle - 2.5) * 13)
                pygame.draw.polygon(screen, YELLOW, [tip, left, right])
                label = font_small.render("首领", True, YELLOW)
                screen.blit(label, label.get_rect(center=(cx, cy + 30)))
            draw_hud(
                player, stage, world["normal_kills"], STAGE_KILL_QUOTA[stage - 1],
                world["boss_spawned"], world["score"], world["xp"], world["xp_need"],
                world["upgrade_level"], world["combo"],
            )
            if world["boss_alert_timer"] > 0:
                alert_progress = world["boss_alert_timer"] / 180
                banner = pygame.Surface((W, 118), pygame.SRCALPHA)
                banner.fill((95, 0, 0, int(165 * min(1, alert_progress * 3))))
                screen.blit(banner, (0, H // 2 - 59))
                pulse = int(math.sin(pygame.time.get_ticks() * 0.018) * 4)
                alert = font_menu_large.render("首领来袭", True, (255, 84, 54))
                subtitle = font_menu_small.render("警报：高威胁目标已进入战区", True, WHITE)
                screen.blit(alert, alert.get_rect(center=(W // 2, H // 2 - 13 + pulse)))
                screen.blit(subtitle, subtitle.get_rect(center=(W // 2, H // 2 + 32 + pulse)))
            if world["boss_buff_notice_timer"] > 0:
                buff_text = font_small.render(world["boss_buff_notice"], True, YELLOW)
                screen.blit(buff_text, buff_text.get_rect(center=(W // 2, 55)))
            if world["achievement_notice_timer"] > 0:
                draw_achievement_toast(
                    world["achievement_notice"], world["achievement_notice_desc"],
                    world["achievement_notice_timer"],
                )
            if state == "upgrade":
                upgrade_controls = draw_upgrade_menu(
                    world["up_cards"], world["refresh_left"], mouse, world["upgrade_intro_timer"]
                )
            elif state == "win":
                win_controls = draw_win_pop(stage < len(STAGE_LIVE_LIMIT), profile, world["materials_gained"])
            elif state == "gameover":
                over_controls = draw_game_over_pop()
        pygame.display.flip()
        # Browser builds must yield once per frame so Safari can paint the
        # canvas, process input and continue loading packaged assets.
        await asyncio.sleep(0)

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(run_game())
