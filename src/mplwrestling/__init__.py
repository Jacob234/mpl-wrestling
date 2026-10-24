"""mplwrestling: matplotlib visualizations for wrestling."""
from importlib import resources

from .charts import match_summary, plot_events, position_strip, score_timeline
from .mat import DIMENSIONS, MatStyle, WrestlingMat
from .match import NCAA_RULES, NFHS_RULES, UWW_RULES, Event, EventType, Match, Ruleset, get_ruleset
from .units import MAT_UNITS, ureg

__version__ = "0.1.0"

__all__ = ["WrestlingMat", "MatStyle", "DIMENSIONS", "Match", "Event", "EventType", "Ruleset",
           "NCAA_RULES", "NFHS_RULES", "UWW_RULES", "get_ruleset", "score_timeline", "position_strip",
           "plot_events", "match_summary", "ureg", "MAT_UNITS", "load_sample_match"]


def load_sample_match():
    """A made-up NCAA dual-meet match bundled with the package, for trying things out."""
    path = resources.files(__package__).joinpath("data/sample_match.json")
    return Match.from_json(path.read_text())
