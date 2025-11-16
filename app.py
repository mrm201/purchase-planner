import json
import os
from datetime import datetime

import pandas as pd
import streamlit as st

from purchase_forecaster import PurchasePlanForecaster
from dataio.parsers import (
    read_any_table,
    df_to_sales_history,
    df_to_item_params,
    df_to_inventory,
    df_to_fcst_map,
)

st.set_page_config(page_title="Purchase Planning Portal", layout="wide")

BASE_DIR = os.path.dirname(__file__)
# NOTE: use "Samples" because that's how it exists on GitHub
SAMPLES_DIR = os.path.join(BASE_DIR, "Samples")


# ----------------- Helpers to load data -----------------


def load_sample_tables():
    """Load sample CSVs from the Samples/ folder."""
    sales_path = os.path.join(SAMPLES_DIR, "sales_history.csv")
    items_path = os.path.join(SAMPLES_DIR, "item_parameters.csv")
    inv_path = os.path.join(SAMPLES_DIR, "current_inventory.csv")
    fcst_path = os.path.join(SAMPLES_DIR, "sales_forecasts_n12.csv")

    sales_df = read_any_table(sales_path)
    items_df = read_any_table(items_path)
    inv_df = read_any_table(inv_path)
    fcst_df = read_any_table(fcst_path)

    return sales_df, items_df, inv_df, fcst_df


def load_uploaded_tables(upload_sales, upload_items, upload_inv, upload_fcst):
    """Load uploaded files into DataFrames."""
    sales_df = read_any_table(upload_sales) if upload_sales else None
    items_df = read_any_table(upload_items) if upload_items else None
    inv_df = read_any_table(upload_inv) if upload_inv else None
    fcst_df = read_any_table(upload_fcst) if upload_fcst else None
    return sales_df, items_df, inv_df, fcst_df


def build_plan(
    sales_df: pd.DataFrame,
    items_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    fcst_df: pd.DataFrame,
    start_month: str,
    num_months: int,
    service_level: float,
    review_period_days: int,
    include_in_transit: bool,
):
    """Convert DataFrames to model dicts, run forecaster, return result dict + DataFrame."""
    pf = PurchasePlanForecaster()

    sales_data = df_to_sales_history(sales_df)
    item_data = df_to_item_params(items_df)
    inv_data = df_to_inventory(inv_df)
    fcst_map = df_to_fcst_map(fcst_df)

    pf.load_sales_history(sales_data)
    pf.load_item_parameters(item_data)
    pf.load_current_inventory(inv_data)
    pf.load_sales_forecasts_n12(fcst_map)

    pf.generate_purchase_plan(
        start_month=start_month,
        num_months=num_months,
        service_level=service_level,
        review_period_days=review_period_days,
        include_in_transit=include_in_transit,
    )

    result = pf.export_to_json()
    plan_df = pd.DataFrame(result["forecasts"])
    return pf, result, plan_df


# ----------------- UI Layout -----------------

st.title("🧮 Purchase Planning Portal")

with st.sidebar:
    st.header("Configuration")

    load_samples = st.checkbox("Load sample data", value=True)

    st.markdown("**Planning Horizon**")
    start_month = st.text_input("Start month (YYYY-MM)", "2025-12")
    num_months = st.number_input("Number of months", 1, 24, 6)

    st.markdown("**Policy Parameters**")
    service_level = st.slider("Service level", 0.90, 0.99, 0.95, 0.01)
    review_period_days = st.number_input("Review period (days)", 7, 60, 30)
    include_in_transit = st.checkbox("Include in-transit stock", value=True)

    st.markdown("---")
    st.markdown("**Or upload your own datasets**")

    upload_sales = st.file_uploader("Sales History", type=["csv", "xlsx"])
    upload_items = st.file_uploader("Item Parameters", type=["csv", "xlsx"])
    upload_inv = st.file_uploader("Current Inventory", type=["csv", "xlsx"])
    upload_fcst = st.file_uploader("Sales Forecasts (N12)", type=["csv", "xlsx"])

    run_btn = st.button("Generate Plan", type="primary")


tab_plan, tab_dashboard = st.tabs(["📈 Planner", "📊 Dashboard"])

