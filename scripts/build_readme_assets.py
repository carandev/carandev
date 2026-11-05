#!/usr/bin/env python3
"""Build the SVG assets used by the profile README.

GitHub strips CSS and web fonts from READMEs, and images cannot load external
resources. Each asset therefore carries the carandev.me design tokens inline,
draws its text as outlines, and embeds the avatar.

Requirements: pip install fonttools uharfbuzz

Usage: build_readme_assets.py FONTS_DIR AVATAR_IMAGE

FONTS_DIR holds the Google Fonts files Marcellus.ttf, Caveat.ttf and
Jakarta.ttf (Plus Jakarta Sans). AVATAR_IMAGE is the site's avatar.
"""

import base64
import mimetypes
import sys
from html import escape
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

OUT = Path(__file__).resolve().parent.parent / "assets"

LIGHT = {
    "ink": "#2c221e", "ink-light": "#5a4c46", "ink-strong": "#15100e",
    "paper": "#faf7f2", "paper-border": "#e5dacb", "paper-border-strong": "#d8cbb7",
    "surface": "#fff", "shadow-ink": "#2c221e", "olive": "#386f54",
    "olive-dark": "#1f3b2d", "on-olive": "#fff", "wine": "#9b1d43", "gold": "#b45309",
    "lavender-bg": "#e7e1f3", "lavender-soft": "#f3f0f9", "lavender-border": "#d4c5e8",
    "lavender-ink": "#3e2c50", "cream-bg": "#fdf4dc", "cream-border": "#f5d384",
    "cream-ink": "#78350f", "mint-bg": "#e8f0ea", "mint-border": "#c5dccb",
    "mint-ink": "#2d5843", "rose-bg": "#fbe4e8", "rose-border": "#f5bac5",
    "rose-ink": "#851d41", "sky-bg": "#eaf0f8", "sky-border": "#c5d4e8", "sky-ink": "#3b5270",
}
DARK = {
    "ink": "#ede4d8", "ink-light": "#b9ac9e", "ink-strong": "#fff8ee",
    "paper": "#1a1513", "paper-border": "#3a302b", "paper-border-strong": "#50443c",
    "surface": "#241e1b", "shadow-ink": "#0b0807", "olive": "#7dbf9c",
    "olive-dark": "#2a4f3c", "on-olive": "#10241a", "wine": "#f08aa6", "gold": "#e9a957",
    "lavender-bg": "#2f2939", "lavender-soft": "#26212e", "lavender-border": "#4c4160",
    "lavender-ink": "#dbcff0", "cream-bg": "#352c1b", "cream-border": "#6d5628",
    "cream-ink": "#f3daa2", "mint-bg": "#1f2e26", "mint-border": "#37513f",
    "mint-ink": "#b6d9c3", "rose-bg": "#3a2129", "rose-border": "#6b3543",
    "rose-ink": "#f3b9c7", "sky-bg": "#1f2834", "sky-border": "#364b64", "sky-ink": "#bdd1eb",
}

# Corner radii from the site, as (horizontal, vertical) per corner: TL, TR, BR, BL.
SKETCH = ((255, 15, 225, 15), (15, 225, 15, 255))
CARD = ((20, 24, 18, 22), (22, 18, 24, 20))
CARD_ALT = ((22, 18, 24, 20), (20, 24, 18, 22))
SMALL = ((14, 18, 12, 16), (16, 12, 18, 14))
CHIP = ((12, 14, 10, 12), (12, 10, 14, 12))
BLOB = ((30, 40, 26, 44), (40, 26, 44, 30))


class Fonts:
    def __init__(self, directory):
        self.faces = {}
        for name, file in (("display", "Marcellus.ttf"), ("hand", "Caveat.ttf"), ("sans", "Jakarta.ttf")):
            self.faces[name] = hb.Face(hb.Blob.from_file_path(str(Path(directory) / file)))

    def shape(self, text, family, weight):
        face = self.faces[family]
        font = hb.Font(face)
        if family != "display":
            font.set_variations({"wght": weight})
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf, {"kern": True, "liga": True})
        return font, face.upem, buf


FONTS = None


