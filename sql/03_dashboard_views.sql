--
-- PostgreSQL database dump
--

\restrict ih7vDs4kphk4PeVW8xd5XTuoIzaNPfdDchvulz2sDSayQiFdGzlV8gUdrBLCgr0

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg13+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg13+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: vw_channel_performance; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_channel_performance AS
 WITH funded AS (
         SELECT c.acquisition_channel,
            count(*) AS signups,
            count(*) FILTER (WHERE (EXISTS ( SELECT 1
                   FROM public.product_events pe
                  WHERE ((pe.customer_id = c.customer_id) AND ((pe.event_name)::text = 'first_funding'::text))))) AS funded_customers
           FROM public.customers c
          GROUP BY c.acquisition_channel
        ), spend AS (
         SELECT marketing_spend.acquisition_channel,
            sum(marketing_spend.spend_gbp) AS total_spend_gbp
           FROM public.marketing_spend
          GROUP BY marketing_spend.acquisition_channel
        ), customer_metrics AS (
         SELECT a.customer_id,
            sum(t.amount_gbp) FILTER (WHERE ((t.status)::text = 'completed'::text)) AS transaction_volume_gbp,
            sum((((t.fee_revenue_gbp + t.interchange_revenue_gbp) + t.fx_spread_revenue_gbp) - t.processing_cost_gbp)) FILTER (WHERE ((t.status)::text = 'completed'::text)) AS contribution_margin_gbp
           FROM (public.accounts a
             JOIN public.transactions t ON ((a.account_id = t.account_id)))
          GROUP BY a.customer_id
        ), channel_value AS (
         SELECT c.acquisition_channel,
            avg(cm.transaction_volume_gbp) AS avg_transaction_volume_gbp,
            avg(cm.contribution_margin_gbp) AS avg_contribution_margin_gbp
           FROM (public.customers c
             JOIN customer_metrics cm ON ((c.customer_id = cm.customer_id)))
          GROUP BY c.acquisition_channel
        )
 SELECT f.acquisition_channel,
    f.signups,
    f.funded_customers,
    round(((100.0 * (f.funded_customers)::numeric) / (f.signups)::numeric), 2) AS signup_to_funding_pct,
    round(s.total_spend_gbp, 2) AS acquisition_spend_gbp,
    round((s.total_spend_gbp / (f.signups)::numeric), 2) AS cac_gbp,
    round((s.total_spend_gbp / (f.funded_customers)::numeric), 2) AS cost_per_funded_customer_gbp,
    round(v.avg_transaction_volume_gbp, 2) AS avg_transaction_volume_gbp,
    round(v.avg_contribution_margin_gbp, 2) AS avg_contribution_margin_gbp
   FROM ((funded f
     JOIN spend s ON (((f.acquisition_channel)::text = (s.acquisition_channel)::text)))
     JOIN channel_value v ON (((f.acquisition_channel)::text = (v.acquisition_channel)::text)));


--
-- Name: vw_dashboard_kpis; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_dashboard_kpis AS
 SELECT ( SELECT count(*) AS count
           FROM public.customers) AS total_signups,
    ( SELECT count(*) AS count
           FROM public.kyc_cases
          WHERE ((kyc_cases.status)::text = 'approved'::text)) AS kyc_approved,
    ( SELECT count(*) AS count
           FROM public.accounts) AS accounts_opened,
    ( SELECT count(*) AS count
           FROM public.product_events
          WHERE ((product_events.event_name)::text = 'first_funding'::text)) AS funded_customers,
    ( SELECT count(*) AS count
           FROM public.product_events
          WHERE ((product_events.event_name)::text = 'first_transaction'::text)) AS transacting_customers,
    ( SELECT count(*) AS count
           FROM public.transactions) AS total_transactions,
    ( SELECT round(sum(transactions.amount_gbp) FILTER (WHERE ((transactions.status)::text = 'completed'::text)), 2) AS round
           FROM public.transactions) AS completed_transaction_volume_gbp,
    ( SELECT round(sum((((transactions.fee_revenue_gbp + transactions.interchange_revenue_gbp) + transactions.fx_spread_revenue_gbp) - transactions.processing_cost_gbp)) FILTER (WHERE ((transactions.status)::text = 'completed'::text)), 2) AS round
           FROM public.transactions) AS total_contribution_margin_gbp;


