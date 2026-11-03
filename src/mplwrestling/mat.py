"""The wrestling mat: rule-book dimensions, unit handling and drawing.

Coordinate system
-----------------
The origin is the centre of the mat. +x runs parallel to the scorer's table
and +y points away from it, so the table sits below the mat (negative y).
All coordinates are in the units the mat was created with.
"""
from enum import Enum

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import patches
from matplotlib.collections import PatchCollection

from .units import MAT_UNITS, as_unit, ureg


class MatStyle(Enum):
    NCAA = "ncaa"
    HIGH_SCHOOL = "high_school"
    INTERNATIONAL = "international"
    CUSTOM = "custom"

    @classmethod
    def from_string(cls, style_string):
        """Convert the many names people use for a style into a MatStyle."""
        international_version = ("international", "greco", "greco-roman", "grecoroman", "greco roman",
                                 "free style", "freestyle", "olympic", "olympics", "uww")
        ncaa_version = ("ncaa", "college", "collegiate", "american", "folkstyle", "national")
        high_school_version = ("high school", "highschool", "high_school", "hs", "nfhs")

        cleaned = style_string.strip().lower()
        if cleaned in ncaa_version:
            return cls.NCAA
        elif cleaned in high_school_version:
            return cls.HIGH_SCHOOL
        elif cleaned in international_version:
            return cls.INTERNATIONAL
        else:
            raise ValueError(
                f"'{style_string}' is not a recognized mat style. "
                f"Valid options include: 'ncaa', 'high_school', 'international' "
                f"(or aliases like 'freestyle', 'greco-roman', 'folkstyle'). "
                f"For custom dimensions, use WrestlingMat.custom()"
            )


# Sources (checked October 2026):
#   NCAA:  2025-26 and 2026-27 NCAA Wrestling Rules Book, Rule 1 Section 1.
#   NFHS:  "Major differences between high school and college rules" (2014-15)
#          and the NFHS 2024-25 rule changes (10-foot circle made optional).
#   UWW:   UWW mat as summarised by the Western Australian sports dimensions guide.
# NFHS starting-line sizes were not confirmed from a primary source; they are
# assumed to match the NCAA's.
DIMENSIONS = {
    MatStyle.NCAA: {
        "measurements": {
            'competition_radius': 16 * ureg.feet,        # circle 32 to 42 ft across; 32 is the minimum
            'protection_width': 5 * ureg.feet,           # minimum matted area outside the circle
            'boundary_line_width': 2 * ureg.inch,        # part of the circle, in bounds
            'center_circle_radius': None,                # not required in college
            'passivity_zone_radius': None,
            'starting_line_length': 3 * ureg.feet,
            'starting_line_gap': 10 * ureg.inch,         # distance between the two down lines
            'starting_line_width': 1 * ureg.inch,
        },
        'units': 'feet',
    },
    MatStyle.HIGH_SCHOOL: {
        "measurements": {
            'competition_radius': 14 * ureg.feet,        # 28 ft minimum circle
            'protection_width': 5 * ureg.feet,           # "approximately 5 feet"
            'boundary_line_width': 2 * ureg.inch,
            'center_circle_radius': 5 * ureg.feet,       # the 10-foot circle, optional since 2024-25
            'passivity_zone_radius': None,
            'starting_line_length': 3 * ureg.feet,
            'starting_line_gap': 10 * ureg.inch,
            'starting_line_width': 1 * ureg.inch,
        },
        'units': 'feet',
    },
    MatStyle.INTERNATIONAL: {
        "measurements": {
            'competition_radius': 4.5 * ureg.meters,     # 9 m circle, red zone included
            'protection_width': 1.5 * ureg.meters,
            'boundary_line_width': None,                 # the red zone marks the edge instead
            'center_circle_radius': 0.5 * ureg.meters,   # 1 m central circle
            'passivity_zone_radius': 3.5 * ureg.meters,  # inner edge of the 1 m red zone
            'starting_line_length': None,
            'starting_line_gap': None,
            'starting_line_width': None,
        },
        'units': 'meters',
    },
}

