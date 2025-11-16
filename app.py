"""Purchase Plan Forecaster – editable Streamlit UI wired to PurchasePlanForecaster."""

import json
import os
from datetime import datetime

import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta

from purchase_forecaster import PurchasePlanForecaster

st.set_page_config(
    page_title="Purchase Plan Forecaster",
    layout="wide",
    page_icon="📦",
)

# ---------- Session state ----------

if "forecasts" not in st.session_state:
    st.session_state["forecasts"] = None
if "edited_plan" not in st.session_state:
    st.session_state["edited_plan"] = None
if "manual_adjustments" not in st.session_state:
    st.session_state["manual_adjustments"] = {}

# ---------- Sidebar configuration ----------

with st.sidebar:
    st.title("⚙️ Configuration")

    start_month = st.text_input(
        "Start Month (YYYY-MM)", value="2025-12", key="start_month_input"
    )
    num_months = st.number_input(
        "Forecast Horizon (months)", min_value=1, max_value=24, value=6, key="horizon_input"
    )
    data_dir = st.text_input("Data Directory", value="data", key="data_dir_input")

    st.divider()
    st.subheader("✏️ Edit Mode")

    edit_enabled = st.toggle("Enable Plan Editing", value=True)

    if edit_enabled:
        current_month = datetime.now().strftime("%Y-%m")
        cutoff_date = datetime.strptime(current_month, "%Y-%m") + relativedelta(months=2)
        cutoff_month = cutoff_date.strftime("%Y-%m")
        st.info(f"📅 Editable from: **{cutoff_month}** onwards")

    st.divider()

    run_btn = st.button("🚀 Generate Plan", type="primary", use_container_width=True)

# main title
st.title("📦 Purchase Plan Forecaster")
st.markdown("Generate optimal purchase recommendations with real-time editing capability")

# ---------- File upload section ----------

with st.expander("📁 Upload Data Files", expanded=not run_btn):
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Required Files (JSON)**")
        sales_history_file = st.file_uploader(
            "sales_history.json", type=["json"], key="sales_hist"
        )
        item_params_file = st.file_uploader(
            "item_parameters.json", type=["json"], key="item_params"
        )
        current_inventory_file = st.file_uploader(
            "current_inventory.json", type=["json"], key="curr_inv"
        )
        sales_n12_file = st.file_uploader(
            "sales_forecasts_n12.json", type=["json"], key="n12"
        )

    with col2:
        st.markdown(
            "_Optional advanced JSON files (not used yet – reserved for v2 logic)_"
        )
        st.caption(
            "- promotional_calendar.json\n"
            "- supplier_reliability.json\n"
            "- price_forecasts.json\n"
            "- demand_variability.json\n"
            "- volume_discounts.json"
        )

# ---------- Generate plan ----------

if run_btn:
    try:
        with st.spinner("Loading data and generating plan..."):
            pf = PurchasePlanForecaster()

            # Required data – either uploaded, or loaded from data_dir
            if sales_history_file:
                pf.load_sales_history(json.load(sales_history_file))
            else:
                with open(os.path.join(data_dir, "sales_history.json")) as f:
                    pf.load_sales_history(json.load(f))

            if item_params_file:
                pf.load_item_parameters(json.load(item_params_file))
            else:
                with open(os.path.join(data_dir, "item_parameters.json")) as f:
                    pf.load_item_parameters(json.load(f))

            if current_inventory_file:
                pf.load_current_inventory(json.load(current_inventory_file))
            else:
                with open(os.path.join(data_dir, "current_inventory.json")) as f:
                    pf.load_current_inventory(json.load(f))

            if sales_n12_file:
                pf.load_sales_forecasts_n12(json.load(sales_n12_file))
            else:
                with open(os.path.join(data_dir, "sales_forecasts_n12.json")) as f:
                    pf.load_sales_forecasts_n12(json.load(f))

            # optional JSONs (not yet used in engine) – safely ignore if missing on disk
            optional_files = [
                "promotional_calendar.json",
                "supplier_reliability.json",
                "price_forecasts.json",
                "demand_variability.json",
                "volume_discounts.json",
            ]
            for fname in optional_files:
                path = os.path.join(data_dir, fname)
                if os.path.exists(path):
                    # placeholder: keep for future integration; do nothing for now
                    pass

            # Generate purchase plan
            forecasts = pf.generate_purchase_plan(
                start_month=start_month,
                num_months=int(num_months),
            )

            # Convert to plain dicts for DataFrame & session
            st.session_state["forecasts"] = [
                vars(f) if hasattr(f, "__dict__") else f for f in forecasts
            ]
            st.session_state["forecaster"] = pf

        st.success(f"✓ Generated {len(forecasts)} forecast rows!")

    except FileNotFoundError as e:
        st.error(f"❌ Missing required file: {e}")
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        st.exception(e)

