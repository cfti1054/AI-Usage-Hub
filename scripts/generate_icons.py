"""AI Hub 앱 아이콘(A안 · 세 조각 원호) 생성기.

    uv run --no-project --with pillow python scripts/generate_icons.py

만드는 파일
- frontend/public/icons/app-icon.svg        원본 SVG (세 조각, 흰 바탕 둥근 사각형)
- frontend/src/app/icon.svg                 브라우저 탭 파비콘 (작은 크기용 두 조각)
- frontend/src/app/favicon.ico              구형 브라우저용 16·32·48
- frontend/src/app/apple-icon.png           아이폰 홈 화면 180 (꽉 찬 흰 바탕 — iOS 가 모서리를 깎음)
- frontend/public/icons/icon-192.png        PWA
- frontend/public/icons/icon-512.png        PWA
- frontend/public/icons/icon-maskable-512.png 안드로이드 모양 맞춤 (안전 영역 안에 축소)

도형은 100×100 좌표계 기준이며, 디자인 목업의 SVG 와 같은 각도·순서로 그린다.
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "app"
PUBLIC_ICONS = ROOT / "frontend" / "public" / "icons"

INK = "#12151C"
GREEN = "#1DB98B"
ORANGE = "#E07A55"
WHITE = "#FFFFFF"
BORDER = "#E3E6EB"

RADIUS = 30  # 원호 반지름
CIRC = 2 * math.pi * RADIUS


def deg(length: float) -> float:
    return length / CIRC * 360


# (색, 시작 각도, 호 길이) — 그리는 순서대로. 0° = 3시 방향, 시계 방향
FULL = {"stroke": 7, "arcs": [(INK, -90, 100), (GREEN, 30, 40), (ORANGE, 110, 22)]}
MEDIUM = {"stroke": 10, "arcs": FULL["arcs"]}
SMALL = {"stroke": 16, "arcs": [(INK, -90, 100), (ORANGE, 30, 40)]}


def svg(spec: dict, rounded: bool = True) -> str:
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">']
    if rounded:
        parts.append(f'<rect x="0.5" y="0.5" width="99" height="99" rx="22" fill="{WHITE}" stroke="{BORDER}"/>')
    else:
        parts.append(f'<rect width="100" height="100" fill="{WHITE}"/>')
    for color, start, length in spec["arcs"]:
        parts.append(
            f'<circle cx="50" cy="50" r="{RADIUS}" fill="none" stroke="{color}" stroke-width="{spec["stroke"]}" '
            f'stroke-linecap="round" stroke-dasharray="{length} {CIRC - length:.1f}" transform="rotate({start} 50 50)"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


def render(size: int, spec: dict, *, rounded: bool, scale: float = 1.0) -> Image.Image:
    """4배로 크게 그린 뒤 줄여서 경계를 부드럽게 한다. scale 은 도형 크기 배율(마스커블 안전 영역용)."""
    ss = 4
    n = size * ss
    u = n / 100
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if rounded:
        border = max(ss, round(n / 170))
        draw.rounded_rectangle([0, 0, n - 1, n - 1], radius=22 * u, fill=WHITE, outline=BORDER, width=border)
    else:
        draw.rectangle([0, 0, n, n], fill=WHITE)

    c = 50 * u
    r = RADIUS * u * scale
    w = spec["stroke"] * u * scale
    for color, start, length in spec["arcs"]:
        end = start + deg(length)
        outer = r + w / 2
        draw.arc([c - outer, c - outer, c + outer, c + outer], start, end, fill=color, width=round(w))
        for angle in (start, end):  # 둥근 끝
            x = c + r * math.cos(math.radians(angle))
            y = c + r * math.sin(math.radians(angle))
            draw.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=color)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    PUBLIC_ICONS.mkdir(parents=True, exist_ok=True)
    (PUBLIC_ICONS / "app-icon.svg").write_text(svg(FULL), encoding="utf-8")
    (APP / "icon.svg").write_text(svg(SMALL), encoding="utf-8")

    render(180, FULL, rounded=False).convert("RGB").save(APP / "apple-icon.png", optimize=True)
    render(192, FULL, rounded=True).save(PUBLIC_ICONS / "icon-192.png", optimize=True)
    render(512, FULL, rounded=True).save(PUBLIC_ICONS / "icon-512.png", optimize=True)
    # 안드로이드는 모양을 원·물방울 등으로 잘라내므로 중앙 80% 안에 들어오도록 줄인다
    render(512, FULL, rounded=False, scale=0.78).convert("RGB").save(PUBLIC_ICONS / "icon-maskable-512.png", optimize=True)
    render(256, SMALL, rounded=True).save(APP / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

    for path in [PUBLIC_ICONS / "app-icon.svg", APP / "icon.svg", APP / "apple-icon.png", APP / "favicon.ico",
                 PUBLIC_ICONS / "icon-192.png", PUBLIC_ICONS / "icon-512.png", PUBLIC_ICONS / "icon-maskable-512.png"]:
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
