import matplotlib
matplotlib.use("Agg")

import pytest

import mplwrestling as mw
from mplwrestling import Event, EventType, Match


def simple_match(rules="ncaa"):
    return Match(wrestlers={"green": "Home", "red": "Visitor"}, rules=rules)


def test_elapsed_from_period_and_clock():
    m = simple_match()
    assert m.elapsed(1, "3:00") == 0
    assert m.elapsed(1, "0:30") == 150
    assert m.elapsed(2, "2:00") == 180
    assert m.elapsed(3, 60) == 360
    assert simple_match("nfhs").elapsed(2, "1:00") == 180
    with pytest.raises(ValueError):
        m.elapsed(4, "1:00")
    with pytest.raises(ValueError):
        m.elapsed(2, "2:30")          # period 2 is only two minutes


def test_default_points_and_penalty_goes_to_opponent():
    m = simple_match("nfhs")   # no riding time to muddy the totals
    m.add("td", "green", time=10)
    m.add("escape", "red", time=20)
    m.add("reversal", "red", time=30)
    m.add("penalty", "red", time=40, points=1)
    assert m.final_score() == {"green": 4, "red": 3}


def test_near_fall_validation():
    m = simple_match()
    with pytest.raises(ValueError):
        m.add("near_fall", "green", time=10)
    with pytest.raises(ValueError):
        m.add("near_fall", "green", time=10, points=5)
    m.add("near_fall", "green", time=10, points=4)


def test_match_needs_two_wrestlers():
    with pytest.raises(ValueError):
        Match(wrestlers={"red": "Solo"})


def test_negative_or_fractional_points_rejected():
    m = simple_match()
    with pytest.raises(ValueError):
        m.add("penalty", "red", time=5, points=-1)
    with pytest.raises(ValueError):
        m.add("near_fall", "green", time=5, points=2.5)


def test_rules_accept_mat_style_aliases():
    assert Match(wrestlers={"red": "A", "blue": "B"}, rules="Greco-Roman").rules is mw.UWW_RULES
    assert simple_match("high school").rules is mw.NFHS_RULES


def test_default_points_are_read_only():
    with pytest.raises(TypeError):
        mw.NCAA_RULES.default_points[EventType.TAKEDOWN] = 2


def test_tech_fall_ends_scoring():
    m = simple_match("nfhs")
    for t in (10, 20, 30, 40, 50):           # five takedowns, escapes in between
        m.add("takedown", "green", time=t)
        m.add("escape", "red", time=t + 5)
    m.add("near_fall", "green", time=60, points=4)   # 19-5, a 14-point lead
    m.add("takedown", "green", time=90)       # 22-5: the lead reaches 15 and the match ends
    m.add("takedown", "green", time=110)      # after the tech fall; must not count
    tech = m.tech_fall()
    assert tech.time == 90
    assert m.end_time == 90
    assert m.final_score() == {"green": 22, "red": 5}
    assert m.score_progression()[-1][2] is tech
    assert m.result() == "green tech. fall red 22-5 1:30"


def test_international_result_has_no_folkstyle_labels():
    m = Match(wrestlers={"red": "A", "blue": "B"}, rules="freestyle")
    m.add("points", "red", time=5, points=10)
    assert m.result() == "red def. blue 10-0"


def test_unknown_wrestler_and_event_type():
    m = simple_match()
    with pytest.raises(ValueError):
        m.add("takedown", "blue", time=1)
    with pytest.raises(ValueError):
        m.add("suplex", "green", time=1)


def test_international_needs_explicit_points():
    m = Match(wrestlers={"red": "A", "blue": "B"}, rules="freestyle")
    with pytest.raises(ValueError):
        m.add("takedown", "red", time=5)
    m.add("takedown", "red", time=5, points=2)
    m.add("points", "blue", time=9, points=1, note="step out")
    assert m.final_score() == {"red": 2, "blue": 1}


def test_position_timeline_and_period_resets():
    m = simple_match()
    m.add("takedown", "green", time=60)
    m.add("position", "red", time=180, position="top")
    m.add("escape", "green", time=200)
    segments = m.position_timeline()
    assert segments[:4] == [(0.0, 60.0, None), (60.0, 180.0, "green"), (180.0, 200.0, "red"),
                            (200.0, 300.0, None)]
    assert segments[-1] == (300.0, 420.0, None)   # period 3 starts neutral when nobody chooses


def test_riding_time_point_awarded_at_one_minute():
    m = simple_match()
    m.add("takedown", "green", time=60)          # green rides 60-180 = 120 s
    rt = m.riding_time()
    assert rt["on_top"]["green"] == 120 and rt["point_to"] == "green"
    assert m.final_score() == {"green": 4, "red": 0}

    close = simple_match()
    close.add("takedown", "green", time=140)     # 40 s only
    assert close.riding_time()["point_to"] is None
    assert close.final_score()["green"] == 3


def test_no_riding_time_in_high_school():
    m = simple_match("nfhs")
    m.add("takedown", "green", time=10)
    assert m.riding_time()["point_to"] is None
    assert m.final_score()["green"] == 3


def test_fall_ends_match_and_scoring():
    m = simple_match()
    m.add("takedown", "red", time=30)
    m.add("fall", "red", time=95)
    m.add("escape", "green", time=200)           # after the pin; ignored
    assert m.end_time == 95
    assert m.final_score() == {"green": 0, "red": 3}
    assert m.result() == "red fall green 1:35"


def test_result_strings():
    m = simple_match("nfhs")
    for t in (10, 30, 50):
        m.add("takedown", "green", time=t)
        m.add("escape", "red", time=t + 5)
    assert m.result() == "green dec. red 9-3"
    m.add("takedown", "green", time=70)
    assert m.result() == "green maj. dec. red 12-3"
    assert simple_match().result() == "draw"


def test_json_round_trip(tmp_path):
    m = mw.load_sample_match()
    path = tmp_path / "m.json"
    m.to_json(path)
    again = Match.from_json(path)
    assert again.final_score() == m.final_score() == {"green": 12, "red": 9}
    assert again.rules is mw.NCAA_RULES
    assert Match.from_json(m.to_json()).result() == "green dec. red 12-9"


def test_event_from_dict_string_kind():
    e = Event(time="12", kind="TD", wrestler="green", x=1, y=2)
    assert e.kind is EventType.TAKEDOWN and e.time == 12.0 and e.has_location
    assert e.to_dict() == {"time": 12.0, "kind": "takedown", "wrestler": "green", "x": 1, "y": 2}


def test_charts_render():
    m = mw.load_sample_match()
    ax = mw.score_timeline(m)
    assert len(ax.lines) >= 2
    mw.position_strip(m)
    mw.plot_events(m)
    fig = mw.match_summary(m)
    assert len(fig.axes) == 3
