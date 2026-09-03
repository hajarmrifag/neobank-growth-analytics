from pathlib import Path
import numpy as np
import pandas as pd

SEED = 42
N_CUSTOMERS = 50_000
OUT_DIR = Path("data/raw")

CHANNELS = np.array(
    ["organic", "paid_search", "paid_social", "referral", "affiliate"]
)
CHANNEL_PROBS = np.array([0.28, 0.24, 0.20, 0.16, 0.12])

COUNTRIES = np.array(["GB", "FR", "DE", "ES", "IT", "NL", "IE"])
COUNTRY_PROBS = np.array([0.40, 0.12, 0.12, 0.10, 0.09, 0.09, 0.08])


def main() -> None:
    rng = np.random.default_rng(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    customer_ids = np.arange(1, N_CUSTOMERS + 1, dtype=np.int64)

    start = pd.Timestamp("2026-01-01")
    end = pd.Timestamp("2026-06-30 23:59:59")
    seconds = int((end - start).total_seconds())
    signup_ts = start + pd.to_timedelta(
        rng.integers(0, seconds, size=N_CUSTOMERS), unit="s"
    )

    acquisition_channel = rng.choice(
        CHANNELS, size=N_CUSTOMERS, p=CHANNEL_PROBS
    )
    country_code = rng.choice(
        COUNTRIES, size=N_CUSTOMERS, p=COUNTRY_PROBS
    )
    age = np.clip(
        np.rint(rng.normal(32, 9, size=N_CUSTOMERS)), 18, 70
    ).astype(int)
    device_os = rng.choice(
        ["iOS", "Android"], size=N_CUSTOMERS, p=[0.57, 0.43]
    )
    referral_code_used = (
        (acquisition_channel == "referral")
        | (rng.random(N_CUSTOMERS) < 0.04)
    )

    # Hidden synthetic variable used only to create realistic behavioural differences.
    # It is deliberately not exported, so it cannot leak into later analysis/models.
    quality = rng.beta(2.4, 2.0, size=N_CUSTOMERS)

    customers = pd.DataFrame(
        {
            "customer_id": customer_ids,
            "signup_ts": signup_ts,
            "country_code": country_code,
            "age": age,
            "acquisition_channel": acquisition_channel,
            "device_os": device_os,
            "referral_code_used": referral_code_used,
        }
    )

    channel_effect = (
        pd.Series(acquisition_channel)
        .map(
            {
                "organic": 0.025,
                "paid_search": 0.000,
                "paid_social": -0.025,
                "referral": 0.035,
                "affiliate": -0.010,
            }
        )
        .to_numpy()
    )

    p_kyc_start = np.clip(0.94 + 0.05 * quality, 0, 0.995)
    started = rng.random(N_CUSTOMERS) < p_kyc_start

    p_approve = np.clip(
        0.78 + 0.16 * quality + channel_effect, 0.65, 0.98
    )
    approved = started & (rng.random(N_CUSTOMERS) < p_approve)
    rejected = (
        started
        & ~approved
        & (rng.random(N_CUSTOMERS) < 0.55)
    )

    status = np.where(
        approved,
        "approved",
        np.where(rejected, "rejected", "abandoned"),
    )

    start_delay = pd.to_timedelta(
        rng.integers(60, 6 * 3600, size=N_CUSTOMERS), unit="s"
    )
    kyc_started_ts = pd.Series(signup_ts + start_delay)
    kyc_started_ts.loc[~started] = pd.NaT

    completion_delay = pd.to_timedelta(
        rng.integers(5 * 60, 48 * 3600, size=N_CUSTOMERS), unit="s"
    )
    kyc_completed_ts = kyc_started_ts + completion_delay
    kyc_completed_ts.loc[status == "abandoned"] = pd.NaT

    failure_reason = np.full(N_CUSTOMERS, None, dtype=object)

    rejected_idx = np.where(rejected)[0]
    failure_reason[rejected_idx] = rng.choice(
        [
            "document_blur",
            "name_mismatch",
            "unsupported_document",
            "liveness_check",
        ],
        size=len(rejected_idx),
        p=[0.28, 0.32, 0.22, 0.18],
    )

    abandoned_idx = np.where(status == "abandoned")[0]
    failure_reason[abandoned_idx] = "user_abandoned"

    kyc_cases = pd.DataFrame(
        {
            "kyc_case_id": customer_ids,
            "customer_id": customer_ids,
            "started_ts": kyc_started_ts,
            "completed_ts": kyc_completed_ts,
            "status": status,
            "failure_reason": failure_reason,
        }
    )

    approved_idx = np.where(approved)[0]
    account_ids = np.arange(1, len(approved_idx) + 1, dtype=np.int64)

    opened_ts = (
        pd.Series(kyc_completed_ts.iloc[approved_idx].to_numpy())
        + pd.to_timedelta(
            rng.integers(5 * 60, 24 * 3600, size=len(approved_idx)),
            unit="s",
        )
    )

    premium_probability = np.where(
        quality[approved_idx] > 0.78, 0.25, 0.08
    )
    plan_tier = np.where(
        rng.random(len(approved_idx)) < premium_probability,
        "premium",
        "standard",
    )
    base_currency = np.where(
        country_code[approved_idx] == "GB", "GBP", "EUR"
    )

    accounts = pd.DataFrame(
        {
            "account_id": account_ids,
            "customer_id": customer_ids[approved_idx],
            "opened_ts": opened_ts,
            "plan_tier": plan_tier,
            "base_currency": base_currency,
        }
    )

    variants = rng.choice(
        ["control", "bonus_10"],
        size=N_CUSTOMERS,
        p=[0.50, 0.50],
    )
    experiments = pd.DataFrame(
        {
            "assignment_id": customer_ids,
            "customer_id": customer_ids,
            "experiment_name": "first_funding_bonus_10",
            "variant": variants,
            "assigned_ts": signup_ts,
        }
    )

    events = []
    event_id = 1
    account_opened_by_customer = dict(
        zip(accounts["customer_id"], accounts["opened_ts"])
    )

    for i, customer_id in enumerate(customer_ids):
        session_id = f"s{customer_id:07d}"

        events.append(
            (
                event_id,
                customer_id,
                signup_ts[i],
                "signup_completed",
                session_id,
                None,
            )
        )
        event_id += 1

        if pd.notna(kyc_started_ts.iloc[i]):
            events.append(
                (
                    event_id,
                    customer_id,
                    kyc_started_ts.iloc[i],
                    "kyc_started",
                    session_id,
                    None,
                )
            )
            event_id += 1

        if pd.notna(kyc_completed_ts.iloc[i]):
            event_name = (
                "kyc_approved"
                if status[i] == "approved"
                else "kyc_rejected"
            )
            events.append(
                (
                    event_id,
                    customer_id,
                    kyc_completed_ts.iloc[i],
                    event_name,
                    session_id,
                    None,
                )
            )
            event_id += 1

        opened = account_opened_by_customer.get(customer_id)
        if opened is not None:
            events.append(
                (
                    event_id,
                    customer_id,
                    opened,
                    "account_opened",
                    session_id,
                    None,
                )
            )
            event_id += 1

    product_events = pd.DataFrame(
        events,
        columns=[
            "event_id",
            "customer_id",
            "event_ts",
            "event_name",
            "session_id",
            "event_value",
        ],
    )

    spend_base = {
        "organic": 5_000,
        "paid_search": 80_000,
        "paid_social": 65_000,
        "referral": 30_000,
        "affiliate": 40_000,
    }
    cpm = {
        "organic": 3.0,
        "paid_search": 18.0,
        "paid_social": 11.0,
        "referral": 7.0,
        "affiliate": 10.0,
    }
    ctr = {
        "organic": 0.060,
        "paid_search": 0.045,
        "paid_social": 0.018,
        "referral": 0.035,
        "affiliate": 0.025,
    }

    spend_rows = []
    for month in pd.date_range(
        "2026-01-01", "2026-06-01", freq="MS"
    ):
        for channel in CHANNELS:
            spend = max(
                0,
                spend_base[channel] * rng.normal(1.0, 0.08),
            )
            impressions = int(spend / cpm[channel] * 1_000)
            clicks = int(
                impressions
                * ctr[channel]
                * rng.normal(1.0, 0.05)
            )
            spend_rows.append(
                (
                    month.date(),
                    channel,
                    round(spend, 2),
                    impressions,
                    clicks,
                )
            )

    marketing_spend = pd.DataFrame(
        spend_rows,
        columns=[
            "spend_month",
            "acquisition_channel",
            "spend_gbp",
            "impressions",
            "clicks",
        ],
    )

    outputs = {
        "customers.csv": customers,
        "kyc_cases.csv": kyc_cases,
        "accounts.csv": accounts,
        "marketing_spend.csv": marketing_spend,
        "experiment_assignments.csv": experiments,
        "product_events.csv": product_events,
    }

    for filename, dataframe in outputs.items():
        path = OUT_DIR / filename
        dataframe.to_csv(path, index=False)
        print(f"{filename:30s} {len(dataframe):>10,} rows")

    print("\nCore Day 1 data generated successfully.")


if __name__ == "__main__":
    main()
