from __future__ import annotations

import math
import os

import psycopg
from dotenv import load_dotenv


def get_connection() -> psycopg.Connection:
    load_dotenv()
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "neobank_analytics"),
        user=os.getenv("POSTGRES_USER", "neobank_user"),
        password=os.getenv("POSTGRES_PASSWORD", "change_me_local_only"),
    )


def fetch_experiment_summary(conn: psycopg.Connection) -> dict[str, dict[str, float]]:
    query = """
    WITH funded AS (
        SELECT DISTINCT customer_id
        FROM product_events
        WHERE event_name = 'first_funding'
    ),
    customer_economics AS (
        SELECT
            a.customer_id,
            SUM(
                t.fee_revenue_gbp
                + t.interchange_revenue_gbp
                + t.fx_spread_revenue_gbp
                - t.processing_cost_gbp
            ) FILTER (WHERE t.status = 'completed') AS margin_before_incentive_gbp,
            SUM(t.incentive_cost_gbp)
                FILTER (WHERE t.status = 'completed') AS incentive_cost_gbp
        FROM accounts a
        LEFT JOIN transactions t
            ON a.account_id = t.account_id
        GROUP BY a.customer_id
    )
    SELECT
        ea.variant,
        COUNT(*) AS assigned_customers,
        COUNT(*) FILTER (WHERE f.customer_id IS NOT NULL) AS activated_customers,
        COALESCE(SUM(ce.incentive_cost_gbp), 0) AS total_incentive_cost_gbp,
        AVG(ce.margin_before_incentive_gbp)
            FILTER (WHERE f.customer_id IS NOT NULL) AS avg_margin_before_incentive_gbp
    FROM experiment_assignments ea
    LEFT JOIN funded f
        ON ea.customer_id = f.customer_id
    LEFT JOIN customer_economics ce
        ON ea.customer_id = ce.customer_id
    GROUP BY ea.variant;
    """

    result: dict[str, dict[str, float]] = {}
    with conn.cursor() as cur:
        cur.execute(query)
        for row in cur.fetchall():
            variant, assigned, activated, incentive_cost, avg_margin = row
            result[variant] = {
                "assigned": int(assigned),
                "activated": int(activated),
                "incentive_cost": float(incentive_cost),
                "avg_margin_before_incentive": float(avg_margin),
            }
    return result


def two_proportion_z_test(
    treatment_success: int,
    treatment_total: int,
    control_success: int,
    control_total: int,
) -> tuple[float, float, float, float, float]:
    p_treatment = treatment_success / treatment_total
    p_control = control_success / control_total
    lift = p_treatment - p_control

    pooled = (
        treatment_success + control_success
    ) / (
        treatment_total + control_total
    )

    pooled_se = math.sqrt(
        pooled
        * (1 - pooled)
        * (1 / treatment_total + 1 / control_total)
    )

    z_stat = lift / pooled_se
    p_value = math.erfc(abs(z_stat) / math.sqrt(2))

    unpooled_se = math.sqrt(
        p_treatment * (1 - p_treatment) / treatment_total
        + p_control * (1 - p_control) / control_total
    )

    ci_lower = lift - 1.96 * unpooled_se
    ci_upper = lift + 1.96 * unpooled_se

    return lift, z_stat, p_value, ci_lower, ci_upper


def main() -> None:
    with get_connection() as conn:
        summary = fetch_experiment_summary(conn)

    bonus = summary["bonus_10"]
    control = summary["control"]

    bonus_rate = bonus["activated"] / bonus["assigned"]
    control_rate = control["activated"] / control["assigned"]

    lift, z_stat, p_value, ci_lower, ci_upper = two_proportion_z_test(
        bonus["activated"],
        bonus["assigned"],
        control["activated"],
        control["assigned"],
    )

    relative_lift = lift / control_rate
    incremental_activations = lift * bonus["assigned"]

    break_even_value = (
        bonus["incentive_cost"] / incremental_activations
        if incremental_activations > 0
        else float("inf")
    )

    observed_control_margin = control["avg_margin_before_incentive"]
    payback_pct = (
        observed_control_margin / break_even_value * 100
        if break_even_value > 0
        else 0
    )

    print("Neobank £10 Activation Experiment")
    print("=" * 36)
    print(f"Bonus conversion:              {bonus_rate:.2%}")
    print(f"Control conversion:            {control_rate:.2%}")
    print(f"Absolute lift:                 {lift:.2%}")
    print(f"Relative lift:                 {relative_lift:.2%}")
    print(f"95% CI for absolute lift:      {ci_lower:.2%} to {ci_upper:.2%}")
    print(f"Z-statistic:                   {z_stat:.4f}")
    print(f"P-value:                       {p_value:.3e}")
    print(f"Estimated incremental users:   {incremental_activations:,.0f}")
    print(f"Total incentive cost:          £{bonus['incentive_cost']:,.2f}")
    print(f"Break-even margin per user:    £{break_even_value:,.2f}")
    print(f"Observed control margin:       £{observed_control_margin:,.2f}")
    print(f"Observed short-window payback: {payback_pct:.2f}%")

    print("\nDecision")
    print("-" * 8)
    if p_value < 0.05 and lift > 0:
        print("The incentive produced a statistically significant activation uplift.")
    else:
        print("The experiment did not show a statistically significant positive uplift.")

    if observed_control_margin < break_even_value:
        print(
            "Do not launch at the current £10 incentive based on the observed "
            "short-window economics."
        )
    else:
        print("The observed unit economics meet the estimated break-even threshold.")


if __name__ == "__main__":
    main()
