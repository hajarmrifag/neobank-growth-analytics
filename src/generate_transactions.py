from pathlib import Path

import numpy as np
import pandas as pd


SEED = 43
DATA_DIR = Path("data/raw")
ANALYSIS_END = pd.Timestamp("2026-08-31 23:59:59")

CHANNEL_ACTIVATION = {
    "organic": 0.84,
    "paid_search": 0.81,
    "paid_social": 0.75,
    "referral": 0.88,
    "affiliate": 0.78,
}

CHANNEL_ACTIVITY_MULTIPLIER = {
    "organic": 1.05,
    "paid_search": 1.00,
    "paid_social": 0.85,
    "referral": 1.15,
    "affiliate": 0.92,
}

TRANSACTION_TYPES = np.array(
    ["card_payment", "bank_transfer", "fx_exchange", "cash_withdrawal"]
)
TRANSACTION_TYPE_PROBS = np.array([0.66, 0.16, 0.11, 0.07])

MERCHANT_CATEGORIES = np.array(
    ["groceries", "restaurants", "transport", "shopping", "travel", "subscriptions"]
)
MERCHANT_CATEGORY_PROBS = np.array([0.24, 0.19, 0.14, 0.20, 0.10, 0.13])

COUNTRIES = np.array(["GB", "FR", "DE", "ES", "IT", "NL", "IE"])

# Approximate GBP value of one unit of each currency.
FX_RATES_TO_GBP = {
    "GBP": 1.00,
    "EUR": 0.86,
    "USD": 0.79,
    "CHF": 0.89,
}


def sample_amount(rng: np.random.Generator, transaction_type: str) -> float:
    params = {
        "cash_in": (4.15, 0.75),
        "card_payment": (3.20, 0.75),
        "bank_transfer": (4.55, 0.80),
        "fx_exchange": (4.25, 0.80),
        "cash_withdrawal": (3.80, 0.60),
    }
    mean, sigma = params[transaction_type]
    return round(float(rng.lognormal(mean=mean, sigma=sigma)), 2)


def transaction_economics(
    transaction_type: str,
    amount: float,
    status: str,
) -> tuple:
    if status != "completed":
        return 0.0, 0.0, 0.0, 0.01

    if transaction_type == "card_payment":
        return (
            0.0,
            round(amount * 0.0065, 2),
            0.0,
            round(0.02 + amount * 0.0015, 2),
        )

    if transaction_type == "bank_transfer":
        return (
            0.25 if amount > 250 else 0.0,
            0.0,
            0.0,
            0.04,
        )

    if transaction_type == "fx_exchange":
        return (
            0.0,
            0.0,
            round(amount * 0.004, 2),
            0.03,
        )

    if transaction_type == "cash_withdrawal":
        return (
            1.0 if amount > 200 else 0.0,
            0.0,
            0.0,
            0.35,
        )

    return 0.0, 0.0, 0.0, 0.02


