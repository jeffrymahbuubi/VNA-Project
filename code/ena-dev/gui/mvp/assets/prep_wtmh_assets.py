"""prep_wtmh_assets.py — one-time/regenerable prep of the WTMH branding assets (G-14).

Copies the lab `.ico` and downscales the 6 MB source logo to a small RGBA PNG used for
the in-app TopBar emblem (design-system §9.11/D-21). Re-run if the source logo changes.

    uv run python ena-dev/gui/mvp/assets/prep_wtmh_assets.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent                       # code/ena-dev/gui/mvp/assets
SRC = (HERE.parents[3] / "LibreVNA-dev" / "gui" / "resources")  # code/LibreVNA-dev/gui/resources
LOGO_PX = 256


def main() -> int:
    ico_src, png_src = SRC / "WTMH.ico", SRC / "WTMH.png"
    if not ico_src.exists() or not png_src.exists():
        print(f"FAIL: source assets not found under {SRC}")
        return 1
    # 1) copy the multi-res .ico verbatim (window/taskbar + PyInstaller --icon).
    shutil.copyfile(ico_src, HERE / "WTMH.ico")
    print(f"copied  {HERE / 'WTMH.ico'}  ({(HERE / 'WTMH.ico').stat().st_size} B)")
    # 2) downscale the 6 MB PNG → small RGBA emblem (preserve transparency).
    img = Image.open(png_src).convert("RGBA")
    img.thumbnail((LOGO_PX, LOGO_PX), Image.LANCZOS)
    out = HERE / "wtmh_logo.png"
    img.save(out, "PNG", optimize=True)
    print(f"scaled  {out}  {img.size}  ({out.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
