"""Pixel-Optik des Zimmers (tutor/pixel_zimmer.py, 2026-10-08) — headless.

Geprüft wird, was „Pixel statt Matsch" heißt: ganzzahliges Raster, in der
Szene nur Palettenfarben (keine weichen Zwischentöne), beide Themen und
kleine Fenster stürzen nicht ab; und die Einstellung tutor_optik.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
pygame = pytest.importorskip("pygame")

from tutor import pixel_zimmer as px   # noqa: E402


@pytest.mark.parametrize("w,h", [(1280, 720), (920, 600), (800, 480), (1920, 1080)])
def test_raster_ist_ganzzahlig_und_mindestens_zwei(w, h):
    s, W, H = px.raster(w, h)
    assert isinstance(s, int) and s >= 2
    assert W * s <= w and H * s <= h and w - W * s < s and h - H * s < s


@pytest.mark.parametrize("pal", [px.NACHT, px.TAG])
def test_hintergrund_nur_palettenfarben(pal):
    pygame.init()
    fl = px.hintergrund(320, 180, pal)
    erlaubt = {tuple(c) for c in pal.values()}
    gesehen = {tuple(fl.get_at((x, y)))[:3] for x in range(0, 320, 3) for y in range(0, 180, 3)}
    fremd = gesehen - erlaubt
    assert not fremd, f"Farben außerhalb der Palette (weiche Kanten?): {sorted(fremd)[:5]}"


class _Figur:
    x = 400.0

    def head_top(self):
        return 300.0

    def draw(self, surf):
        w, h = surf.get_size()
        pygame.draw.rect(surf, (200, 60, 60), (w // 3, h // 2, max(8, w // 40), h // 6))


@pytest.mark.parametrize("thema", ["night", "day"])
@pytest.mark.parametrize("w,h", [(1280, 720), (800, 480), (320, 200)])
def test_ein_frame_ohne_absturz(thema, w, h):
    pygame.init()
    screen = pygame.Surface((w, h))
    z = px.Pixelzimmer(lambda n: pygame.font.Font(None, n))
    z.zeichnen(screen, dict(
        w=w, h=h, t=0.3, thema=thema, persona=_Figur(), tv_an=True, tv_titel="x",
        kopf=(400, 300), blase="¿Quieres agua? " * 6, gedanke=("agua", "water"),
        name="Lucía", hinweis="Esc Menü", mikro="Mic: hört zu", musik="♪ chill",
        laune="ok", batterie=55, log=[("user", "hola"), ("tutor", "¡Hola!")] * 4,
        scroll=0, eingabe="", ime=""))
    # Figur kommt durch das Raster: es gibt ihr Rot im Bild
    assert any(tuple(screen.get_at((x, y)))[:3] == (200, 60, 60)
               for x in range(0, w, 2) for y in range(0, h, 2))


def test_optik_einstellung(monkeypatch):
    import ai_config
    import tutor_port
    monkeypatch.setattr(ai_config, "_overrides", {})
    monkeypatch.delenv("ZENTRALE_TUTOR_OPTIK", raising=False)
    monkeypatch.setattr(ai_config, "_config", {})
    assert tutor_port.optik() == "pixel", "Standard: pixel"
    ai_config.set_override("tutor_optik", "alt")
    assert tutor_port.optik() == "alt"
    ai_config.set_override("tutor_optik", "quatsch")
    assert tutor_port.optik() == "pixel", "Tippfehler → kein leeres Bild"
