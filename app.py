import streamlit as st
import pandas as pd

from core.config import ASSUMPTIONS
from core.data_loader import load_game_data
from core.explainability import executive_summary
from core.recommender import build_recommendation
from core.state_builder import build_derived_state


st.set_page_config(page_title="Medica Scientific Decision Support Script", layout="wide")
st.title("Medica Scientific Decision Support Script")
st.caption("Queue-stability controller for a tightly coupled production, inventory, workforce, and finance system.")

uploaded_file = st.file_uploader("Upload Medica Scientific Excel export", type=["xlsx"])

if uploaded_file is None:
    st.info("Please upload an .xlsx export file to begin.")
    st.stop()

try:
    state, derived, raw = build_derived_state(uploaded_file, ASSUMPTIONS)
    recommendation = build_recommendation(state, derived, ASSUMPTIONS)
    summary = executive_summary(state, derived, recommendation)
except Exception as e:
    st.exception(e)
    st.stop()

st.header("Executive Summary")
st.write(summary["summary_text"])

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Bottleneck", derived.bottleneck)
c2.metric("Regime", derived.current_regime)
c3.metric("Raw Coverage Days", f"{derived.raw_coverage_days:.2f}")
c4.metric("Custom Congestion", f"{derived.custom_congestion_score:.2f}")
c5.metric("Stress Score", f"{derived.stress_score:.2f}")

tabs = st.tabs(["Recommended Settings", "Diagnostics", "Trend View", "Raw Data Preview"])

with tabs[0]:
    st.subheader("Main Output — copy these values into the game")
    rec_df = pd.DataFrame(
        {
            "Setting": [
                "Standard Order Frequency",
                "Standard Order Size",
                "Standard S1 Allocation %",
                "Desired S1 Machines",
                "Initial Batch Size",
                "Manual Workday Length in Shifts",
                "Final Batch Size",
                "Standard Product Price",
                "S2 Allocation to First Pass %",
                "Desired S2 Machines",
                "Desired S3 Machines",
                "Inventory ROP",
                "Inventory ROQ",
                "Get Loan",
                "Pay Loan",
                "Desired Employees",
            ],
            "Recommended Value": [
                recommendation.standard_order_frequency,
                recommendation.standard_order_size,
                recommendation.standard_s1_allocation_pct,
                recommendation.desired_s1_machines,
                recommendation.initial_batch_size,
                recommendation.manual_workday_length_shifts,
                recommendation.final_batch_size,
                recommendation.standard_product_price,
                recommendation.s2_allocation_first_pass_pct,
                recommendation.desired_s2_machines,
                recommendation.desired_s3_machines,
                recommendation.inventory_rop,
                recommendation.inventory_roq,
                recommendation.get_loan,
                recommendation.pay_loan,
                recommendation.desired_employees,
            ],
        }
    )
    st.dataframe(rec_df, use_container_width=True, hide_index=True)

    st.subheader("Why these recommendations")
    for line in summary["why_lines"]:
        st.write(line)

with tabs[1]:
    st.subheader("Diagnostics")
    diag_df = pd.DataFrame(
        {
            "Metric": [
                "Raw Coverage Days",
                "Custom Congestion Score",
                "Stress Score",
                "Endgame Robustness",
                "Std Avg Demand / Day",
                "Custom Demand / Day",
                "Expected Parts / Day",
                "S1 Utilization",
                "S2 Utilization",
                "S3 Utilization",
                "Manual Utilization",
                "Std Queue Before Batch",
                "Std Manual Queue",
                "Std FG Inventory",
                "Custom Q1",
                "Custom Q2 First",
                "Custom Q2 Second",
                "Custom Q3",
                "Custom Lead Time",
            ],
            "Value": [
                round(derived.raw_coverage_days, 2),
                round(derived.custom_congestion_score, 2),
                round(derived.stress_score, 2),
                round(derived.endgame_robustness, 2),
                round(derived.std_avg_demand_per_day, 2),
                round(derived.custom_avg_demand_per_day, 2),
                round(derived.expected_parts_per_day, 2),
                round(derived.s1_utilization, 2),
                round(derived.s2_utilization, 2),
                round(derived.s3_utilization, 2),
                round(derived.manual_utilization, 2),
                round(state.standard.q_before_batch, 2),
                round(state.standard.q_manual, 2),
                round(state.standard.fg_inventory, 2),
                round(state.custom.q1, 2),
                round(state.custom.q2_first, 2),
                round(state.custom.q2_second, 2),
                round(state.custom.q3, 2),
                round(state.custom.average_lead_time, 2),
            ],
        }
    )
    st.dataframe(diag_df, use_container_width=True, hide_index=True)

with tabs[2]:
    st.subheader("Trend View")
    for sheet_name, df in raw.items():
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        if "Day" not in df.columns:
            continue
        st.markdown(f"**{sheet_name}**")
        numeric_cols = [c for c in df.columns if c != "Day" and pd.api.types.is_numeric_dtype(df[c])]
        if numeric_cols:
            st.line_chart(df.set_index("Day")[numeric_cols].tail(50), height=250)

with tabs[3]:
    st.subheader("Raw Data Preview")
    for sheet_name, df in raw.items():
        st.markdown(f"**{sheet_name}**")
        st.dataframe(df.tail(20), use_container_width=True)