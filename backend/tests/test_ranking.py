"""A3: route ranking follows the brief's order, with hand-worked winners."""

from core.risk import Risk, deciding_rule, rank_routes, summarize

L, M, H, S, N = Risk.LOW, Risk.MODERATE, Risk.HIGH, Risk.SEVERE, Risk.NO_TRAVEL


def route(rid, segments, hours):
    return summarize(rid, segments, hours * 3600)


def winner(*routes):
    return rank_routes(list(routes))[0].route_id


def test_brief_example_fewer_high_miles_beats_faster():
    a = route("A", [(250, L), (50, H)], 6)
    b = route("B", [(275, L), (25, H)], 6.5)
    assert winner(a, b) == "B"
    assert deciding_rule(*rank_routes([a, b])) == "high_miles"


def test_severe_miles_beat_everything_below():
    a = route("A", [(10, S), (290, L)], 5)
    b = route("B", [(0, S), (200, H), (100, L)], 9)
    assert winner(a, b) == "B"
    assert deciding_rule(*rank_routes([a, b])) == "severe_miles"


def test_no_travel_ranks_last_even_if_otherwise_best():
    a = route("A", [(1, N), (299, L)], 4)
    b = route("B", [(100, S), (200, L)], 8)
    assert winner(a, b) == "B"
    assert deciding_rule(*rank_routes([a, b])) == "no_travel_miles"


def test_average_risk_breaks_tie_on_severe_and_high():
    a = route("A", [(100, M), (200, L)], 5)  # avg 0.333
    b = route("B", [(50, M), (250, L)], 6)  # avg 0.167
    assert winner(a, b) == "B"
    assert deciding_rule(*rank_routes([a, b])) == "avg_risk"


def test_time_decides_only_when_risk_ties():
    a = route("A", [(300, L)], 6)
    b = route("B", [(300, L)], 5)
    assert winner(a, b) == "B"
    assert deciding_rule(*rank_routes([a, b])) == "duration"


def test_float_noise_does_not_decide():
    a = route("A", [(100.00001, H), (200, L)], 5)
    b = route("B", [(100.0, H), (200.00001, L)], 6)
    assert winner(a, b) == "A"  # high miles tie at 0.1 mi precision; then avg ties; time decides
    assert deciding_rule(*rank_routes([a, b])) == "duration"


def test_full_tie_is_stable_and_reported():
    a = route("A", [(300, L)], 5)
    b = route("B", [(300, L)], 5)
    ranked = rank_routes([b, a])
    assert [r.route_id for r in ranked] == ["A", "B"]
    assert deciding_rule(*ranked) is None


def test_three_routes_full_order():
    a = route("A", [(20, H), (280, L)], 5)
    b = route("B", [(5, S), (295, L)], 4)
    c = route("C", [(300, L)], 7)
    assert [r.route_id for r in rank_routes([a, b, c])] == ["C", "A", "B"]


def test_summary_maths():
    s = route("A", [(10, L), (20, H), (30, N)], 1)
    assert s.total_miles == 60
    assert s.miles(H) == 20 and s.miles(N) == 30 and s.miles(S) == 0
    assert abs(s.avg_risk - (20 * 2 + 30 * 4) / 60) < 1e-12
