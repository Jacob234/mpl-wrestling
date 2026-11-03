import matplotlib
matplotlib.use("Agg")

import numpy as np
import pytest

from mplwrestling import MAT_UNITS, MatStyle, WrestlingMat, ureg


@pytest.mark.parametrize("name, expected", [
    ("ncaa", MatStyle.NCAA), ("NCAA", MatStyle.NCAA), ("Folkstyle", MatStyle.NCAA), ("college", MatStyle.NCAA),
    ("high school", MatStyle.HIGH_SCHOOL), ("nfhs", MatStyle.HIGH_SCHOOL),
    ("Greco-Roman", MatStyle.INTERNATIONAL), (" freestyle ", MatStyle.INTERNATIONAL), ("olympics", MatStyle.INTERNATIONAL),
])
def test_from_string_aliases(name, expected):
    assert MatStyle.from_string(name) is expected


def test_unknown_style_points_to_custom():
    with pytest.raises(ValueError, match="WrestlingMat.custom"):
        WrestlingMat("sumo")


def test_style_must_be_str_or_enum():
    with pytest.raises(TypeError):
        WrestlingMat(3)


def test_rulebook_dimensions_native_units():
    assert WrestlingMat("ncaa").radius == pytest.approx(16)          # 32 ft circle
    assert WrestlingMat("high_school").radius == pytest.approx(14)   # 28 ft circle
    intl = WrestlingMat("international", units="meters")
    assert intl.radius == pytest.approx(4.5)
    assert intl.dims["passivity_zone_radius"] == pytest.approx(3.5)
    assert intl.dims["center_circle_radius"] == pytest.approx(0.5)


def test_unit_conversion_feet_to_meters():
    mat = WrestlingMat("ncaa", units="meters")
    assert mat.radius == pytest.approx(16 * 0.3048)
    assert mat.dims["starting_line_gap"] == pytest.approx(10 * 0.0254)
    assert mat.dimensions["competition_radius"].units == ureg.meter


def test_unit_conversion_accepts_abbreviations():
    assert WrestlingMat("international", units="ft").radius == pytest.approx(4.5 / 0.3048)


def test_none_measurements_survive_conversion():
    mat = WrestlingMat("ncaa", units="meters")
    assert mat.dims["center_circle_radius"] is None
    assert mat.dims["passivity_zone_radius"] is None


def test_mat_units_normalise_to_competition_radius():
    mat = WrestlingMat("high_school", units=MAT_UNITS)
    assert mat.radius == pytest.approx(1.0)
    assert mat.dims["center_circle_radius"] == pytest.approx(5 / 14)


def test_bad_units():
    with pytest.raises(ValueError):
        WrestlingMat("ncaa", units="seconds")
    with pytest.raises(ValueError):
        WrestlingMat("ncaa", units="parsnips")


def test_overrides_for_larger_ncaa_circle():
    mat = WrestlingMat("ncaa", competition_radius=21)             # plain number = native feet
    assert mat.radius == 21
    mat = WrestlingMat("ncaa", units="meters", competition_radius=6.4 * ureg.meters)
    assert mat.radius == pytest.approx(6.4)
    with pytest.raises(TypeError):
        WrestlingMat("ncaa", radius=21)


def test_custom_mat():
    youth = WrestlingMat.custom(competition_radius=10, protection_width=3, units="feet",
                                center_circle_radius=4)
    assert youth.style is MatStyle.CUSTOM
    assert youth.outer_radius == 13
    assert youth.dims["starting_line_length"] is None
    metric = WrestlingMat.custom(10 * ureg.feet, 3 * ureg.feet, units="meters")
    assert metric.radius == pytest.approx(3.048)
    youth.draw()
    with pytest.raises(TypeError):
        WrestlingMat.custom(10, 3, center_cirle_radius=4)     # typo is caught


