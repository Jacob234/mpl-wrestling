"""Render the README gallery into docs/images/. Run: python examples/gallery.py"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import mplwrestling as mw

OUT = Path(__file__).resolve().parents[1] / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)


def save(fig, name):
    fig.savefig(OUT / name, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("wrote", OUT / name)


# 1. The three regulation mats, each in its own units
fig, axes = plt.subplots(1, 3, figsize=(15, 5))
for ax, style, units in zip(axes, ["ncaa", "high_school", "international"], ["feet", "feet", "meters"]):
    mat = mw.WrestlingMat(style, units=units)
    mat.draw(ax=ax)
    ax.set_title(f"{style}: {2 * mat.radius:g} {units} circle", fontsize=11)
save(fig, "mats.png")

# 2. One-page match summary from the bundled (fictional) sample
match = mw.load_sample_match()
save(mw.match_summary(match), "match_summary.png")

# 3. Mat-zone heatmap of synthetic takedown locations
rng = np.random.default_rng(7)
mat = mw.WrestlingMat("ncaa")
n = 400
angle = rng.uniform(0, 2 * np.pi, n)
radius = np.clip(rng.normal(0.72, 0.22, n), 0, 1.05) * mat.radius   # takedowns cluster near the edge
x, y = radius * np.cos(angle), radius * np.sin(angle)
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6))
mat.draw(ax=ax1)
mat.zone_heatmap(x, y, ax=ax1, normalize=True, cmap="magma")
ax1.set_title("Share of takedowns by mat zone (synthetic data)")
mat.draw(ax=ax2)
mat.heatmap(x, y, ax=ax2, bins=12, cmap="YlOrRd", alpha=0.85, clip_to="competition")
ax2.set_title("Takedown density (synthetic data)")
save(fig, "zones.png")
