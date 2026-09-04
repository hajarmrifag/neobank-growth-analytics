from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed" / "dashboard"

st.set_page_config(
    page_title="Neobank Growth & Unit Economics",
    page_icon="📊",
    layout="wide",
)

st.title("Neobank Growth & Unit Economics Analytics")
st.caption(
    "Synthetic fintech dataset • 50,000 customers • 890K+ transactions • "
    "Python, SQL, PostgreSQL"
)

st.info(
    "All customer and transaction data in this project is synthetic and was "
    "generated for portfolio analysis."
)


@st.cache_data
def load_data():
    return {
        "kpis": pd.read_csv(DATA_DIR / "kpis.csv"),
        "channels": pd.read_csv(DATA_DIR / "channel_performance.csv"),
        "retention": pd.read_csv(DATA_DIR / "retention_cohorts.csv"),
        "experiment": pd.read_csv(DATA_DIR / "experiment_performance.csv"),
        "fx_segments": pd.read_csv(DATA_DIR / "fx_customer_segments.csv"),
        "fx_retention": pd.read_csv(DATA_DIR / "fx_retention.csv"),
        "economics": pd.read_csv(DATA_DIR / "transaction_economics.csv"),
    }


data = load_data()
kpis = data["kpis"].iloc[0]

st.header("Executive overview")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Signups", f"{int(kpis['total_signups']):,}")
c2.metric("Funded customers", f"{int(kpis['funded_customers']):,}")
c3.metric("Transactions", f"{int(kpis['total_transactions']):,}")
c4.metric(
    "Completed volume",
    f"£{float(kpis['completed_transaction_volume_gbp']) / 1_000_000:.1f}M",
)

c5, c6, c7, c8 = st.columns(4)
signup_to_funding = (
    float(kpis["funded_customers"]) / float(kpis["total_signups"]) * 100
)
c5.metric("Signup → funding", f"{signup_to_funding:.1f}%")
c6.metric("KYC approved", f"{int(kpis['kyc_approved']):,}")
c7.metric("Transacting customers", f"{int(kpis['transacting_customers']):,}")
c8.metric(
    "Contribution margin",
    f"£{float(kpis['total_contribution_margin_gbp']):,.0f}",
)

st.markdown(
    """
**Headline:** customer quality varies materially by acquisition source.
Referral users show the strongest conversion and retention, while organic
acquisition is dramatically cheaper than paid channels.
"""
)

st.header("Acquisition performance")

channels = data["channels"].copy()
channels["channel"] = (
    channels["acquisition_channel"].str.replace("_", " ").str.title()
)

left, right = st.columns(2)

with left:
    fig = px.bar(
        channels.sort_values("signup_to_funding_pct", ascending=False),
        x="channel",
        y="signup_to_funding_pct",
        labels={
            "channel": "Acquisition channel",
            "signup_to_funding_pct": "Signup → funding (%)",
        },
        title="Signup-to-funding conversion",
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    fig = px.bar(
        channels.sort_values("cost_per_funded_customer_gbp"),
        x="channel",
        y="cost_per_funded_customer_gbp",
        labels={
            "channel": "Acquisition channel",
            "cost_per_funded_customer_gbp": "Cost per funded customer (£)",
        },
        title="Cost per funded customer",
    )
    st.plotly_chart(fig, use_container_width=True)

st.dataframe(
    channels[
        [
            "channel",
            "signups",
            "funded_customers",
            "signup_to_funding_pct",
            "cac_gbp",
            "cost_per_funded_customer_gbp",
            "avg_transaction_volume_gbp",
            "avg_contribution_margin_gbp",
        ]
    ].rename(
        columns={
            "channel": "Channel",
            "signups": "Signups",
            "funded_customers": "Funded customers",
            "signup_to_funding_pct": "Signup → funding %",
            "cac_gbp": "CAC £",
            "cost_per_funded_customer_gbp": "Cost / funded £",
            "avg_transaction_volume_gbp": "Avg volume £",
            "avg_contribution_margin_gbp": "Avg margin £",
        }
    ),
    use_container_width=True,
    hide_index=True,
)

st.header("Cohort retention")

retention = data["retention"].copy()
retention["funding_cohort"] = pd.to_datetime(retention["funding_cohort"])
retention["cohort"] = retention["funding_cohort"].dt.strftime("%b 2026")

retention_long = retention.melt(
    id_vars=["cohort"],
    value_vars=["d30_retention_pct", "d60_retention_pct"],
    var_name="metric",
    value_name="retention_pct",
)
retention_long["metric"] = retention_long["metric"].map(
    {
        "d30_retention_pct": "D30",
        "d60_retention_pct": "D60",
    }
)

fig = px.line(
    retention_long,
    x="cohort",
    y="retention_pct",
    color="metric",
    markers=True,
    labels={
        "cohort": "Funding cohort",
        "retention_pct": "Retention (%)",
        "metric": "Window",
    },
    title="D30 and D60 retention by funding cohort",
)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Retention is defined as at least three completed non-funding transactions "
    "during the relevant 30-day activity window. Only fully observed cohorts "
    "are included."
)