--
-- Name: vw_experiment_performance; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_experiment_performance AS
 WITH funded AS (
         SELECT DISTINCT product_events.customer_id
           FROM public.product_events
          WHERE ((product_events.event_name)::text = 'first_funding'::text)
        ), customer_economics AS (
         SELECT a.customer_id,
            sum((((t.fee_revenue_gbp + t.interchange_revenue_gbp) + t.fx_spread_revenue_gbp) - t.processing_cost_gbp)) FILTER (WHERE ((t.status)::text = 'completed'::text)) AS margin_before_incentive_gbp,
            sum(t.incentive_cost_gbp) FILTER (WHERE ((t.status)::text = 'completed'::text)) AS incentive_cost_gbp
           FROM (public.accounts a
             LEFT JOIN public.transactions t ON ((a.account_id = t.account_id)))
          GROUP BY a.customer_id
        )
 SELECT ea.variant,
    count(*) AS assigned_customers,
    count(*) FILTER (WHERE (f.customer_id IS NOT NULL)) AS activated_customers,
    round(((100.0 * (count(*) FILTER (WHERE (f.customer_id IS NOT NULL)))::numeric) / (count(*))::numeric), 2) AS activation_rate_pct,
    round(sum(COALESCE(ce.incentive_cost_gbp, (0)::numeric)), 2) AS total_incentive_cost_gbp,
    round(avg(ce.margin_before_incentive_gbp) FILTER (WHERE (f.customer_id IS NOT NULL)), 2) AS avg_margin_before_incentive_gbp,
    round(avg((ce.margin_before_incentive_gbp - COALESCE(ce.incentive_cost_gbp, (0)::numeric))) FILTER (WHERE (f.customer_id IS NOT NULL)), 2) AS avg_margin_after_incentive_gbp
   FROM ((public.experiment_assignments ea
     LEFT JOIN funded f ON ((ea.customer_id = f.customer_id)))
     LEFT JOIN customer_economics ce ON ((ea.customer_id = ce.customer_id)))
  GROUP BY ea.variant;


--
-- Name: vw_fx_customer_segments; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_fx_customer_segments AS
 WITH funded_customers AS (
         SELECT DISTINCT a.customer_id,
            a.account_id
           FROM (public.accounts a
             JOIN public.transactions t ON ((a.account_id = t.account_id)))
          WHERE (((t.transaction_type)::text = 'cash_in'::text) AND ((t.status)::text = 'completed'::text))
        ), customer_metrics AS (
         SELECT fc.customer_id,
                CASE
                    WHEN (count(*) FILTER (WHERE (((t.transaction_type)::text = 'fx_exchange'::text) AND ((t.status)::text = 'completed'::text))) > 0) THEN 'FX user'::text
                    ELSE 'Non-FX user'::text
                END AS customer_segment,
            count(*) FILTER (WHERE ((t.status)::text = 'completed'::text)) AS completed_transactions,
            sum(t.amount_gbp) FILTER (WHERE ((t.status)::text = 'completed'::text)) AS transaction_volume_gbp,
            sum((((t.fee_revenue_gbp + t.interchange_revenue_gbp) + t.fx_spread_revenue_gbp) - t.processing_cost_gbp)) FILTER (WHERE ((t.status)::text = 'completed'::text)) AS contribution_margin_gbp
           FROM (funded_customers fc
             JOIN public.transactions t ON ((fc.account_id = t.account_id)))
          GROUP BY fc.customer_id
        )
 SELECT customer_segment,
    count(*) AS customers,
    round(avg(completed_transactions), 2) AS avg_completed_transactions,
    round(avg(transaction_volume_gbp), 2) AS avg_transaction_volume_gbp,
    round(avg(contribution_margin_gbp), 2) AS avg_contribution_margin_gbp
   FROM customer_metrics
  GROUP BY customer_segment;


--
-- Name: vw_fx_retention; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_fx_retention AS
 WITH first_funding AS (
         SELECT a.customer_id,
            a.account_id,
            min(t.transaction_ts) AS first_funding_ts
           FROM (public.accounts a
             JOIN public.transactions t ON ((a.account_id = t.account_id)))
          WHERE (((t.transaction_type)::text = 'cash_in'::text) AND ((t.status)::text = 'completed'::text))
          GROUP BY a.customer_id, a.account_id
        ), eligible AS (
         SELECT first_funding.customer_id,
            first_funding.account_id,
            first_funding.first_funding_ts
           FROM first_funding
          WHERE (first_funding.first_funding_ts <= '2026-07-02 23:59:59'::timestamp without time zone)
        ), customer_activity AS (
         SELECT e.customer_id,
                CASE
                    WHEN (EXISTS ( SELECT 1
                       FROM public.transactions fx
                      WHERE ((fx.account_id = e.account_id) AND ((fx.transaction_type)::text = 'fx_exchange'::text) AND ((fx.status)::text = 'completed'::text)))) THEN 'FX user'::text
                    ELSE 'Non-FX user'::text
                END AS customer_segment,
            count(t.transaction_id) FILTER (WHERE (((t.status)::text = 'completed'::text) AND ((t.transaction_type)::text <> 'cash_in'::text) AND (t.transaction_ts >= (e.first_funding_ts + '30 days'::interval)) AND (t.transaction_ts < (e.first_funding_ts + '60 days'::interval)))) AS d30_transactions
           FROM (eligible e
             LEFT JOIN public.transactions t ON ((e.account_id = t.account_id)))
          GROUP BY e.customer_id, e.account_id, e.first_funding_ts
        )
 SELECT customer_segment,
    count(*) AS eligible_customers,
    count(*) FILTER (WHERE (d30_transactions >= 3)) AS retained_d30,
    round(((100.0 * (count(*) FILTER (WHERE (d30_transactions >= 3)))::numeric) / (count(*))::numeric), 2) AS d30_retention_pct
   FROM customer_activity
  GROUP BY customer_segment;


