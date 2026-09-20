"""Classification metrics, bootstrap CI and Cohen's kappa against hand-computed values."""

import math

import pytest

from evals.metrics import accuracy, bootstrap_ci, cohen_kappa, confusion, macro_f1, per_class_prf, rate


def test_accuracy():
    assert accuracy(["a", "a", "b", "b"], ["a", "b", "b", "b"]) == 0.75
    with pytest.raises(ValueError):
        accuracy([], [])
    with pytest.raises(ValueError):
        accuracy(["a"], ["a", "b"])


def test_precision_recall_f1_per_class():
    # true a a b b, predicted a b b b
    # a: tp 1, fp 0, fn 1 -> P 1, R 1/2, F1 2/3      b: tp 2, fp 1, fn 0 -> P 2/3, R 1, F1 4/5
    got = per_class_prf(["a", "a", "b", "b"], ["a", "b", "b", "b"])
    assert got["a"] == pytest.approx({"precision": 1.0, "recall": 0.5, "f1": 2 / 3, "support": 2})
    assert got["b"] == pytest.approx({"precision": 2 / 3, "recall": 1.0, "f1": 0.8, "support": 2})


def test_macro_f1_is_the_unweighted_mean_of_class_f1():
    assert macro_f1(["a", "a", "b", "b"], ["a", "b", "b", "b"]) == pytest.approx((2 / 3 + 0.8) / 2)


def test_macro_f1_counts_a_never_predicted_label_as_zero():
    # labels a, b, c; c never predicted and never true -> F1 0 drags the mean down when listed explicitly
    assert macro_f1(["a", "b"], ["a", "b"]) == 1.0
    assert macro_f1(["a", "b"], ["a", "b"], labels=["a", "b", "c"]) == pytest.approx(2 / 3)


def test_confusion_only_lists_nonzero_cells():
    assert confusion(["a", "a", "b"], ["a", "b", "b"]) == {"a": {"a": 1, "b": 1}, "b": {"b": 1}}


def test_rate_of_empty_is_nan_not_zero():
    assert rate([True, False, True, True]) == 0.75
    assert math.isnan(rate([]))


def test_kappa_two_by_two():
    # both yes 4, A yes / B no 1, A no / B yes 2, both no 3: po 0.7, pe .5*.6 + .5*.4 = 0.5, kappa 0.4
    a = [1] * 4 + [1] + [0] * 2 + [0] * 3
    b = [1] * 4 + [0] + [1] * 2 + [0] * 3
    assert cohen_kappa(a, b) == pytest.approx(0.4)


def test_kappa_perfect_and_undefined():
    assert cohen_kappa([1, 2, 3, 3], [1, 2, 3, 3]) == 1.0
    assert math.isnan(cohen_kappa([4, 4, 4], [4, 4, 4]))  # chance agreement is already perfect


def test_kappa_below_zero_for_systematic_disagreement():
    assert cohen_kappa([1, 0, 1, 0], [0, 1, 0, 1]) == pytest.approx(-1.0)


def test_linear_weighted_kappa():
    # A 1 2 3 3, B 1 3 3 2; observed disagreement 2 * 0.25 * 0.5 = 0.25; expected 0.1875 + 0.25 = 0.4375
    assert cohen_kappa([1, 2, 3, 3], [1, 3, 3, 2], weights="linear") == pytest.approx(1 - 0.25 / 0.4375)
    # unweighted on the same data: po 2/4, pe .25*.25 + .25*.25 + .5*.5 = 0.375 -> (0.5 - 0.375) / 0.625 = 0.2
    assert cohen_kappa([1, 2, 3, 3], [1, 3, 3, 2]) == pytest.approx(0.2)


def test_quadratic_weights_punish_far_disagreement_more_than_linear():
    a, b = [1, 2, 3, 4, 5, 5], [1, 2, 3, 4, 5, 1]
    assert cohen_kappa(a, b, weights="quadratic") < cohen_kappa(a, b, weights="linear") < 1


def test_kappa_input_validation():
    with pytest.raises(ValueError):
        cohen_kappa([1], [1, 2])
    with pytest.raises(ValueError):
        cohen_kappa([1, 2], [1, 2], weights="cubic")


def test_bootstrap_ci_of_a_constant_is_that_constant():
    assert bootstrap_ci([4.0] * 10) == (4.0, 4.0)


def test_bootstrap_ci_brackets_the_mean_and_is_deterministic():
    values = [1, 2, 3, 4, 5] * 6
    lo, hi = bootstrap_ci(values)
    assert lo < sum(values) / len(values) == 3.0 < hi
    assert (lo, hi) == bootstrap_ci(values)
    assert bootstrap_ci(values, seed=1) != (lo, hi)


def test_bootstrap_ci_narrows_with_more_data():
    small = bootstrap_ci([1, 5] * 5)
    large = bootstrap_ci([1, 5] * 200)
    assert (large[1] - large[0]) < (small[1] - small[0])


def test_bootstrap_ci_accepts_another_statistic():
    lo, hi = bootstrap_ci([1, 1, 1, 9], stat=max, n_boot=200)
    assert lo in (1, 9) and hi == 9


def test_bootstrap_needs_data():
    with pytest.raises(ValueError):
        bootstrap_ci([])