st.header("£10 activation incentive experiment")

experiment = data["experiment"].copy()
experiment["variant_label"] = experiment["variant"].map(
    {"bonus_10": "£10 bonus", "control": "Control"}
)

left, right = st.columns(2)

with left:
    fig = px.bar(
        experiment,
        x="variant_label",
        y="activation_rate_pct",
        labels={
            "variant_label": "Variant",
            "activation_rate_pct": "Activation rate (%)",
        },
        title="Activation rate",
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    fig = px.bar(
        experiment,
        x="variant_label",
        y="avg_margin_after_incentive_gbp",
        labels={
            "variant_label": "Variant",
            "avg_margin_after_incentive_gbp": "Avg margin after incentive (£)",
        },
        title="Observed margin after incentive",
    )
    st.plotly_chart(fig, use_container_width=True)

st.markdown(
    """
**Experiment readout:** the £10 bonus increased activation from **69.03% to
73.12%**, an absolute uplift of **4.09 percentage points**. A two-proportion
z-test gives **z = 10.09** with **p ≈ 6.1×10⁻²⁴**, and the 95% confidence
interval for the uplift is **3.30 to 4.89 percentage points**.

Despite the statistically significant uplift, the estimated break-even
contribution margin is about **£178.72 per incremental activation**, far above
the short-window margin observed in the control group. The recommendation is
therefore **not to launch the £10 incentive at its current economics**.
"""
)

st.header("FX customer segment")

fx_segments = data["fx_segments"].copy()
fx_retention = data["fx_retention"].copy()

fx_row = fx_segments.loc[fx_segments["customer_segment"] == "FX user"].iloc[0]
non_fx_row = fx_segments.loc[
    fx_segments["customer_segment"] == "Non-FX user"
].iloc[0]

fx_ret_row = fx_retention.loc[
    fx_retention["customer_segment"] == "FX user"
].iloc[0]
non_fx_ret_row = fx_retention.loc[
    fx_retention["customer_segment"] == "Non-FX user"
].iloc[0]

a, b, c = st.columns(3)
a.metric(
    "Avg completed transactions",
    f"{fx_row['avg_completed_transactions']:.2f}",
    delta=(
        f"{fx_row['avg_completed_transactions'] - non_fx_row['avg_completed_transactions']:.2f} "
        "vs non-FX"
    ),
)
b.metric(
    "Avg transaction volume",
    f"£{fx_row['avg_transaction_volume_gbp']:,.2f}",
    delta=(
        f"£{fx_row['avg_transaction_volume_gbp'] - non_fx_row['avg_transaction_volume_gbp']:,.2f} "
        "vs non-FX"
    ),
)
c.metric(
    "D30 retention",
    f"{fx_ret_row['d30_retention_pct']:.2f}%",
    delta=(
        f"{fx_ret_row['d30_retention_pct'] - non_fx_ret_row['d30_retention_pct']:.2f} pp "
        "vs non-FX"
    ),
)

fig = px.bar(
    fx_retention,
    x="customer_segment",
    y="d30_retention_pct",
    labels={
        "customer_segment": "Customer segment",
        "d30_retention_pct": "D30 retention (%)",
    },
    title="D30 retention: FX vs non-FX users",
)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "FX usage is associated with higher engagement and retention in this "
    "synthetic dataset. This is an observational relationship, not a causal claim."
)

st.header("Transaction economics")

economics = data["economics"].copy()
economics["transaction_label"] = (
    economics["transaction_type"].str.replace("_", " ").str.title()
)

fig = px.bar(
    economics.sort_values("contribution_margin_gbp", ascending=False),
    x="transaction_label",
    y="contribution_margin_gbp",
    labels={
        "transaction_label": "Transaction type",
        "contribution_margin_gbp": "Contribution margin (£)",
    },
    title="Contribution margin by transaction type",
)
st.plotly_chart(fig, use_container_width=True)

st.dataframe(
    economics[
        [
            "transaction_label",
            "completed_transactions",
            "transaction_volume_gbp",
            "revenue_gbp",
            "processing_cost_gbp",
            "contribution_margin_gbp",
            "avg_margin_per_transaction_gbp",
        ]
    ].rename(
        columns={
            "transaction_label": "Transaction type",
            "completed_transactions": "Completed transactions",
            "transaction_volume_gbp": "Volume £",
            "revenue_gbp": "Revenue £",
            "processing_cost_gbp": "Processing cost £",
            "contribution_margin_gbp": "Contribution margin £",
            "avg_margin_per_transaction_gbp": "Avg margin / transaction £",
        }
    ),
    use_container_width=True,
    hide_index=True,
)

st.markdown(
    """
**Product insight:** card payments contribute the most total margin, while FX
has the highest margin per completed transaction. Cash withdrawals are the
largest loss-making transaction type in the current synthetic economics.
"""
)

st.divider()
st.caption(
    "Portfolio project by Hajar Mrifag • Synthetic data only • "
    "Analysis built with Python, SQL and PostgreSQL"
)
