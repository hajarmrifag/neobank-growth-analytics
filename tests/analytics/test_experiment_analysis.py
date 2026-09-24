import math

import pytest

from experiment_analysis import two_proportion_z_test

# Published results from the £10 activation experiment (see README).
BONUS = (18_340, 25_081)
CONTROL = (17_202, 24_919)


def test_matches_published_experiment_results():
    lift, z_stat, p_value, ci_lower, ci_upper = two_proportion_z_test(*BONUS, *CONTROL)

    assert lift * 100 == pytest.approx(4.09, abs=0.01)
    assert z_stat == pytest.approx(10.09, abs=0.01)
    assert p_value == pytest.approx(6.145e-24, rel=0.01)
    assert ci_lower * 100 == pytest.approx(3.30, abs=0.01)
    assert ci_upper * 100 == pytest.approx(4.89, abs=0.01)


def test_identical_groups_show_no_effect():
    lift, z_stat, p_value, ci_lower, ci_upper = two_proportion_z_test(500, 1_000, 500, 1_000)

    assert lift == 0
    assert z_stat == 0
    assert p_value == pytest.approx(1.0)
    assert ci_lower < 0 < ci_upper


def test_swapping_groups_flips_the_sign_only():
    forward = two_proportion_z_test(*BONUS, *CONTROL)
    reverse = two_proportion_z_test(*CONTROL, *BONUS)

    assert reverse[0] == pytest.approx(-forward[0])
    assert reverse[1] == pytest.approx(-forward[1])
    assert reverse[2] == pytest.approx(forward[2])


def test_confidence_interval_is_centred_on_the_lift():
    lift, _, _, ci_lower, ci_upper = two_proportion_z_test(*BONUS, *CONTROL)

    assert math.isclose((ci_lower + ci_upper) / 2, lift)
