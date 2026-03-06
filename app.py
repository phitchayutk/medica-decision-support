from __future__ import annotations

import io
from dataclasses import asdict

import pandas as pd
import streamlit as st

from core.config import GameAssumptions
from core.data_loader import load_game_data
from core.explainability import executive_summary
from core.recommender import build_recommendation
from core.state_builder import build_derived_state

st.set_page_config(page_title="Medica Scientific Decision Support", layout="wide")

ASSUMPTIONS = GameAssumptions()


@st.cache_data(show_spinner=False)
def parse_uploaded_file(file_bytes: bytes):
    return load_game_data(io.BytesIO(file_bytes))


st.title("Medica Scientific Decision Support Script")
st.caption("Queue-stability controller for a tightly coupled production, inventory, workforce, and finance system.")

with st.sidebar:
    st.header("Input")
    uploaded = st.file_uploader("Upload Medica export (.xlsx)", type=["xlsx"])
    st.markdown("Recommended file: the full game export with Standard, Custom, Inventory, Financial, and WorkForce sheets.")

if not uploaded:
    st.info("Upload the exported Excel file to start the analysis.")
    st.stop()

file_bytes = uploaded.read()
states, raw_tables, load_warnings = parse_uploaded_file(file_bytes)

if not states:
    st.error("No daily state rows were parsed from the workbook.")
    st.stop()

max_day = max(s.day for s in states)
selected_day = st.sidebar.slider("Select day to analyze", min_value=0, max_value=max_day, value=max_day)
state_index = next(i for i, s in enumerate(states) if s.day == selected_day)
state = states[state_index]
derived = build_derived_state(states, state_index, ASSUMPTIONS)
recommendation = build_recommendation(state, derived, ASSUMPTIONS)

if load_warnings:
    for warning in load_warnings:
        st.warning(warning)

st.subheader("Executive Summary")
st.write(executive_summary(derived, recommendation))

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Bottleneck", derived.current_bottleneck)
k2.metric("Regime", derived.current_regime)
k3.metric("Raw Coverage Days", f"{derived.raw_coverage_days:.2f}")
k4.metric("Custom Congestion", f"{derived.cus_congestion_score:.2f}")
k5.metric("Stress Score", f"{derived.system_stress_score:.2f}")
k6.metric("Endgame Robustness", f"{derived.endgame_robustness_score:.2f}")

st.divider()

rec_tab, diag_tab, trend_tab, data_tab = st.tabs(["Recommended Settings", "Diagnostics", "Trend View", "Raw Data Preview"])

with rec_tab:
    st.subheader("Main Output — copy these values into the game")
    rec_df = pd.DataFrame([
        ["Standard Order Frequency", recommendation.standard_order_frequency],
        ["Standard Order Size", recommendation.standard_order_size],
        ["Standard S1 Allocation %", recommendation.standard_s1_allocation_pct],
        ["Desired S1 Machines", recommendation.desired_s1_machines],
        ["Initial Batch Size", recommendation.initial_batch_size],
        ["Manual Workday Length in Shifts", recommendation.manual_workday_length_in_shifts],
        ["Final Batch Size", recommendation.final_batch_size],
        ["Standard Product Price", recommendation.standard_product_price],
        ["S2 Allocation to First Pass %", recommendation.s2_allocation_to_first_pass_pct],
        ["Desired S2 Machines", recommendation.desired_s2_machines],
        ["Desired S3 Machines", recommendation.desired_s3_machines],
        ["Inventory ROP", recommendation.inventory_rop],
        ["Inventory ROQ", recommendation.inventory_roq],
        ["Get Loan", recommendation.get_loan],
        ["Pay Loan", recommendation.pay_loan],
        ["Desired Employees", recommendation.desired_employees],
    ], columns=["Setting", "Recommended Value"])
    st.dataframe(rec_df, use_container_width=True, hide_index=True)

    st.subheader("Why these recommendations")
    for key, value in recommendation.rationale.items():
        st.markdown(f"**{key.replace('_', ' ').title()}**: {value}")

    st.subheader("Scorecard")
    score_df = pd.DataFrame(list(recommendation.scores.items()), columns=["Dimension", "Score"])
    st.dataframe(score_df, use_container_width=True, hide_index=True)

with diag_tab:
    left, right = st.columns(2)
    with left:
        st.markdown("### Warnings")
        if derived.warnings:
            for warning in derived.warnings:
                st.warning(warning)
        else:
            st.success("No critical warning flags at the selected day.")

        st.markdown("### Diagnostics")
        diag_rows = [
            ("Raw On Hand", derived.raw_on_hand),
            ("Raw On Order", derived.raw_on_order),
            ("Inventory Position", derived.raw_inventory_position),
            ("Expected Parts / Day", derived.expected_parts_per_day),
            ("Standard Total Queue", derived.std_total_queue),
            ("Custom Total WIP", derived.cus_total_wip),
            ("Custom WIP Ratio", derived.cus_wip_ratio),
            ("S1 Pressure", derived.s1_pressure),
            ("S2 Pressure", derived.s2_pressure),
            ("S3 Pressure", derived.s3_pressure),
            ("Manual Pressure", derived.manual_pressure),
            ("Cash Buffer Adequacy", derived.cash_buffer_adequacy),
            ("Loan Urgency", derived.loan_urgency_score),
        ]
        st.dataframe(pd.DataFrame(diag_rows, columns=["Metric", "Value"]), use_container_width=True, hide_index=True)

    with right:
        st.markdown("### Forecast (next 15 days proxy)")
        st.info(recommendation.queue_imbalance_warning)
        st.info(recommendation.cash_risk_warning)
        forecast_rows = [
            ("Selected Day", recommendation.day),
            ("Current Bottleneck", recommendation.current_bottleneck),
            ("Current Regime", recommendation.current_regime),
            ("Raw Coverage Days", recommendation.raw_coverage_days),
            ("Custom Congestion Score", recommendation.custom_congestion_score),
        ]
        st.dataframe(pd.DataFrame(forecast_rows, columns=["Item", "Value"]), use_container_width=True, hide_index=True)

with trend_tab:
    st.subheader("Historical trend charts")
    hist = pd.DataFrame([{**asdict(s)} for s in states])
    hist["std_total_queue"] = hist[["std_q1", "std_q2", "std_q3", "std_q4", "std_q5"]].sum(axis=1)
    hist["cus_total_wip"] = hist[["cus_q1", "cus_q2_first", "cus_q2_second", "cus_q3"]].sum(axis=1)

    st.line_chart(hist.set_index("day")[["inventory_level"]], height=250)
    st.line_chart(hist.set_index("day")[["std_total_queue", "cus_total_wip"]], height=250)
    st.line_chart(hist.set_index("day")[["cash_on_hand", "debt"]], height=250)
    st.line_chart(hist.set_index("day")[["cus_avg_lead_time", "std_market_price", "cus_actual_price"]], height=250)

with data_tab:
    st.subheader("Raw data preview")
    sheet_choice = st.selectbox("Select sheet", list(raw_tables.keys()))
    st.dataframe(raw_tables[sheet_choice], use_container_width=True)

st.divider()
st.caption("Best-effort decision support version built directly against the real Medica export schema.")