def test_custom_mat_partial_starting_lines_and_passivity_zone():
    mat = WrestlingMat.custom(10, 3, starting_line_length=3, passivity_zone_radius=8)
    fig, ax = mat.draw()                                  # no KeyError, no TypeError
    corners = [p for p in ax.patches if type(p).__name__ == "Polygon"]
    assert corners == []                                  # red/blue corners are international only


def test_custom_style_requires_custom_constructor():
    with pytest.raises(ValueError):
        WrestlingMat(MatStyle.CUSTOM)


@pytest.mark.parametrize("style", ["ncaa", "high_school", "international"])
def test_draw_sets_square_limits(style):
    mat = WrestlingMat(style)
    fig, ax = mat.draw()
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    assert xmax >= mat.outer_radius and xmin <= -mat.outer_radius
    assert ymax >= mat.outer_radius and ymin <= -mat.outer_radius
    assert ax.get_aspect() == 1.0
    assert len(ax.patches) >= 2
    assert mat.fig is fig


def _artists(ax):
    return len(ax.patches) + len(ax.collections)


def test_draw_on_existing_axes_and_toggles():
    import matplotlib.pyplot as plt
    mat = WrestlingMat("high_school")
    fig, ax = plt.subplots()
    _, ax_full = mat.draw(ax=ax)
    assert ax_full is ax
    full = _artists(ax)
    _, no_circle = plt.subplots()
    mat.draw(ax=no_circle, show_center_circle=False)
    assert _artists(no_circle) == full - 1              # just the 10 ft circle
    _, no_lines = plt.subplots()
    mat.draw(ax=no_lines, show_starting_lines=False)
    assert _artists(no_lines) == full - 3               # down lines + two neutral lines


def test_draw_rejects_bad_home_side():
    with pytest.raises(ValueError):
        WrestlingMat("ncaa").draw(home_side="north")


def test_in_bounds():
    mat = WrestlingMat("ncaa")
    assert mat.in_bounds([0, 15.9, 16.1], [0, 0, 0]).tolist() == [True, True, False]


def test_zone_of():
    mat = WrestlingMat("ncaa")   # rings at 0, 5.33, 10.67, 16, 21
    ring, sector = mat.zone_of([0, 8, 0, -12, 18, 16], [0, 0.1, 8, -0.1, 0, 0], sectors=4)
    assert ring.tolist() == [0, 1, 1, 2, 3, 2]   # a point on the boundary line is in bounds
    assert sector.tolist() == [-1, 0, 1, 2, 0, 0]   # (-12, -0.1) is just past 180 degrees


def test_zone_heatmap_counts_everything_in_bounds():
    mat = WrestlingMat("ncaa")
    rng = np.random.default_rng(0)
    x, y = rng.uniform(-11, 11, 200), rng.uniform(-11, 11, 200)
    counts, wedges = mat.zone_heatmap(x, y)
    inside = mat.in_bounds(x, y).sum()
    assert sum(counts.values()) == inside
    assert len(wedges) == 1 + 2 * 8
    shares, _ = mat.zone_heatmap(x, y, normalize=True, include_out_of_bounds=True)
    assert sum(shares.values()) == pytest.approx(1.0)
    shares, _ = mat.zone_heatmap(np.append(x, 30), np.append(y, 0), normalize=True)
    assert sum(shares.values()) == pytest.approx(1.0)   # out-of-bounds point is not in the denominator


def test_heatmap_and_scatter_draw():
    mat = WrestlingMat("international", units="meters")
    points = mat.scatter([0, 1], [0, 1])
    assert points in mat.ax.collections and len(points.get_offsets()) == 2
    mesh = mat.heatmap(np.zeros(10), np.zeros(10), clip_to="competition")
    assert mesh.get_clip_path() is not None
    with pytest.raises(ValueError):
        mat.heatmap([0], [0], clip_to="competiton")


def test_clipped_heatmap_ignores_out_of_bounds_points():
    mat = WrestlingMat("ncaa")
    mesh = mat.heatmap([0, 16.5], [0, 0], bins=2, clip_to="competition")
    assert mesh.get_array().sum() == 1