--
-- Name: vw_retention_cohorts; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_retention_cohorts AS
 WITH first_funding AS (
         SELECT a.customer_id,
            min(t.transaction_ts) AS first_funding_ts
           FROM (public.accounts a
             JOIN public.transactions t ON ((a.account_id = t.account_id)))
          WHERE (((t.transaction_type)::text = 'cash_in'::text) AND ((t.status)::text = 'completed'::text))
          GROUP BY a.customer_id
        ), eligible AS (
         SELECT first_funding.customer_id,
            first_funding.first_funding_ts,
            (date_trunc('month'::text, first_funding.first_funding_ts))::date AS funding_cohort
           FROM first_funding
          WHERE (first_funding.first_funding_ts < '2026-06-01 00:00:00'::timestamp without time zone)
        ), activity AS (
         SELECT e.customer_id,
            e.funding_cohort,
            count(*) FILTER (WHERE (((t.status)::text = 'completed'::text) AND ((t.transaction_type)::text <> 'cash_in'::text) AND (t.transaction_ts >= (e.first_funding_ts + '30 days'::interval)) AND (t.transaction_ts < (e.first_funding_ts + '60 days'::interval)))) AS d30_transactions,
            count(*) FILTER (WHERE (((t.status)::text = 'completed'::text) AND ((t.transaction_type)::text <> 'cash_in'::text) AND (t.transaction_ts >= (e.first_funding_ts + '60 days'::interval)) AND (t.transaction_ts < (e.first_funding_ts + '90 days'::interval)))) AS d60_transactions
           FROM ((eligible e
             JOIN public.accounts a ON ((e.customer_id = a.customer_id)))
             LEFT JOIN public.transactions t ON ((a.account_id = t.account_id)))
          GROUP BY e.customer_id, e.funding_cohort
        )
 SELECT funding_cohort,
    count(*) AS funded_customers,
    count(*) FILTER (WHERE (d30_transactions >= 3)) AS retained_d30,
    round(((100.0 * (count(*) FILTER (WHERE (d30_transactions >= 3)))::numeric) / (count(*))::numeric), 2) AS d30_retention_pct,
    count(*) FILTER (WHERE (d60_transactions >= 3)) AS retained_d60,
    round(((100.0 * (count(*) FILTER (WHERE (d60_transactions >= 3)))::numeric) / (count(*))::numeric), 2) AS d60_retention_pct
   FROM activity
  GROUP BY funding_cohort
  ORDER BY funding_cohort;


--
-- Name: vw_transaction_economics; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_transaction_economics AS
 SELECT transaction_type,
    count(*) FILTER (WHERE ((status)::text = 'completed'::text)) AS completed_transactions,
    round(sum(amount_gbp) FILTER (WHERE ((status)::text = 'completed'::text)), 2) AS transaction_volume_gbp,
    round(sum(((fee_revenue_gbp + interchange_revenue_gbp) + fx_spread_revenue_gbp)) FILTER (WHERE ((status)::text = 'completed'::text)), 2) AS revenue_gbp,
    round(sum(processing_cost_gbp) FILTER (WHERE ((status)::text = 'completed'::text)), 2) AS processing_cost_gbp,
    round(sum((((fee_revenue_gbp + interchange_revenue_gbp) + fx_spread_revenue_gbp) - processing_cost_gbp)) FILTER (WHERE ((status)::text = 'completed'::text)), 2) AS contribution_margin_gbp,
    round(avg((((fee_revenue_gbp + interchange_revenue_gbp) + fx_spread_revenue_gbp) - processing_cost_gbp)) FILTER (WHERE ((status)::text = 'completed'::text)), 4) AS avg_margin_per_transaction_gbp
   FROM public.transactions
  GROUP BY transaction_type;


--
-- PostgreSQL database dump complete
--

\unrestrict ih7vDs4kphk4PeVW8xd5XTuoIzaNPfdDchvulz2sDSayQiFdGzlV8gUdrBLCgr0

