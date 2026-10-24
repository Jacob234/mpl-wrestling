"""Match data: events, scoring, position (top/bottom/neutral) and riding time.

Times are seconds elapsed since the start of the match, not the clock reading.
Use :meth:`Match.elapsed` to convert a period and clock reading.

Wrestlers are identified by corner colour: ``'red'`` and ``'green'`` in
folkstyle (green is the home wrestler), ``'red'`` and ``'blue'`` internationally.
"""
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional


class EventType(Enum):
    TAKEDOWN = "takedown"
    ESCAPE = "escape"
    REVERSAL = "reversal"
    NEAR_FALL = "near_fall"
    PENALTY = "penalty"              # `wrestler` is the offender; points go to the opponent
    STALL_WARNING = "stall_warning"  # `wrestler` is the offender; no points
    POSITION = "position"            # sets top/bottom/neutral, e.g. the choice at a period start
    POINTS = "points"                # anything else that scores, e.g. international exposure or step-out
    FALL = "fall"                    # pin; ends the match

    @classmethod
    def from_string(cls, value):
        if isinstance(value, cls):
            return value
        aliases = {"td": "takedown", "e": "escape", "esc": "escape", "r": "reversal", "rev": "reversal",
                   "nf": "near_fall", "near fall": "near_fall", "nearfall": "near_fall", "pen": "penalty",
                   "stall": "stall_warning", "pin": "fall"}
        cleaned = value.strip().lower()
        try:
            return cls(aliases.get(cleaned, cleaned))
        except ValueError:
            raise ValueError(f"'{value}' is not a known event type. "
                             f"Valid: {[e.value for e in cls]}") from None


SHORT_LABELS = {EventType.TAKEDOWN: "T", EventType.ESCAPE: "E", EventType.REVERSAL: "R",
                EventType.NEAR_FALL: "N", EventType.PENALTY: "P", EventType.STALL_WARNING: "S",
                EventType.POSITION: "", EventType.POINTS: "+", EventType.FALL: "F"}


@dataclass(frozen=True)
class Ruleset:
    name: str
    period_lengths: tuple            # seconds, regulation only
    default_points: dict             # EventType -> points; missing types need explicit points
    riding_time: bool = False
    riding_time_threshold: float = 60.0
    corners: tuple = ("red", "green")


# Values checked against the 2025-27 NCAA rules book and the NFHS 2024-25 rule changes.
NCAA_RULES = Ruleset(
    name="ncaa",
    period_lengths=(180, 120, 120),
    default_points={EventType.TAKEDOWN: 3, EventType.ESCAPE: 1, EventType.REVERSAL: 2},
    riding_time=True,
)
NFHS_RULES = Ruleset(
    name="nfhs",
    period_lengths=(120, 120, 120),
    default_points={EventType.TAKEDOWN: 3, EventType.ESCAPE: 1, EventType.REVERSAL: 2},
)
# International scoring depends on the move (2, 4 or 5 for takedowns and throws),
# so every scoring event needs explicit points. Not verified against the current UWW rules.
UWW_RULES = Ruleset(
    name="uww",
    period_lengths=(180, 180),
    default_points={},
    corners=("red", "blue"),
)
RULESETS = {"ncaa": NCAA_RULES, "college": NCAA_RULES, "folkstyle": NCAA_RULES,
            "nfhs": NFHS_RULES, "high_school": NFHS_RULES, "hs": NFHS_RULES,
            "uww": UWW_RULES, "international": UWW_RULES, "freestyle": UWW_RULES, "greco": UWW_RULES}


def get_ruleset(rules):
    if isinstance(rules, Ruleset):
        return rules
    try:
        return RULESETS[rules.strip().lower()]
    except KeyError:
        raise ValueError(f"Unknown ruleset '{rules}'. Valid: {sorted(set(RULESETS))}") from None


def format_clock(seconds):
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60}:{seconds % 60:02d}"


def parse_clock(clock):
    """'1:23' or 83 -> 83.0 seconds."""
    if isinstance(clock, (int, float)):
        return float(clock)
    minutes, _, secs = str(clock).partition(":")
    return float(minutes) * 60 + float(secs) if secs else float(minutes)


