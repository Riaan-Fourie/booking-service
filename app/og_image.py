"""Dynamic OG image generation using Pillow.

Pre-computes gradient-overlaid backgrounds at module load for fast generation.
Output is JPEG with sharpening for crisp text even after WhatsApp re-compression.
"""

import io
import logging
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger("booking.og_image")

STATIC_DIR = Path(__file__).parent.parent / "static"
BG_IMAGE_PATHS = {
    "duckweed": STATIC_DIR / "duckweed-farm.png",
    "coffee": STATIC_DIR / "cafe-scene.png",
}

# OG image dimensions (1200x630 is the standard)
OG_WIDTH = 1200
OG_HEIGHT = 630

# ── Pre-compute backgrounds with gradient at module load ──────────
_prepared_backgrounds: dict[str, Image.Image] = {}


def _prepare_background(theme: str) -> Image.Image:
    """Load, resize, and apply gradient overlay to a background image."""
    bg_path = BG_IMAGE_PATHS.get(theme, BG_IMAGE_PATHS["duckweed"])
    try:
        bg = Image.open(bg_path).convert("RGBA")
    except FileNotFoundError:
        logger.error("Background image not found at %s", bg_path)
        bg = Image.new("RGBA", (OG_WIDTH, OG_HEIGHT), (5, 46, 22, 255))

    bg = bg.resize((OG_WIDTH, OG_HEIGHT), Image.LANCZOS)

    # Build gradient as raw bytes (much faster than 630 draw.line calls)
    gradient_data = bytearray(OG_WIDTH * OG_HEIGHT * 4)
    for y in range(OG_HEIGHT):
        alpha = int(140 * (y / OG_HEIGHT) ** 1.5)
        row = bytes([0, 0, 0, alpha]) * OG_WIDTH
        offset = y * OG_WIDTH * 4
        gradient_data[offset : offset + OG_WIDTH * 4] = row

    gradient = Image.frombytes("RGBA", (OG_WIDTH, OG_HEIGHT), bytes(gradient_data))
    return Image.alpha_composite(bg, gradient)


def _init_backgrounds() -> None:
    """Pre-compute all theme backgrounds at startup."""
    for theme in BG_IMAGE_PATHS:
        try:
            _prepared_backgrounds[theme] = _prepare_background(theme)
            logger.info("Pre-computed OG background for theme: %s", theme)
        except Exception:
            logger.exception("Failed to pre-compute OG background for %s", theme)


# Run at import time so backgrounds are ready before first request
_init_backgrounds()


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get a font, falling back to default if preferred fonts aren't available."""
    if bold:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]
    else:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


# Pre-load fonts at module level
_font_small = _get_font(36)
_font_large = _get_font(64, bold=True)
_font_med = _get_font(32)


def _draw_text_with_shadow(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    shadow_offset: int = 2,
) -> None:
    """Draw text with a subtle drop shadow for readability."""
    x, y = xy
    draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=(0, 0, 0, 120))
    draw.text(xy, text, font=font, fill=fill)


@lru_cache(maxsize=128)
def generate_og_image(recipient_name: str, theme: str = "duckweed") -> bytes:
    """Generate a personalized OG image. Returns JPEG bytes (~40-60KB)."""
    bg = _prepared_backgrounds.get(theme)
    if bg is None:
        bg = _prepare_background(theme)

    # Copy so we don't draw on the cached background
    img = bg.copy()
    draw = ImageDraw.Draw(img)

    # Theme-aware text colors
    if theme == "coffee":
        subtitle_fill = (220, 200, 180, 230)
        ampersand_fill = (210, 180, 150, 220)
    else:
        subtitle_fill = (200, 220, 200, 230)
        ampersand_fill = (180, 210, 180, 220)

    # Personalized vs generic OG image
    from app.config import config

    if recipient_name:
        first_name = recipient_name.split()[0]
        main_text = f"{first_name} & {config.OWNER_FIRST_NAME}"
        subtitle_text = "A Coffee Chat" if theme == "coffee" else "A conversation with"
    else:
        main_text = config.OWNER_NAME
        subtitle_text = "Book a call with"

    _draw_text_with_shadow(
        draw, (80, OG_HEIGHT - 190),
        subtitle_text,
        font=_font_small, fill=subtitle_fill,
    )
    _draw_text_with_shadow(
        draw, (80, OG_HEIGHT - 130),
        main_text,
        font=_font_large, fill=(255, 255, 255, 255),
    )

    # Sharpen after text compositing to keep text crisp through WhatsApp re-compression
    rgb = img.convert("RGB")
    rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.2, percent=100, threshold=2))

    buffer = io.BytesIO()
    rgb.save(buffer, format="JPEG", quality=92, optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def get_static_og_image(theme: str = "duckweed") -> bytes:
    """Return a plain background as JPEG fallback."""
    bg = _prepared_backgrounds.get(theme)
    if bg is None:
        bg_path = BG_IMAGE_PATHS.get(theme, BG_IMAGE_PATHS["duckweed"])
        return bg_path.read_bytes()
    rgb = bg.convert("RGB")
    buffer = io.BytesIO()
    rgb.save(buffer, format="JPEG", quality=92, optimize=True)
    buffer.seek(0)
    return buffer.getvalue()