def _num(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


def width(text, family, size, weight=400):
    _, upem, buf = FONTS.shape(text, family, weight)
    return sum(p.x_advance for p in buf.glyph_positions) * size / upem


def text(value, x, y, family, size, color, weight=400, anchor="start"):
    """Draw text as one outlined path, since SVG images cannot load web fonts."""
    font, upem, buf = FONTS.shape(value, family, weight)
    scale = size / upem
    total = sum(p.x_advance for p in buf.glyph_positions) * scale
    cursor = x - {"start": 0, "middle": total / 2, "end": total}[anchor]
    pen = SVGPathPen(None, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        if info.codepoint == 0:
            raise ValueError(f"{family} has no glyph for a character in {value!r}")
        font.draw_glyph_with_pen(info.codepoint, TransformPen(
            pen, (scale, 0, 0, -scale, cursor + pos.x_offset * scale, y - pos.y_offset * scale)))
        cursor += pos.x_advance * scale
    return f'<path style="fill:var(--{color})" d="{pen.getCommands()}"/>'


def wrap(value, family, size, max_width, weight=400):
    lines, line = [], ""
    for word in value.split():
        candidate = f"{line} {word}".strip()
        if line and width(candidate, family, size, weight) > max_width:
            lines.append(line)
            line = word
        else:
            line = candidate
    return lines + [line]


def paragraph(value, x, y, family, size, color, max_width, leading, weight=400):
    lines = wrap(value, family, size, max_width, weight)
    return "".join(text(l, x, y + i * leading, family, size, color, weight) for i, l in enumerate(lines))


def shape_path(x, y, w, h, radii):
    """Build a rounded rectangle path that scales radii like CSS border-radius."""
    (htl, htr, hbr, hbl), (vtl, vtr, vbr, vbl) = radii
    f = min(1, w / (htl + htr), w / (hbl + hbr), h / (vtl + vbl), h / (vtr + vbr))
    htl, htr, hbr, hbl, vtl, vtr, vbr, vbl = (r * f for r in (htl, htr, hbr, hbl, vtl, vtr, vbr, vbl))
    n = _num
    return (
        f"M{n(x + htl)} {n(y)}H{n(x + w - htr)}A{n(htr)} {n(vtr)} 0 0 1 {n(x + w)} {n(y + vtr)}"
        f"V{n(y + h - vbr)}A{n(hbr)} {n(vbr)} 0 0 1 {n(x + w - hbr)} {n(y + h)}"
        f"H{n(x + hbl)}A{n(hbl)} {n(vbl)} 0 0 1 {n(x)} {n(y + h - vbl)}"
        f"V{n(y + vtl)}A{n(htl)} {n(vtl)} 0 0 1 {n(x + htl)} {n(y)}Z"
    )


def box(x, y, w, h, radii, fill, stroke=None, stroke_width=1.5, shadow=None, offset=(0, 0), extra=""):
    parts = []
    d = shape_path(x, y, w, h, radii)
    if shadow:
        parts.append(f'<path style="fill:var(--{shadow})" transform="translate({offset[0]} {offset[1]})" d="{d}"/>')
    style = f"fill:var(--{fill})"
    if stroke:
        style += f";stroke:var(--{stroke});stroke-width:{stroke_width}"
    parts.append(f'<path style="{style}" {extra}d="{d}"/>')
    return "".join(parts)


def chip(value, x, y):
    w = width(value, "sans", 13, 700) + 24
    return box(x, y, w, 28, CHIP, "surface", "paper-border-strong", 1) + text(
        value, x + 12, y + 19, "sans", 13, "ink-light", 700), w


def tape(cx, y, tone, rotate=-3, w=84):
    return (
        f'<rect x="{cx - w / 2}" y="{y}" width="{w}" height="24" opacity=".85" '
        f'transform="rotate({rotate} {cx} {y + 12})" style="fill:var(--{tone})"/>'
    )


def arrow(x, y, color, size=9):
    """Draw the site's external-link arrow, with its bottom-left corner at x, y."""
    return (
        f'<path style="fill:none;stroke:var(--{color});stroke-width:2;stroke-linecap:round;'
        f'stroke-linejoin:round" d="M{x} {y}L{x + size} {y - size}M{x + 2} {y - size}H{x + size}V{y - 2}"/>'
    )


def svg(name, w, h, title, body):
    def tokens(values):
        return "".join(f"--{k}:{v};" for k, v in values.items())

    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{escape(title)}"><title>{escape(title)}</title>'
        f"<style>:root{{{tokens(LIGHT)}}}"
        f"@media (prefers-color-scheme:dark){{:root{{{tokens(DARK)}}}}}</style>{body}</svg>\n",
        encoding="utf-8",
    )


def data_uri(path):
    mime = mimetypes.guess_type(path)[0] or "image/webp"
    return f"data:{mime};base64,{base64.b64encode(Path(path).read_bytes()).decode()}"


def build_hero(avatar):
    w, h = 880, 420
    body = [box(1, 1, w - 2, h - 2, CARD, "paper", "paper-border")]

    # Logo in its hand-drawn lavender oval.
    body.append(f'<ellipse cx="96" cy="50" rx="58" ry="23" transform="rotate(-3 96 50)" '
                'style="fill:none;stroke:var(--lavender-border);stroke-width:2.5"/>')
    body.append(text("carandev", 96, 58, "hand", 27, "ink", 700, "middle"))

    body.append(text("hi! I'm", 44, 122, "hand", 34, "wine", 700))
    body.append(text("Carlos Gómez", 44, 186, "display", 62, "ink-strong"))
    x = 44
    for run, weight in (("Fullstack Developer", 700), (" · .NET + React", 500)):
        body.append(text(run, x, 226, "sans", 19, "ink", weight))
        x += width(run, "sans", 19, weight)
    body.append(paragraph(
        "Systems engineering student and fullstack developer passionate about building clean, "
        "functional software. When I'm not coding, I'm exploring 3D design or getting lost in a fantasy novel.",
        44, 260, "sans", 15.5, "ink-light", 510, 25))

    x = 44
    for label in ("Continuous learner", "Fantasy book lover"):
        drawn, chip_w = chip(label, x, 342)
        body.append(drawn)
        x += chip_w + 10
    body.append(text("building things that matter", 44, 400, "hand", 25, "gold", 700))

    # Framed avatar: rose backing, ink border, hard shadow, and tape.
    ax, ay, aw, ah = 610, 74, 226, 262
    body.append(f'<g transform="rotate(3 {ax + aw / 2} {ay + ah / 2})">'
                + box(ax + 6, ay + 4, aw, ah, BLOB, "rose-bg", "rose-border") + "</g>")
    body.append(box(ax, ay, aw, ah, BLOB, "lavender-bg", "shadow-ink", 2.5, "shadow-ink", (5, 6)))
    body.append(f'<clipPath id="avatar"><path d="{shape_path(ax, ay, aw, ah, BLOB)}"/></clipPath>')
    body.append(f'<image href="{data_uri(avatar)}" x="{ax}" y="{ay}" width="{aw}" height="{ah}" '
                'preserveAspectRatio="xMidYMid slice" clip-path="url(#avatar)"/>')
    body.append(f'<path style="fill:none;stroke:var(--shadow-ink);stroke-width:2.5" '
                f'd="{shape_path(ax, ay, aw, ah, BLOB)}"/>')
    body.append(tape(ax + aw / 2, ay - 12, "cream-border"))

    # Handwritten caption and its curved arrow.
    body.append(f'<g transform="rotate(-8 505 376)">{text("that is me", 505, 376, "hand", 23, "ink-light", 700, "middle")}</g>')
    body.append('<path style="fill:none;stroke:var(--ink-light);stroke-width:1.8;stroke-linecap:round;'
                'stroke-linejoin:round" d="M556 364C580 358 596 346 604 330M592 336L605 328L607 343"/>')

    svg("hero.svg", w, h, "Hi! I'm Carlos Gómez, fullstack developer working with .NET and React.", "".join(body))


def build_stack():
    w, h = 880, 330
    body = [box(1, 1, w - 2, h - 2, CARD_ALT, "surface", "paper-border")]
    body.append(text("01 · stack", 44, 74, "hand", 27, "gold", 700))
    for i, line in enumerate(("What I build", "things with")):
        body.append(text(line, 44, 122 + i * 44, "display", 38, "ink-strong"))
    body.append('<path style="fill:none;stroke:var(--wine);stroke-width:2.5;stroke-linecap:round" '
                'd="M46 186C90 180 150 192 240 182"/>')

    cards = (
        ("Frontend", "React · Next.js · Tailwind CSS · Vite · Blazor", "lavender", CARD),
        ("Backend", ".NET · C# · Node.js", "cream", CARD_ALT),
        ("Database", "Firebase · SQL Server", "mint", CARD_ALT),
        ("Tools", "Git · GitHub Actions", "rose", CARD),
    )
    cw, ch, gap = 262, 130, 16
    for i, (title, items, tone, radii) in enumerate(cards):
        x, y = 310 + (i % 2) * (cw + gap), 34 + (i // 2) * (ch + gap)
        body.append(box(x, y, cw, ch, radii, f"{tone}-bg", f"{tone}-border"))
        body.append(text(title, x + 20, y + 42, "display", 24, f"{tone}-ink"))
        body.append(paragraph(items, x + 20, y + 74, "sans", 15, f"{tone}-ink", cw - 40, 23, 500))
    svg("stack.svg", w, h, "Stack: React, Next.js, Tailwind CSS, Vite, Blazor, .NET, C#, Node.js, "
        "Firebase, SQL Server, Git and GitHub Actions.", "".join(body))


def build_banner(name, eyebrow, title):
    w, h = 880, 128
    body = box(1, 1, w - 2, h - 2, CARD, "paper", "paper-border")
    body += text(eyebrow, 44, 52, "hand", 27, "gold", 700)
    body += text(title, 44, 100, "display", 38, "ink-strong")
    svg(name, w, h, f"{eyebrow}: {title}", body)


def build_project(name, title, description, link, tone, rotate, radii):
    w, h = 430, 330
    body = [box(1, 14, w - 8, h - 22, radii, "surface", "paper-border", 1.5, "paper-border-strong", (3, 4))]
    body.append(box(20, 34, w - 46, 96, SMALL, f"{tone}-bg", f"{tone}-border"))
    body.append(text(title, (w - 6) / 2, 94, "hand", 36, f"{tone}-ink", 700, "middle"))
    body.append(tape((w - 6) / 2, 2, f"{tone}-border", rotate))
    body.append(text(title, 22, 172, "display", 26, "ink-strong"))
    body.append(paragraph(description, 22, 204, "sans", 15, "ink-light", w - 60, 23))
    link_w = width(link, "sans", 14, 700)
    body.append(text(link, 22, 296, "sans", 14, "ink", 700))
    body.append(f'<path style="fill:none;stroke:var(--ink);stroke-width:1.5" d="M22 301H{22 + link_w:.1f}"/>')
    body.append(arrow(round(30 + link_w), 295, "ink"))
    svg(name, w, h, f"{title}: {description} {link}", "".join(body))


def build_contact():
    w, h = 880, 160
    body = box(3, 3, w - 12, h - 14, BLOB, "lavender-soft", "shadow-ink", 2.5, "shadow-ink", (5, 6))
    body += text("04 · let's talk?", (w - 6) / 2, 62, "hand", 28, "wine", 700, "middle")
    body += text("Find me around the web", (w - 6) / 2, 118, "display", 42, "ink-strong", 400, "middle")
    svg("contact.svg", w, h, "04, let's talk? Find me around the web.", body)


def build_button(name, label, primary=False):
    h = 54
    text_w = width(label, "sans", 16, 700)
    w = round(text_w + 66)
    if primary:
        body = box(2, 2, w - 8, h - 9, SKETCH, "olive", "olive-dark", 1.5, "olive-dark", (3, 4))
        color = "on-olive"
    else:
        body = box(2, 2, w - 8, h - 9, SMALL, "surface", "paper-border-strong", 1.5, "paper-border-strong", (2, 2))
        color = "ink"
    body += text(label, 22, 32, "sans", 16, color, 700)
    body += arrow(round(30 + text_w), 31, color)
    svg(name, w, h, label, body)


def main(fonts_dir, avatar):
    global FONTS
    FONTS = Fonts(fonts_dir)
    build_hero(avatar)
    build_stack()
    build_banner("heading-projects.svg", "02 · projects", "Things I've built")
    build_banner("heading-activity.svg", "03 · activity", "Lately on GitHub")
    build_project("project-portfolio.svg", "Portfolio",
                  "Personal portfolio site built with vanilla HTML/CSS/JS.",
                  "carandev.me", "rose", -3, CARD)
    build_project("project-flat-brutal.svg", "Flat Brutal UI",
                  "Razor component library with brutalist design system.",
                  "flatbrutal.carandev.me", "cream", 2, CARD_ALT)
    build_project("project-accounting.svg", "Accounting Manager",
                  "Personal finance management web app.",
                  "accounting-manager.carandev.me", "mint", -2, CARD_ALT)
    build_project("project-bacpac.svg", "BACPAC Manager",
                  "JetBrains plugin to import .bacpac files into SQL Server.",
                  "JetBrains Marketplace", "lavender", 3, CARD)
    build_contact()
    build_button("button-portfolio.svg", "Portfolio")
    build_button("button-linkedin.svg", "LinkedIn")
    build_button("button-twitter.svg", "Twitter")
    build_button("button-twitch.svg", "Twitch")
    build_button("button-youtube.svg", "YouTube")
    build_button("button-email.svg", "Email", primary=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