# ----------------- Planner Tab -----------------
with tab_plan:
    st.subheader("Planner")

    if run_btn:
        try:
            # Load data
            if load_samples:
                sales_df, items_df, inv_df, fcst_df = load_sample_tables()
            else:
                if not (upload_sales and upload_items and upload_inv and upload_fcst):
                    st.error("Please provide all four datasets (or turn ON 'Load sample data').")
                    st.stop()
                sales_df, items_df, inv_df, fcst_df = load_uploaded_tables(
                    upload_sales, upload_items, upload_inv, upload_fcst
                )

            # Run forecaster
            pf, result, plan_df = build_plan(
                sales_df=sales_df,
                items_df=items_df,
                inv_df=inv_df,
                fcst_df=fcst_df,
                start_month=start_month,
                num_months=int(num_months),
                service_level=float(service_level),
                review_period_days=int(review_period_days),
                include_in_transit=include_in_transit,
            )

            # Save for dashboard
            st.session_state["plan_df"] = plan_df.copy()

            # KPIs
            total_cost = plan_df["total_order_cost"].sum()
            total_units = plan_df["optimized_order_qty"].sum()
            unique_skus = plan_df["item_id"].nunique()

            c1, c2, c3 = st.columns(3)
            c1.metric("Total Planned Spend", f"${total_cost:,.0f}")
            c2.metric("Total Units", f"{int(total_units):,}")
            c3.metric("SKUs Planned", unique_skus)

            st.markdown("### Plan Table")

            edited_df = st.data_editor(
                plan_df,
                use_container_width=True,
                num_rows="dynamic",
                key="plan_editor",
            )

            # OPTIONAL: update in session with edits
            st.session_state["plan_df"] = edited_df.copy()

            st.markdown("### Exports")

            # JSON download
            json_str = json.dumps(result, indent=2)
            st.download_button(
                "Download JSON",
                data=json_str,
                file_name="purchase_plan.json",
                mime="application/json",
            )

            # Excel download via exporter in forecaster
            excel_path = "purchase_plan.xlsx"
            pf.export_to_excel(excel_path)
            with open(excel_path, "rb") as f:
                st.download_button(
                    "Download Excel",
                    data=f.read(),
                    file_name="purchase_plan.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

        except Exception as e:
            st.error(f"Error while generating plan: {e}")

    else:
        st.info("Configure parameters in the sidebar and click **Generate Plan**.")


# ----------------- Dashboard Tab -----------------
with tab_dashboard:
    st.subheader("Purchase Plan Dashboard")

    if "plan_df" not in st.session_state:
        st.info("Generate a plan first in the Planner tab.")
    else:
        df = st.session_state["plan_df"].copy()

        # ensure proper datetime for filtering
        df["forecast_month"] = pd.to_datetime(df["forecast_month"], format="%Y-%m", errors="coerce")
        df = df.dropna(subset=["forecast_month"])

        # --- Date range filters ---
        min_date = df["forecast_month"].min()
        max_date = df["forecast_month"].max()

        col_fr, col_to = st.columns(2)
        from_date = col_fr.date_input("From month", min_date.date() if pd.notna(min_date) else None)
        to_date = col_to.date_input("To month", max_date.date() if pd.notna(max_date) else None)

        if from_date and to_date:
            df = df[(df["forecast_month"].dt.date >= from_date) &
                    (df["forecast_month"].dt.date <= to_date)]

        # --- Category / Segment / SKU filters ---
        cats = sorted(df["category"].dropna().unique()) if "category" in df.columns else []
        segs = sorted(df["segment"].dropna().unique()) if "segment" in df.columns else []
        skus = sorted(df["item_id"].unique())

        c1, c2, c3 = st.columns(3)
        sel_cat = c1.selectbox("Category", ["All"] + cats) if cats else "All"
        sel_seg = c2.selectbox("Segment", ["All"] + segs) if segs else "All"
        sel_sku = c3.selectbox("SKU", skus if skus else [""])

        if sel_cat != "All":
            df = df[df["category"] == sel_cat]
        if sel_seg != "All":
            df = df[df["segment"] == sel_seg]
        if sel_sku:
            df = df[df["item_id"] == sel_sku]

        if df.empty:
            st.warning("No data for the selected filters.")
        else:
            df_sku = df.sort_values("forecast_month")

            # columns like Jan-2026 etc.
            month_labels = df_sku["forecast_month"].dt.strftime("%b-%Y").tolist()
            months_key = df_sku["forecast_month"].dt.strftime("%Y-%m").tolist()

            # map row label -> column in df_sku
            metric_map = [
                ("Opening Inventory", "opening_inventory_units"),
                ("Planned Intake", "planned_intake_units"),
                ("Actual Intake", "actual_intake_units"),
                ("Forecasted Sales", "forecasted_sales_units"),
                ("Actual Sales", "actual_sales_units"),
                ("Closing Inventory", "closing_inventory_units"),
                ("Future Cover (months)", "future_cover_months"),
            ]

            rows = []
            for label, col_name in metric_map:
                row = {"Metric": label}
                for mk, ml in zip(months_key, month_labels):
                    mask = df_sku["forecast_month"].dt.strftime("%Y-%m") == mk
                    vals = df_sku.loc[mask, col_name]
                    val = float(vals.iloc[0]) if not vals.empty else 0.0
                    row[ml] = val
                rows.append(row)

            layout_df = pd.DataFrame(rows).set_index("Metric")

            st.write(f"**SKU:** {df_sku['item_id'].iloc[0]} — {df_sku['item_name'].iloc[0]}")
            if "category" in df_sku.columns and "segment" in df_sku.columns:
                st.caption(
                    f"Category: {df_sku['category'].iloc[0] or '-'} | "
                    f"Segment: {df_sku['segment'].iloc[0] or '-'}"
                )

            st.dataframe(layout_df, use_container_width=True)