def main() -> None:
    rng = np.random.default_rng(SEED)

    customers = pd.read_csv(
        DATA_DIR / "customers.csv",
        parse_dates=["signup_ts"],
    )
    accounts = pd.read_csv(
        DATA_DIR / "accounts.csv",
        parse_dates=["opened_ts"],
    )
    experiments = pd.read_csv(
        DATA_DIR / "experiment_assignments.csv",
        parse_dates=["assigned_ts"],
    )
    existing_events = pd.read_csv(
        DATA_DIR / "product_events.csv",
        parse_dates=["event_ts"],
    )

    base = (
        accounts
        .merge(
            customers[
                [
                    "customer_id",
                    "country_code",
                    "age",
                    "acquisition_channel",
                    "device_os",
                ]
            ],
            on="customer_id",
            how="left",
        )
        .merge(
            experiments[["customer_id", "variant"]],
            on="customer_id",
            how="left",
        )
    )

    # Baseline activation differs by acquisition channel.
    activation_probability = (
        base["acquisition_channel"]
        .map(CHANNEL_ACTIVATION)
        .astype(float)
    )

    # The simulated £10 first-funding offer produces a +5 percentage-point lift.
    activation_probability += np.where(
        base["variant"].eq("bonus_10"),
        0.05,
        0.0,
    )
    activation_probability = activation_probability.clip(upper=0.97)

    base["activated"] = (
        rng.random(len(base)) < activation_probability
    )

    base["days_available"] = (
        ANALYSIS_END - base["opened_ts"]
    ).dt.days.clip(lower=1)

    # Adds natural customer-to-customer variation in usage intensity.
    customer_activity_noise = rng.lognormal(
        mean=0.0,
        sigma=0.35,
        size=len(base),
    )

    expected_after_funding = (
        base["days_available"]
        * 0.15
        * base["acquisition_channel"].map(CHANNEL_ACTIVITY_MULTIPLIER)
        * customer_activity_noise
    ).clip(lower=1.0, upper=120.0)

    extra_transactions = rng.poisson(expected_after_funding)

    # Non-activated accounts have zero transactions.
    # Activated accounts start with one completed cash-in.
    base["transaction_count"] = np.where(
        base["activated"],
        1 + extra_transactions,
        0,
    )

    transactions = []
    card_details = []
    transfer_details = []
    fx_details = []
    new_events = []

    transaction_id = 1
    next_event_id = int(existing_events["event_id"].max()) + 1

    for row in base.itertuples(index=False):
        n_transactions = int(row.transaction_count)

        if n_transactions == 0:
            continue

        opened_ts = pd.Timestamp(row.opened_ts)

        # First funding occurs within seven days of account opening.
        max_first_delay_seconds = min(
            int((ANALYSIS_END - opened_ts).total_seconds()),
            7 * 24 * 3600,
        )
        max_first_delay_seconds = max(max_first_delay_seconds, 60)

        first_funding_ts = opened_ts + pd.to_timedelta(
            int(rng.integers(60, max_first_delay_seconds + 1)),
            unit="s",
        )

        first_amount = sample_amount(rng, "cash_in")
        incentive_cost = (
            10.0 if row.variant == "bonus_10" else 0.0
        )

        transactions.append(
            [
                transaction_id,
                row.account_id,
                first_funding_ts,
                "cash_in",
                "completed",
                first_amount,
                0.0,
                0.0,
                0.0,
                0.02,
                incentive_cost,
            ]
        )

        new_events.append(
            [
                next_event_id,
                row.customer_id,
                first_funding_ts,
                "first_funding",
                f"funding-{row.customer_id}",
                first_amount,
            ]
        )
        next_event_id += 1
        transaction_id += 1

        remaining = n_transactions - 1
        first_non_funding_completed_ts = None

        if remaining > 0:
            total_seconds_after_funding = max(
                int((ANALYSIS_END - first_funding_ts).total_seconds()),
                1,
            )

            offsets = np.sort(
                rng.integers(
                    1,
                    total_seconds_after_funding + 1,
                    size=remaining,
                )
            )

            timestamps = (
                first_funding_ts
                + pd.to_timedelta(offsets, unit="s")
            )

            types = rng.choice(
                TRANSACTION_TYPES,
                size=remaining,
                p=TRANSACTION_TYPE_PROBS,
            )

            for ts, transaction_type in zip(timestamps, types):
                status = rng.choice(
                    ["completed", "failed", "reversed"],
                    p=[0.965, 0.025, 0.010],
                )

                amount = sample_amount(
                    rng,
                    transaction_type,
                )

                (
                    fee_revenue,
                    interchange_revenue,
                    fx_spread_revenue,
                    processing_cost,
                ) = transaction_economics(
                    transaction_type,
                    amount,
                    status,
                )

                transactions.append(
                    [
                        transaction_id,
                        row.account_id,
                        ts,
                        transaction_type,
                        status,
                        amount,
                        fee_revenue,
                        interchange_revenue,
                        fx_spread_revenue,
                        processing_cost,
                        0.0,
                    ]
                )

                if (
                    status == "completed"
                    and first_non_funding_completed_ts is None
                ):
                    first_non_funding_completed_ts = ts

                if transaction_type == "card_payment":
                    merchant_country = (
                        row.country_code
                        if rng.random() < 0.80
                        else rng.choice(COUNTRIES)
                    )

                    card_details.append(
                        [
                            transaction_id,
                            rng.choice(
                                MERCHANT_CATEGORIES,
                                p=MERCHANT_CATEGORY_PROBS,
                            ),
                            merchant_country,
                            bool(rng.random() < 0.72),
                        ]
                    )

                elif transaction_type == "bank_transfer":
                    if row.country_code == "GB":
                        rail = rng.choice(
                            ["faster_payments", "swift"],
                            p=[0.88, 0.12],
                        )
                    else:
                        rail = rng.choice(
                            ["sepa", "swift"],
                            p=[0.90, 0.10],
                        )

                    transfer_details.append(
                        [
                            transaction_id,
                            rng.choice(
                                ["inbound", "outbound"],
                                p=[0.42, 0.58],
                            ),
                            rail,
                            rng.choice(COUNTRIES),
                        ]
                    )

                elif transaction_type == "fx_exchange":
                    base_currency = row.base_currency

                    possible_targets = [
                        currency
                        for currency in FX_RATES_TO_GBP
                        if currency != base_currency
                    ]

                    target_currency = rng.choice(
                        possible_targets
                    )

                    source_amount = (
                        amount
                        / FX_RATES_TO_GBP[base_currency]
                    )
                    gbp_value = (
                        source_amount
                        * FX_RATES_TO_GBP[base_currency]
                    )
                    target_amount = (
                        gbp_value
                        / FX_RATES_TO_GBP[target_currency]
                    )
                    quoted_rate = (
                        target_amount / source_amount
                    )

                    fx_details.append(
                        [
                            transaction_id,
                            base_currency,
                            target_currency,
                            round(source_amount, 2),
                            round(target_amount, 2),
                            round(quoted_rate, 8),
                            40.0,
                        ]
                    )

                transaction_id += 1

        if first_non_funding_completed_ts is not None:
            new_events.append(
                [
                    next_event_id,
                    row.customer_id,
                    first_non_funding_completed_ts,
                    "first_transaction",
                    f"txn-{row.customer_id}",
                    None,
                ]
            )
            next_event_id += 1

    transactions_df = pd.DataFrame(
        transactions,
        columns=[
            "transaction_id",
            "account_id",
            "transaction_ts",
            "transaction_type",
            "status",
            "amount_gbp",
            "fee_revenue_gbp",
            "interchange_revenue_gbp",
            "fx_spread_revenue_gbp",
            "processing_cost_gbp",
            "incentive_cost_gbp",
        ],
    )

    card_df = pd.DataFrame(
        card_details,
        columns=[
            "transaction_id",
            "merchant_category",
            "merchant_country",
            "card_present",
        ],
    )

    transfer_df = pd.DataFrame(
        transfer_details,
        columns=[
            "transaction_id",
            "direction",
            "transfer_rail",
            "counterparty_country",
        ],
    )

    fx_df = pd.DataFrame(
        fx_details,
        columns=[
            "transaction_id",
            "from_currency",
            "to_currency",
            "source_amount",
            "target_amount",
            "quoted_rate",
            "spread_bps",
        ],
    )

    events_df = pd.DataFrame(
        new_events,
        columns=[
            "event_id",
            "customer_id",
            "event_ts",
            "event_name",
            "session_id",
            "event_value",
        ],
    )

    outputs = {
        "transactions.csv": transactions_df,
        "card_transactions.csv": card_df,
        "transfers.csv": transfer_df,
        "fx_transactions.csv": fx_df,
        "transaction_events.csv": events_df,
    }

    for filename, dataframe in outputs.items():
        path = DATA_DIR / filename
        dataframe.to_csv(path, index=False)
        print(
            f"{filename:30s} "
            f"{len(dataframe):>10,} rows"
        )

    activated_accounts = int(
        (base["transaction_count"] > 0).sum()
    )

    print()
    print(
        f"Activated accounts: "
        f"{activated_accounts:,} / {len(base):,}"
    )
    print(
        f"Activation rate: "
        f"{100 * activated_accounts / len(base):.2f}%"
    )
    print(
        f"Total transactions: "
        f"{len(transactions_df):,}"
    )
    print(
        "Transaction data generated successfully."
    )


if __name__ == "__main__":
    main()
