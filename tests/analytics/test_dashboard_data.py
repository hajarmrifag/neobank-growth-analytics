"""Data-contract tests for the CSVs that power the Streamlit dashboard."""

from pathlib import Path

import pandas as pd
import pytest

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "dashboard"


def load(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / f"{name}.csv")


@pytest.fixture(scope="module")
def kpis():
    return load("kpis").iloc[0]


def test_every_dashboard_file_is_present_and_non_empty():
    for name in (
        "kpis",
        "channel_performance",
        "retention_cohorts",
        "experiment_performance",
        "fx_customer_segments",
        "fx_retention",
        "transaction_economics",
    ):
        assert len(load(name)) > 0, name


def test_funnel_is_monotonic(kpis):
    assert kpis.total_signups >= kpis.kyc_approved >= kpis.funded_customers
    assert kpis.funded_customers >= kpis.transacting_customers - 10
    assert kpis.kyc_approved == kpis.accounts_opened


def test_channels_reconcile_with_headline_kpis(kpis):
    channels = load("channel_performance")

    assert channels.signups.sum() == kpis.total_signups
    assert channels.funded_customers.sum() == kpis.funded_customers


def test_channel_conversion_and_cost_are_consistent():
    channels = load("channel_performance")

    conversion = channels.funded_customers / channels.signups * 100
    assert conversion.round(2).tolist() == pytest.approx(
        channels.signup_to_funding_pct.tolist(), abs=0.01
    )

    cost_per_funded = channels.acquisition_spend_gbp / channels.funded_customers
    assert cost_per_funded.round(2).tolist() == pytest.approx(
        channels.cost_per_funded_customer_gbp.tolist(), abs=0.01
    )


def test_transaction_economics_reconcile_with_kpis(kpis):
    economics = load("transaction_economics")

    assert economics.contribution_margin_gbp.sum() == pytest.approx(
        kpis.total_contribution_margin_gbp, abs=0.01
    )
    assert economics.transaction_volume_gbp.sum() == pytest.approx(
        kpis.completed_transaction_volume_gbp, abs=0.01
    )
    margin = economics.revenue_gbp - economics.processing_cost_gbp
    assert margin.tolist() == pytest.approx(economics.contribution_margin_gbp.tolist(), abs=0.01)


def test_experiment_arms_cover_all_customers(kpis):
    experiment = load("experiment_performance").set_index("variant")

    assert experiment.assigned_customers.sum() == kpis.total_signups
    assert set(experiment.index) == {"bonus_10", "control"}
    assert experiment.loc["control", "total_incentive_cost_gbp"] == 0


def test_experiment_incentive_cost_is_ten_pounds_per_activation():
    bonus = load("experiment_performance").set_index("variant").loc["bonus_10"]

    assert bonus.total_incentive_cost_gbp == pytest.approx(bonus.activated_customers * 10)


def test_retention_rates_are_valid_percentages():
    cohorts = load("retention_cohorts")

    for column in ("d30_retention_pct", "d60_retention_pct"):
        assert cohorts[column].between(0, 100).all()
    recomputed = cohorts.retained_d30 / cohorts.funded_customers * 100
    assert recomputed.round(2).tolist() == pytest.approx(
        cohorts.d30_retention_pct.tolist(), abs=0.01
    )


def test_fx_segments_partition_funded_customers(kpis):
    segments = load("fx_customer_segments")

    assert segments.customers.sum() == kpis.funded_customers