MEASUREMENT_NAMES = tuple(DIMENSIONS[MatStyle.NCAA]["measurements"])

THEMES = {
    MatStyle.NCAA: dict(mat_color='#7a1f2b', protection_color='#5c1720', line_color='white',
                        home_color='#00843d', visitor_color='#c8102e', center_line_color='white'),
    MatStyle.HIGH_SCHOOL: dict(mat_color='#1f3f7a', protection_color='#173061', line_color='white',
                               home_color='#00843d', visitor_color='#c8102e', center_line_color='white'),
    MatStyle.INTERNATIONAL: dict(mat_color='#f2c14e', protection_color='#1f4e9c', line_color='white',
                                 passivity_color='#d9412b', center_line_color='#d9412b',
                                 home_color='#c8102e', visitor_color='#0b2a66'),
}
THEMES[MatStyle.CUSTOM] = dict(THEMES[MatStyle.NCAA], passivity_color='#d9412b')
CLIP_CHOICES = ('outer', 'competition')


class WrestlingMat:
    DIMENSIONS = DIMENSIONS

    def __init__(self, style=MatStyle.NCAA, units="feet", **overrides):
        """
        Initialize a wrestling mat visualization.
        Defaults to: ncaa and feet

        Parameters
        ----------
        style : str or MatStyle
            'ncaa', 'high_school', or 'international' (or an alias such as 'folkstyle').
        units : str
            Any pint length unit ('feet', 'meters', 'inches', ...) or 'mat_units',
            which scales every length so the competition circle has radius 1.
        **overrides
            Replace individual measurements, e.g. ``competition_radius=21 * ureg.feet``
            for a 42 ft NCAA circle. Plain numbers are read in the style's native units.
        """
        if isinstance(style, str):
            self.style = MatStyle.from_string(style)
        elif isinstance(style, MatStyle):
            self.style = style
        else:
            raise TypeError("style must be a string or MatStyle enum")
        if self.style is MatStyle.CUSTOM and not hasattr(self, "_custom_spec"):
            raise ValueError("Use WrestlingMat.custom() to build a custom mat.")

        unknown = set(overrides) - set(MEASUREMENT_NAMES)
        if unknown:
            raise TypeError(f"Unknown measurement(s): {sorted(unknown)}. "
                            f"Valid names: {list(MEASUREMENT_NAMES)}")
        self._overrides = overrides
        self.units = units
        self._set_dimensions()

        self.fig = None
        self.ax = None

    @classmethod
    def custom(cls, competition_radius, protection_width, units="feet", native_units=None, **measurements):
        """Build a mat with your own dimensions, e.g. a youth mat.

        Numbers without pint units are read in ``native_units`` (default: ``units``,
        or feet when ``units`` is 'mat_units'). Measurements you leave out are None,
        so that feature is not drawn.
        """
        unknown = set(measurements) - set(MEASUREMENT_NAMES)
        if unknown:
            raise TypeError(f"Unknown measurement(s): {sorted(unknown)}. "
                            f"Valid names: {list(MEASUREMENT_NAMES)}")
        native = native_units or ("feet" if units == MAT_UNITS else units)
        spec = {name: None for name in MEASUREMENT_NAMES}
        spec.update(measurements, competition_radius=competition_radius, protection_width=protection_width)
        mat = cls.__new__(cls)
        mat._custom_spec = {"measurements": spec, "units": native}
        mat.__init__(MatStyle.CUSTOM, units=units)
        return mat

    # ------------------------------------------------------------------ dimensions
    def _spec(self):
        if self.style is MatStyle.CUSTOM:
            return self._custom_spec
        return self.DIMENSIONS[self.style]

    def _set_dimensions(self):
        """Convert every measurement to ``self.units``.

        ``self.dimensions`` keeps pint Quantities (or None); ``self.dims`` holds the
        plain floats that matplotlib needs.
        """
        spec = self._spec()
        native = as_unit(spec["units"])
        measurements = {**spec["measurements"], **self._overrides}
        # pint does not attach to a numpy array built from a list of Quantities,
        # so convert one value at a time and keep the names.
        quantities = {}
        for name, value in measurements.items():
            if value is None:
                quantities[name] = None
            elif isinstance(value, ureg.Quantity):
                quantities[name] = value
            else:
                quantities[name] = value * native

        if self.units == MAT_UNITS:
            radius = quantities['competition_radius']
            self.dimensions = {name: None if q is None else (q / radius).to(ureg.dimensionless)
                               for name, q in quantities.items()}
        else:
            target = as_unit(self.units)
            self.dimensions = {name: None if q is None else q.to(target)
                               for name, q in quantities.items()}
        self.dims = {name: None if q is None else float(q.magnitude) for name, q in self.dimensions.items()}

    @property
    def radius(self):
        """Radius of the competition circle (the in-bounds area)."""
        return self.dims['competition_radius']

    @property
    def outer_radius(self):
        """Distance from the centre to the edge of the protection area."""
        return self.dims['competition_radius'] + self.dims['protection_width']

    def __repr__(self):
        return f"WrestlingMat(style={self.style.value!r}, units={self.units!r})"

    # ------------------------------------------------------------------ geometry helpers
    def in_bounds(self, x, y):
        """True where (x, y) lies inside the competition circle (boundary line included)."""
        x, y = np.asarray(x, float), np.asarray(y, float)
        return np.hypot(x, y) <= self.radius

    def default_ring_edges(self):
        """Radii that split the mat into centre, middle, edge and out-of-bounds rings."""
        r = self.radius
        if self.dims['passivity_zone_radius'] is not None:
            p = self.dims['passivity_zone_radius']
            return [0.0, p / 2, p, r, self.outer_radius]
        return [0.0, r / 3, 2 * r / 3, r, self.outer_radius]

    def zone_of(self, x, y, ring_edges=None, sectors=8, sector_offset=0.0):
        """Assign each point to a mat zone.

        Returns ``(ring, sector)`` integer arrays. Ring 0 is the centre and is not
        split into sectors (its sector is -1). Sectors are counted counter-clockwise
        from +x, starting at ``sector_offset`` degrees. Points beyond the last edge
        go in the last ring.
        """
        edges = np.asarray(ring_edges if ring_edges is not None else self.default_ring_edges(), float)
        x, y = np.asarray(x, float), np.asarray(y, float)
        r = np.hypot(x, y)
        # the boundary line is in bounds, so a point exactly on the circle belongs inside it
        r = np.where(np.isclose(r, self.radius), np.nextafter(self.radius, 0), r)
        ring = np.clip(np.searchsorted(edges, r, side='right') - 1, 0, len(edges) - 2)
        angle = (np.degrees(np.arctan2(y, x)) - sector_offset) % 360
        sector = (angle // (360 / sectors)).astype(int)
        sector = np.where(ring == 0, -1, sector)
        return ring, sector

    # ------------------------------------------------------------------ drawing
    def _theme(self, overrides):
        theme = dict(THEMES[self.style])
        theme.update({k: v for k, v in overrides.items() if v is not None})
        return theme

    def draw(self, ax=None, figsize=(7, 7), mat_color=None, protection_color=None, line_color=None,
             home_side='left', show_center_circle=True, show_starting_lines=True, pad=0.03):
        """
        Draw the wrestling mat to scale.

        Parameters
        ----------
        ax : matplotlib axes, optional
            If None, creates a new figure and axes.
        mat_color, protection_color, line_color : color, optional
            Override the style's theme colors.
        home_side : 'left' or 'right'
            Which end of the starting box carries the home (green) line.
        show_center_circle, show_starting_lines : bool
            Turn off the optional markings.

        Returns
        -------
        fig, ax : matplotlib figure and axes
        """
        if home_side not in ('left', 'right'):
            raise ValueError(f"home_side must be 'left' or 'right', not {home_side!r}")
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        else:
            fig = ax.figure
        theme = self._theme(dict(mat_color=mat_color, protection_color=protection_color, line_color=line_color))
        d = self.dims
        r, outer = self.radius, self.outer_radius
        z = 0.5  # keep the mat underneath anything the user plots

        ax.add_patch(patches.Rectangle((-outer, -outer), 2 * outer, 2 * outer, facecolor=theme['protection_color'],
                                       edgecolor='none', zorder=z))
        ax.add_patch(patches.Circle((0, 0), r, facecolor=theme['mat_color'], edgecolor='none', zorder=z))

        if d['passivity_zone_radius'] is not None:
            p = d['passivity_zone_radius']
            ax.add_patch(patches.Wedge((0, 0), r, 0, 360, width=r - p, facecolor=theme['passivity_color'],
                                       edgecolor='none', zorder=z))
        if self.style is MatStyle.INTERNATIONAL:
            self._draw_corners(ax, theme, z)

        if d['boundary_line_width']:
            ax.add_patch(patches.Wedge((0, 0), r, 0, 360, width=d['boundary_line_width'],
                                       facecolor=theme['line_color'], edgecolor='none', zorder=z))

        if show_center_circle and d['center_circle_radius']:
            c = d['center_circle_radius']
            if self.style is MatStyle.INTERNATIONAL:
                ax.add_patch(patches.Circle((0, 0), c, facecolor='none', edgecolor=theme['center_line_color'],
                                            linewidth=2, zorder=z))
            else:
                width = d['boundary_line_width'] or 0.01 * r
                ax.add_patch(patches.Wedge((0, 0), c, 0, 360, width=width, facecolor=theme['center_line_color'],
                                           edgecolor='none', zorder=z))

        if show_starting_lines and all(d[k] for k in ('starting_line_length', 'starting_line_gap',
                                                     'starting_line_width')):
            self._draw_starting_lines(ax, theme, home_side, z)

        lim = outer * (1 + pad)
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.set_aspect('equal')
        ax.axis('off')
        ax._mplwrestling_mat = self   # lets plot_events tell a drawn mat from other patches
        self.fig, self.ax = fig, ax
        return fig, ax

    def _draw_starting_lines(self, ax, theme, home_side, z):
        """Two down lines closed at each end by a green (home) and a red (visitor) neutral line."""
        d = self.dims
        length, gap, w = d['starting_line_length'], d['starting_line_gap'], d['starting_line_width']
        half_l, half_g = length / 2, gap / 2
        line = theme['line_color']
        rects = [
            patches.Rectangle((-half_l, half_g), length, w),          # upper down line
            patches.Rectangle((-half_l, -half_g - w), length, w),     # lower down line
        ]
        ax.add_collection(PatchCollection(rects, facecolor=line, edgecolor='none', zorder=z))
        home_x = -half_l - w if home_side == 'left' else half_l
        visitor_x = half_l if home_side == 'left' else -half_l - w
        for x0, color in ((home_x, theme['home_color']), (visitor_x, theme['visitor_color'])):
            ax.add_patch(patches.Rectangle((x0, -half_g - w), w, gap + 2 * w, facecolor=color,
                                           edgecolor='none', zorder=z))

    def _draw_corners(self, ax, theme, z):
        """International mats mark two diagonally opposite corners red and blue."""
        outer, prot = self.outer_radius, self.dims['protection_width']
        size = prot * 0.8
        for sx, sy, color in ((-1, 1, theme['home_color']), (1, -1, theme['visitor_color'])):
            corner = np.array([sx * outer, sy * outer])
            tri = [corner, corner - [sx * size, 0], corner - [0, sy * size]]
            ax.add_patch(patches.Polygon(tri, closed=True, facecolor=color, edgecolor='none', zorder=z))

    # ------------------------------------------------------------------ data layers
    def _require_ax(self, ax):
        if ax is not None:
            return ax
        if self.ax is None:
            self.draw()
        return self.ax

    def scatter(self, x, y, ax=None, **kwargs):
        """``ax.scatter`` on top of the mat."""
        ax = self._require_ax(ax)
        kwargs.setdefault('zorder', 3)
        return ax.scatter(x, y, **kwargs)

    def heatmap(self, x, y, ax=None, bins=24, cmap='magma', alpha=0.75, clip_to='outer', **kwargs):
        """2-D histogram of positions, clipped to the circle (``clip_to='competition'``) or the mat."""
        if clip_to not in CLIP_CHOICES:
            raise ValueError(f"clip_to must be one of {CLIP_CHOICES}, not {clip_to!r}")
        ax = self._require_ax(ax)
        outer = self.outer_radius
        x, y = np.asarray(x, float), np.asarray(y, float)
        if clip_to == 'competition':
            keep = self.in_bounds(x, y)   # drop outside points so they don't tint edge bins
            x, y = x[keep], y[keep]
        counts, xe, ye = np.histogram2d(x, y, bins=bins, range=[[-outer, outer], [-outer, outer]])
        counts = np.ma.masked_equal(counts.T, 0)
        mesh = ax.pcolormesh(xe, ye, counts, cmap=cmap, alpha=alpha, zorder=2, **kwargs)
        clip_r = self.radius if clip_to == 'competition' else None
        if clip_r is not None:
            mesh.set_clip_path(patches.Circle((0, 0), clip_r, transform=ax.transData))
        return mesh

    def zone_heatmap(self, x, y, ax=None, ring_edges=None, sectors=8, sector_offset=0.0, cmap='viridis',
                     alpha=0.8, annotate=True, fmt='{:d}', normalize=False, include_out_of_bounds=False):
        """Count points per mat zone and shade each zone.

        ``normalize=True`` shows shares of all points instead of counts.
        Returns ``(counts, wedges)`` where counts is a ``{(ring, sector): value}`` dict.
        """
        ax = self._require_ax(ax)
        edges = list(ring_edges if ring_edges is not None else self.default_ring_edges())
        n_rings = len(edges) - 1 if include_out_of_bounds else len(edges) - 2
        ring, sector = self.zone_of(x, y, edges, sectors, sector_offset)

        keys = [(0, -1)] + [(i, s) for i in range(1, n_rings) for s in range(sectors)]
        counts = {k: int(np.sum((ring == k[0]) & (sector == k[1]))) for k in keys}
        total = sum(counts.values())   # shares are of the points shown, so they add up to 100%
        values = {k: (v / total if (normalize and total) else v) for k, v in counts.items()}
        vmax = max(values.values()) or 1
        colormap = plt.get_cmap(cmap)

        step = 360 / sectors
        wedges = []
        for (i, s), v in values.items():
            r_in, r_out = edges[i], edges[i + 1]
            theta1, theta2 = (0, 360) if s == -1 else (sector_offset + s * step, sector_offset + (s + 1) * step)
            wedge = patches.Wedge((0, 0), r_out, theta1, theta2, width=r_out - r_in,
                                  facecolor=colormap(v / vmax), edgecolor='white', linewidth=0.8,
                                  alpha=alpha, zorder=2)
            ax.add_patch(wedge)
            wedges.append(wedge)
            if annotate:
                if s == -1:
                    tx, ty = 0, 0
                else:
                    mid = np.radians((theta1 + theta2) / 2)
                    rr = (r_in + r_out) / 2
                    tx, ty = rr * np.cos(mid), rr * np.sin(mid)
                label = f"{v:.0%}" if normalize else fmt.format(v)
                ax.text(tx, ty, label, ha='center', va='center', fontsize=8, color='white', zorder=4,
                        fontweight='bold')
        return values, wedges
