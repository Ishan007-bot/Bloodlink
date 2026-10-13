from datetime import datetime, timedelta

from app.allocation import Candidate, choose_units, match_type

NOW = datetime(2026, 10, 13, 12, 0, 0)


def unit(unit_id: int, group: str, days_left: float) -> Candidate:
    return Candidate(unit_id, group, NOW + timedelta(days=days_left))


def ids(chosen):
    return [c.unit_id for c in chosen]


def test_exact_group_is_used_before_substitutes():
    stock = [unit(1, "O+", 2), unit(2, "A+", 30)]
    assert ids(choose_units(stock, "A+", 1, NOW)) == [2]


def test_first_expiring_first_out_within_a_group():
    stock = [unit(1, "B+", 20), unit(2, "B+", 3), unit(3, "B+", 10)]
    assert ids(choose_units(stock, "B+", 3, NOW)) == [2, 3, 1]


def test_expired_units_are_never_chosen():
    stock = [unit(1, "A-", -1), unit(2, "A-", 0), unit(3, "A-", 5)]
    assert ids(choose_units(stock, "A-", 3, NOW)) == [3]


def test_incompatible_units_are_ignored():
    stock = [unit(1, "A+", 5), unit(2, "B-", 5), unit(3, "AB-", 5)]
    assert choose_units(stock, "O-", 2, NOW) == []


def test_substitutes_fill_the_gap_when_exact_stock_runs_out():
    stock = [unit(1, "A+", 5), unit(2, "O+", 5), unit(3, "A-", 5)]
    # A+ first, then A- (same ABO), then O+.
    assert ids(choose_units(stock, "A+", 3, NOW)) == [1, 3, 2]


def test_universal_donor_is_kept_for_last_even_if_it_expires_first():
    stock = [unit(1, "O-", 1), unit(2, "O+", 30)]
    assert ids(choose_units(stock, "O+", 1, NOW)) == [2]


def test_never_returns_more_than_needed():
    stock = [unit(i, "AB+", i) for i in range(1, 6)]
    assert len(choose_units(stock, "AB+", 2, NOW)) == 2


def test_zero_needed_returns_nothing():
    assert choose_units([unit(1, "O+", 5)], "O+", 0, NOW) == []


def test_ties_break_on_unit_id():
    stock = [unit(7, "B-", 4), unit(3, "B-", 4)]
    assert ids(choose_units(stock, "B-", 2, NOW)) == [3, 7]


def test_match_type_labels():
    assert match_type("A+", "A+") == "EXACT"
    assert match_type("O-", "A+") == "SUBSTITUTE"