@dataclass
class Event:
    time: float
    kind: EventType
    wrestler: str
    points: Optional[int] = None
    position: Optional[str] = None   # POSITION events: 'top', 'bottom' or 'neutral' for `wrestler`
    x: Optional[float] = None        # where it happened on the mat, in the mat's units
    y: Optional[float] = None
    note: str = ""

    def __post_init__(self):
        self.kind = EventType.from_string(self.kind)
        self.time = float(self.time)

    @property
    def has_location(self):
        return self.x is not None and self.y is not None

    def to_dict(self):
        d = asdict(self)
        d["kind"] = self.kind.value
        return {k: v for k, v in d.items() if v not in (None, "")}


@dataclass
class Match:
    wrestlers: dict                          # corner -> display name
    events: list = field(default_factory=list)
    rules: Ruleset = NCAA_RULES
    colors: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    DEFAULT_COLORS = {"red": "#c8102e", "green": "#00843d", "blue": "#1f4e9c"}

    def __post_init__(self):
        self.rules = get_ruleset(self.rules)
        self.events = [e if isinstance(e, Event) else Event(**e) for e in self.events]
        self.colors = {c: self.colors.get(c, self.DEFAULT_COLORS.get(c, "grey")) for c in self.wrestlers}
        self.validate()

    # ------------------------------------------------------------------ building
    @property
    def corners(self):
        return tuple(self.wrestlers)

    def opponent(self, corner):
        a, b = self.corners
        return b if corner == a else a

    @property
    def regulation_length(self):
        return float(sum(self.rules.period_lengths))

    def period_starts(self):
        starts, t = [], 0.0
        for length in self.rules.period_lengths:
            starts.append(t)
            t += length
        return starts

    def elapsed(self, period, clock, clock_counts_down=True):
        """Seconds since the match started for a period (1-based) and clock reading."""
        lengths = self.rules.period_lengths
        if not 1 <= period <= len(lengths):
            raise ValueError(f"period must be 1..{len(lengths)} under {self.rules.name} rules")
        clock = parse_clock(clock)
        into_period = lengths[period - 1] - clock if clock_counts_down else clock
        return self.period_starts()[period - 1] + into_period

    def add(self, kind, wrestler, time=None, period=None, clock=None, **kwargs):
        """Add an event by elapsed ``time`` or by ``period`` and ``clock``. Returns the event."""
        if time is None:
            if period is None or clock is None:
                raise ValueError("give either time, or period and clock")
            time = self.elapsed(period, clock)
        event = Event(time=time, kind=kind, wrestler=wrestler, **kwargs)
        self._validate_event(event)
        self.events.append(event)
        return event

    def validate(self):
        for event in self.events:
            self._validate_event(event)

    def _validate_event(self, event):
        if event.wrestler not in self.wrestlers:
            raise ValueError(f"Event wrestler '{event.wrestler}' is not one of {list(self.wrestlers)}")
        if event.kind is EventType.POSITION and event.position not in ("top", "bottom", "neutral"):
            raise ValueError("POSITION events need position='top', 'bottom' or 'neutral'")
        if event.kind is EventType.NEAR_FALL and self.rules.name in ("ncaa", "nfhs") \
                and event.points not in (2, 3, 4):
            raise ValueError("Folkstyle near falls are worth 2, 3 or 4 points; pass points=")
        if event.kind in (EventType.PENALTY, EventType.POINTS) and event.points is None:
            raise ValueError(f"{event.kind.value} events need explicit points")
        if self.points_for(event) is None:
            raise ValueError(f"{event.kind.value} has no default value under {self.rules.name} rules; "
                             f"pass points=")

    # ------------------------------------------------------------------ scoring
    def sorted_events(self):
        return sorted(self.events, key=lambda e: e.time)

    def points_for(self, event):
        if event.kind in (EventType.POSITION, EventType.STALL_WARNING, EventType.FALL):
            return 0
        if event.points is not None:
            return event.points
        return self.rules.default_points.get(event.kind)

    def scorer(self, event):
        """Who the event's points go to (the opponent, for penalties)."""
        return self.opponent(event.wrestler) if event.kind is EventType.PENALTY else event.wrestler

    def fall(self):
        """The FALL event, if the match ended in a pin."""
        return next((e for e in self.sorted_events() if e.kind is EventType.FALL), None)

    @property
    def end_time(self):
        fall = self.fall()
        if fall is not None:
            return fall.time
        last = max((e.time for e in self.events), default=0.0)
        return max(self.regulation_length, last)

    def score_progression(self, include_riding_time=True):
        """List of ``(time, {corner: score}, event_or_None)`` after each scoring change.

        Starts at 0-0 at time 0. The riding-time point, if earned, appears at the end of
        regulation with event None.
        """
        score = {c: 0 for c in self.corners}
        rows = [(0.0, dict(score), None)]
        riding_added = False
        riding = self.riding_time() if include_riding_time and self.rules.riding_time else None
        for event in self.sorted_events():
            if event.time > self.end_time:
                break
            if riding and not riding_added and event.time > self.regulation_length:
                riding_added = self._apply_riding_point(score, riding, rows)
            pts = self.points_for(event)
            if pts:
                score[self.scorer(event)] += pts
                rows.append((event.time, dict(score), event))
            if event.kind is EventType.FALL:
                return rows
        if riding and not riding_added:
            self._apply_riding_point(score, riding, rows)
        return rows

    def _apply_riding_point(self, score, riding, rows):
        if riding["point_to"] is not None:
            score[riding["point_to"]] += 1
            rows.append((self.regulation_length, dict(score), None))
        return True

    def final_score(self):
        return self.score_progression()[-1][1]

    def winner(self):
        fall = self.fall()
        if fall is not None:
            return fall.wrestler
        score = self.final_score()
        a, b = self.corners
        return None if score[a] == score[b] else (a if score[a] > score[b] else b)

    def result(self):
        """Short result string such as 'red dec. green 7-3' or 'green fall red 4:12'."""
        win = self.winner()
        if win is None:
            return "draw"
        lose = self.opponent(win)
        if self.fall() is not None:
            return f"{win} fall {lose} {format_clock(self.fall().time)}"
        s = self.final_score()
        margin = s[win] - s[lose]
        kind = "dec." if margin < 8 else ("maj. dec." if margin < 15 else "tech. fall")
        return f"{win} {kind} {lose} {s[win]}-{s[lose]}"

    # ------------------------------------------------------------------ position and riding time
    def position_timeline(self):
        """Segments ``(start, end, top_corner)`` where top_corner is None for neutral.

        Each period starts neutral; a POSITION event at the period start applies the
        choice. Takedowns and reversals put the scorer on top, escapes return to neutral.
        """
        segments = []
        boundaries = self.period_starts()
        end = self.end_time
        changes = []  # (time, order, top_corner) - period resets sort before events at the same time
        for start in boundaries:
            changes.append((start, 0, None))
        for e in self.sorted_events():
            top = "keep"
            if e.kind in (EventType.TAKEDOWN, EventType.REVERSAL):
                top = e.wrestler
            elif e.kind is EventType.ESCAPE:
                top = None
            elif e.kind is EventType.POSITION:
                top = {"top": e.wrestler, "bottom": self.opponent(e.wrestler), "neutral": None}[e.position]
            if top != "keep":
                changes.append((e.time, 1, top))
        changes.sort(key=lambda c: (c[0], c[1]))

        current, since = None, 0.0
        for t, _, top in changes:
            if t > end:
                break
            if t > since:
                segments.append((since, t, current))
            current, since = top, t
        if end > since:
            segments.append((since, end, current))
        return segments

    def riding_time(self):
        """Riding time in regulation: seconds on top per corner, the net advantage, and who earns the point."""
        on_top = {c: 0.0 for c in self.corners}
        reg = self.regulation_length
        for start, end, top in self.position_timeline():
            if top is not None and start < reg:
                on_top[top] += min(end, reg) - start
        a, b = self.corners
        net = on_top[a] - on_top[b]
        leader = a if net > 0 else (b if net < 0 else None)
        earned = self.rules.riding_time and abs(net) >= self.rules.riding_time_threshold
        return {"on_top": on_top, "leader": leader, "advantage": abs(net),
                "point_to": leader if earned else None}

    # ------------------------------------------------------------------ io
    def to_dict(self):
        return {"wrestlers": self.wrestlers, "rules": self.rules.name, "colors": self.colors,
                "metadata": self.metadata, "events": [e.to_dict() for e in self.sorted_events()]}

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        data["events"] = [Event(**e) for e in data.get("events", [])]
        return cls(**data)

    def to_json(self, path=None, indent=2):
        text = json.dumps(self.to_dict(), indent=indent)
        if path is not None:
            with open(path, "w") as fh:
                fh.write(text)
        return text

    @classmethod
    def from_json(cls, path_or_text):
        text = str(path_or_text)
        if not text.lstrip().startswith("{"):
            with open(path_or_text) as fh:
                text = fh.read()
        return cls.from_dict(json.loads(text))