# ---------- Display & edit plan ----------

if st.session_state["forecasts"]:
    st.divider()
    forecasts_data = st.session_state["forecasts"]
    df = pd.DataFrame(forecasts_data)

    # Map engine columns to what the UI expects (if not already present)
    # Our engine provides:
    # - opening_inventory_units
    # - closing_inventory_units
    # - future_cover_months
    # We'll derive UI names from these.
    if "opening_stock" not in df.columns and "opening_inventory_units" in df.columns:
        df["opening_stock"] = df["opening_inventory_units"]
    if "ending_stock_after_order" not in df.columns and "closing_inventory_units" in df.columns:
        df["ending_stock_after_order"] = df["closing_inventory_units"]
    if "stock_cover_months" not in df.columns and "future_cover_months" in df.columns:
        df["stock_cover_months"] = df["future_cover_months"]
    if "in_transit" not in df.columns:
        df["in_transit"] = 0
    if "adjusted_safety_stock" not in df.columns:
        df["adjusted_safety_stock"] = 0
    if "stockout_risk" not in df.columns:
        df["stockout_risk"] = 0  # or False

    # ---------- Summary metrics ----------

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        total_orders = df.get("optimized_order_qty", pd.Series([0])).sum()
        st.metric("Total Orders", f"{total_orders:,.0f}")

    with col2:
        total_cost = df.get("total_order_cost", pd.Series([0.0])).sum()
        st.metric("Total Cost", f"${total_cost:,.2f}")

    with col3:
        stockout_count = df.get("stockout_risk", pd.Series([0])).sum()
        st.metric("Stockout Risks", int(stockout_count))

    with col4:
        avg_cover = df.get("stock_cover_months", pd.Series([0.0])).replace(
            [float("inf")], 0
        ).mean()
        st.metric("Avg Cover", f"{avg_cover:.1f} mo")

    with col5:
        items_count = df.get("item_id", pd.Series([])).nunique()
        st.metric("Items", items_count)

    st.divider()

    # ---------- Editable plan table ----------

    if edit_enabled:
        st.subheader("📝 Editable Purchase Plan")

        current_month = datetime.now().strftime("%Y-%m")
        current_date = datetime.strptime(current_month, "%Y-%m")
        cutoff_date = current_date + relativedelta(months=2)
        cutoff_month = cutoff_date.strftime("%Y-%m")

        # Add editable flag
        if "forecast_month" in df.columns:
            df["is_editable"] = df["forecast_month"] >= cutoff_month
        else:
            df["is_editable"] = False

        df["original_order_qty"] = df.get("optimized_order_qty", 0)

        # Apply any manual adjustments
        if st.session_state["manual_adjustments"]:
            for key, new_qty in st.session_state["manual_adjustments"].items():
                item_id, month = key.split("_", 1)
                mask = (df["item_id"] == item_id) & (df["forecast_month"] == month)
                if "optimized_order_qty" in df.columns:
                    df.loc[mask, "optimized_order_qty"] = new_qty

        # Configure columns
        column_config = {
            "forecast_month": st.column_config.TextColumn("Month", width="small"),
            "item_id": st.column_config.TextColumn("SKU", width="small"),
            "item_name": st.column_config.TextColumn("Item", width="medium"),
            "adjusted_demand": st.column_config.NumberColumn(
                "Demand", width="small", format="%d"
            ),
            "opening_stock": st.column_config.NumberColumn(
                "Opening", width="small", format="%d"
            ),
            "in_transit": st.column_config.NumberColumn(
                "In-Transit", width="small", format="%d"
            ),
            "adjusted_safety_stock": st.column_config.NumberColumn(
                "Safety", width="small", format="%d"
            ),
            "optimized_order_qty": st.column_config.NumberColumn(
                "✏️ Order Qty",
                width="small",
                format="%d",
                help="Editable for months >= current+2",
            ),
            "ending_stock_after_order": st.column_config.NumberColumn(
                "End Stock", width="small", format="%d"
            ),
            "stock_cover_months": st.column_config.NumberColumn(
                "Cover", width="small", format="%.1f"
            ),
            "total_order_cost": st.column_config.NumberColumn(
                "Cost", width="medium", format="$%.2f"
            ),
            "stockout_risk": st.column_config.CheckboxColumn("⚠️", width="small"),
            "is_editable": st.column_config.CheckboxColumn("Edit?", width="small"),
        }

        # Columns to display if they exist
        display_cols = [
            "forecast_month",
            "item_id",
            "item_name",
            "adjusted_demand",
            "opening_stock",
            "in_transit",
            "adjusted_safety_stock",
            "optimized_order_qty",
            "ending_stock_after_order",
            "stock_cover_months",
            "total_order_cost",
            "stockout_risk",
            "is_editable",
        ]
        display_cols = [c for c in display_cols if c in df.columns]

        editable_only = ["optimized_order_qty"]

        edited_df = st.data_editor(
            df[display_cols],
            column_config=column_config,
            disabled=[c for c in display_cols if c not in editable_only],
            hide_index=True,
            use_container_width=True,
            key="plan_editor",
            num_rows="fixed",
        )

        # Detect changes
        changes = []
        for idx in edited_df.index:
            if "is_editable" in edited_df.columns and edited_df.loc[idx, "is_editable"]:
                orig = df.loc[idx, "original_order_qty"]
                new = edited_df.loc[idx, "optimized_order_qty"]
                if orig != new:
                    item_id = edited_df.loc[idx, "item_id"]
                    month = edited_df.loc[idx, "forecast_month"]
                    changes.append(
                        {
                            "item_id": item_id,
                            "item_name": edited_df.loc[idx, "item_name"],
                            "month": month,
                            "original_qty": int(orig),
                            "new_qty": int(new),
                            "difference": int(new - orig),
                            "key": f"{item_id}_{month}",
                        }
                    )

        # Changes summary
        if changes:
            st.divider()
            st.subheader("📊 Manual Adjustments Summary")

            changes_df = pd.DataFrame(changes)
            st.dataframe(
                changes_df[
                    ["month", "item_name", "original_qty", "new_qty", "difference"]
                ],
                use_container_width=True,
                hide_index=True,
            )

            col1, col2, col3 = st.columns([1, 1, 3])

            with col1:
                if st.button("✅ Apply Changes", type="primary"):
                    for change in changes:
                        st.session_state["manual_adjustments"][change["key"]] = change[
                            "new_qty"
                        ]
                    st.success("Changes applied!")
                    st.rerun()

            with col2:
                if st.button("↺ Reset All"):
                    st.session_state["manual_adjustments"] = {}
                    st.rerun()

            with col3:
                adjusted_data = edited_df.to_dict("records")
                json_str = json.dumps(adjusted_data, indent=2, default=str)
                st.download_button(
                    label="💾 Download Adjusted Plan",
                    data=json_str,
                    file_name=f"adjusted_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                )

    else:
        st.subheader("📊 Purchase Plan (View Only)")
        st.dataframe(df, use_container_width=True, hide_index=True)

    # ---------- Export section ----------

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        pf = st.session_state.get("forecaster")
        if pf:
            output = pf.export_to_json()
            json_str = json.dumps(output, indent=2, default=str)
            st.download_button(
                label="📥 Download Full Report (JSON)",
                data=json_str,
                file_name=f"purchase_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
            )

    with col2:
        st.caption("📥 Excel export: to be implemented with in-memory buffer in v1.1")

else:
    # Welcome screen
    st.info(
        "👆 Upload your data files or configure the data directory, "
        "then click **Generate Plan** to start."
    )

    with st.expander("📖 How to Use", expanded=True):
        st.markdown(
            """
        ### Quick Start Guide

        1. **Upload Data Files** or configure the data directory path  
        2. **Set Parameters** in the sidebar (start month, horizon)  
        3. Click **Generate Plan** to create the purchase forecast  
        4. **Enable Edit Mode** to adjust orders for future months  
        5. **Apply Changes** to recalculate the plan  
        6. **Export** your adjusted plan as JSON  

        ### Editing Rules
        - ✅ **Editable**: Months ≥ Current Month + 2  
        - 🔒 **Locked**: Current month and next month  
        - 💡 **Tip**: Changes are highlighted automatically  

        ### Features
        - 📊 Real-time order adjustments  
        - 🔄 Manual adjustment tracking  
        - 💾 Export adjusted plans  
        - 📈 Stock cover analysis  
        """
        )

st.divider()
st.caption("Purchase Plan Forecaster v1.0 | Production-Grade Planning Tool")
