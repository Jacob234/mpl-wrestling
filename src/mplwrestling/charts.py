"""Match charts: score timeline, position strip, events on the mat, and a one-page summary."""
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MultipleLocator

from .mat import WrestlingMat
from .match import SHORT_LABELS, EventType, format_clock

EVENT_MARKERS = {EventType.TAKEDOWN: "o", EventType.ESCAPE: "^", EventType.REVERSAL: "s",
                 EventType.NEAR_FALL: "*", EventType.PENALTY: "X", EventType.STALL_WARNING: "x",
                 EventType.POINTS: "D", EventType.FALL: "P", EventType.POSITION: "."}
NEUTRAL_COLOR = "#c9c9c9"


def _event_label(match, event):
    pts = match.points_for(event)
    base = SHORT_LABELS[event.kind]
    return f"{base}{pts}" if pts else base


def _format_time_axis(ax, match):
    ax.xaxis.set_major_locator(MultipleLocator(60))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: format_clock(v)))
    ax.set_xlim(0, match.end_time)


def _period_lines(ax, match, label=True):
    starts = match.period_starts()
    for i, start in enumerate(starts):
        if i:
            ax.axvline(start, color="0.6", linestyle="--", linewidth=0.8, zorder=0)
        if label:
            ax.text(start + 3, 1.0, f"P{i + 1}", transform=ax.get_xaxis_transform(), va="bottom",
                    ha="left", fontsize=8, color="0.4")
    if match.end_time > match.regulation_length:
        ax.axvline(match.regulation_length, color="0.3", linewidth=1, zorder=0)


def score_timeline(match, ax=None, annotate=True, figsize=(10, 4)):
    """Step chart of both wrestlers' scores over the match, with each scoring event labelled."""
    if ax is None:
        _, ax = plt.subplots(figsize=figsize)
    rows = match.score_progression()
    end = match.end_time
    for corner in match.corners:
        times = [r[0] for r in rows] + [end]
        scores = [r[1][corner] for r in rows] + [rows[-1][1][corner]]
        ax.step(times, scores, where="post", color=match.colors[corner], linewidth=2.2,
                label=f"{match.wrestlers[corner]} ({rows[-1][1][corner]})")
    if annotate:
        for t, score, event in rows[1:]:
            corner = match.scorer(event) if event is not None else _riding_corner(match)
            label = _event_label(match, event) if event is not None else "RT1"
            ax.annotate(label, (t, score[corner]), xytext=(0, 6), textcoords="offset points",
                        ha="center", fontsize=8, color=match.colors[corner], fontweight="bold")
    fall = match.fall()
    if fall is not None:
        ax.axvline(fall.time, color=match.colors[fall.wrestler], linewidth=2, alpha=0.6)
        ax.annotate("FALL", (fall.time, 1.0), xycoords=("data", "axes fraction"), xytext=(-4, -12),
                    textcoords="offset points", ha="right", fontsize=9, fontweight="bold",
                    color=match.colors[fall.wrestler])
    _period_lines(ax, match)
    _format_time_axis(ax, match)
    top = max(max(r[1].values()) for r in rows)
    ax.set_ylim(-0.5, top + 2)
    ax.yaxis.set_major_locator(MultipleLocator(max(1, round(top / 6))))
    ax.set_ylabel("Score")
    ax.set_xlabel("Match time")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    return ax


def _riding_corner(match):
    return match.riding_time()["point_to"]


def position_strip(match, ax=None, figsize=(10, 1.2), show_riding_time=True):
    """Horizontal bar showing who was on top: grey for neutral, the top wrestler's colour otherwise."""
    if ax is None:
        _, ax = plt.subplots(figsize=figsize)
    for start, end, top in match.position_timeline():
        color = NEUTRAL_COLOR if top is None else match.colors[top]
        ax.broken_barh([(start, end - start)], (0, 1), facecolors=color, edgecolor="white", linewidth=0.5)
    _period_lines(ax, match, label=False)
    _format_time_axis(ax, match)
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    handles = [Patch(color=NEUTRAL_COLOR, label="neutral")] + \
              [Patch(color=match.colors[c], label=f"{match.wrestlers[c]} on top") for c in match.corners]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.45), ncol=3, frameon=False,
              fontsize=8)
    if show_riding_time and match.rules.riding_time:
        rt = match.riding_time()
        if rt["leader"] is not None:
            text = f"Riding time: {match.wrestlers[rt['leader']]} +{format_clock(rt['advantage'])}"
            if rt["point_to"]:
                text += " (1 pt)"
            ax.set_title(text, fontsize=9, loc="right", color=match.colors[rt["leader"]])
    return ax


def plot_events(match, mat=None, ax=None, size=140, legend=True, label=True):
    """Plot every event that has an (x, y) location on a mat, coloured by who scored."""
    if mat is None:
        mat = WrestlingMat(match.rules.name if match.rules.name != "nfhs" else "high_school")
    if ax is None:
        mat.draw()
        ax = mat.ax
    elif not ax.patches:
        mat.draw(ax=ax)
    located = [e for e in match.sorted_events() if e.has_location]
    for e in located:
        corner = match.scorer(e)
        ax.scatter(e.x, e.y, s=size, marker=EVENT_MARKERS[e.kind], color=match.colors[corner],
                   edgecolor="white", linewidth=1.2, zorder=3)
        if label:
            ax.annotate(_event_label(match, e), (e.x, e.y), xytext=(7, 5), textcoords="offset points",
                        fontsize=8, color="white", fontweight="bold", zorder=4)
    if legend and located:
        kinds = sorted({e.kind for e in located}, key=lambda k: list(EventType).index(k))
        handles = [Line2D([], [], linestyle="", marker=EVENT_MARKERS[k], markersize=8, color="0.25",
                          label=k.value.replace("_", " ")) for k in kinds]
        handles += [Line2D([], [], linestyle="", marker="o", markersize=8, color=match.colors[c],
                           label=match.wrestlers[c]) for c in match.corners]
        ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False, fontsize=8)
    return ax


def match_summary(match, mat=None, figsize=(13, 7), title=None):
    """One figure: events on the mat (left), score timeline and position strip (right)."""
    fig = plt.figure(figsize=figsize, layout="constrained")
    grid = fig.add_gridspec(2, 2, width_ratios=[1, 1.6], height_ratios=[3, 1])
    ax_mat = fig.add_subplot(grid[:, 0])
    ax_score = fig.add_subplot(grid[0, 1])
    ax_pos = fig.add_subplot(grid[1, 1], sharex=ax_score)
    plot_events(match, mat=mat, ax=ax_mat, legend=False)
    score_timeline(match, ax=ax_score)
    position_strip(match, ax=ax_pos)
    ax_score.set_xlabel("")
    if title is None:
        a, b = match.corners
        bits = [match.metadata.get("weight"), match.metadata.get("event")]
        title = f"{match.wrestlers[a]} vs {match.wrestlers[b]}"
        extra = " · ".join(str(x) for x in bits if x)
        title += (f"  ·  {extra}" if extra else "") + f"\n{match.result()}"
    fig.suptitle(title, fontsize=13)
    return fig
