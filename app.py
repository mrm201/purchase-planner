# app.py — Purchase Planning v0.2+ (Streamlit)

import sys, os, json
import pandas as pd
import streamlit as st

# Ensure local modules are importable when run from anywhere
sys.path.append(os.path.dirname(__file__))

from purchase_forecaster import PurchasePlanForecaster
from dataio.parsers import (
    read_any_table, df_to_sales_history, df_to_item_params,
    df_to_inventory, df_to_fcst_map, validate_required_columns
)
from dataio.exports import export_plan_excel
from storage.db import init_db, SessionLocal
from storage.models import User, Run, RunLine

st.set_page_config(page_title="Purchase Planning v0.2+", layout="wide")
st.title("🧮 Purchase Planning – v0.2+ (Streamlit)")

# Init DB (SQLite)
init_db()

# Optional samples path
SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "samples")
def _read_csv(path):
    return pd.read_csv(path) if os.path.exists(path) else None

tab_plan, tab_dashboard, tab_history = st.tabs(["📈 Planner", "📊 Dashboard", "🕘 Run History"])
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

# --------------------------- PLANNER ---------------------------
with tab_plan:
    with st.sidebar:
        st.header("Demo Helpers")
        load_samples = st.toggle("Load sample data", value=True)
        st.caption("When ON, /samples CSVs will be used if you don't upload files.")

        st.divider()
        st.header("Upload Data")
        f_sales = st.file_uploader("Sales History (CSV/Excel)", type=["csv", "xlsx"])
        f_items = st.file_uploader("Item Parameters (CSV/Excel)", type=["csv", "xlsx"])
        f_inv   = st.file_uploader("Current Inventory (CSV/Excel)", type=["csv", "xlsx"])
        f_fcst  = st.file_uploader("Sales Forecasts (CSV/Excel)", type=["csv", "xlsx"])

        st.divider()
        st.header("Download Templates")
        st.download_button("Template: Sales History",
            data="month,item_id,item_name,actual_sales_qty,stock_available,lost_sales_qty,unit_price,category\n",
            file_name="sales_history_template.csv", mime="text/csv")
        st.download_button("Template: Item Parameters",
            data="item_id,item_name,supplier,order_lead_time_days,minimum_order_qty,order_multiple,unit_cost,shelf_life_days,safety_stock_days,max_stock_cover_months\n",
            file_name="item_parameters_template.csv", mime="text/csv")
        st.download_button("Template: Current Inventory",
            data="item_id,current_stock_qty,in_transit_qty,in_transit_arrival_date,committed_qty\n",
            file_name="current_inventory_template.csv", mime="text/csv")
        st.download_button("Template: Sales Forecasts (N12)",
            data="item_id,month,forecasted_sales_qty,forecast_source,confidence_score\n",
            file_name="sales_forecasts_n12_template.csv", mime="text/csv")

        st.divider()
        st.header("Planning Parameters")
        start_month = st.text_input("Start month (YYYY-MM)", "2025-12")
        months = st.number_input("Months to plan", min_value=1, max_value=24, value=6, step=1)
        service_level = st.selectbox("Target Service Level", [0.90, 0.95, 0.98, 0.99], index=1)
        review_days = st.number_input("Review period (days)", min_value=7, max_value=60, value=30, step=1)

        st.divider()
        run_btn = st.button("Generate Plan")

    # Read uploads
    sales_df = read_any_table(f_sales) if f_sales else None
    items_df = read_any_table(f_items) if f_items else None
    inv_df   = read_any_table(f_inv)   if f_inv   else None
    fcst_df  = read_any_table(f_fcst)  if f_fcst  else None

    # Load sample CSVs if toggle on
    if load_samples:
        if sales_df is None: sales_df = _read_csv(os.path.join(SAMPLES_DIR, "sales_history.csv"))
        if items_df is None: items_df = _read_csv(os.path.join(SAMPLES_DIR, "item_parameters.csv"))
        if inv_df   is None: inv_df   = _read_csv(os.path.join(SAMPLES_DIR, "current_inventory.csv"))
        if fcst_df  is None: fcst_df  = _read_csv(os.path.join(SAMPLES_DIR, "sales_forecasts_n12.csv"))

    def _validate_all_inputs():
        if any(x is None for x in [sales_df, items_df, inv_df, fcst_df]):
            st.error("Please provide **all four** datasets (or turn ON 'Load sample data').")
            st.stop()
        errs = []
        errs += validate_required_columns(
            sales_df,
            ["month","item_id","item_name","actual_sales_qty","stock_available","lost_sales_qty","unit_price","category"],
            "Sales History",
        )
        errs += validate_required_columns(
            items_df,
            ["item_id","item_name","supplier","order_lead_time_days","minimum_order_qty","order_multiple",
             "unit_cost","shelf_life_days","safety_stock_days","max_stock_cover_months"],
            "Item Parameters",
        )
        errs += validate_required_columns(
            inv_df,
            ["item_id","current_stock_qty","in_transit_qty","in_transit_arrival_date","committed_qty"],
            "Current Inventory",
        )
        errs += validate_required_columns(
            fcst_df,
            ["item_id","month","forecasted_sales_qty","forecast_source","confidence_score"],
            "Sales Forecasts",
        )
        if errs:
            st.error("Column validation errors:\n\n" + "\n".join(f"- {e}" for e in errs))
            st.stop()

    if run_btn:
        _validate_all_inputs()

        # Normalize → engine
        pf = PurchasePlanForecaster()
        pf.load_sales_history(df_to_sales_history(sales_df))
        pf.load_item_parameters(df_to_item_params(items_df))
        pf.load_current_inventory(df_to_inventory(inv_df))
        pf.load_sales_forecasts_n12(df_to_fcst_map(fcst_df))

        # Run engine
        pf.generate_purchase_plan(
            start_month=start_month,
            num_months=int(months),
            service_level=float(service_level),
            review_period_days=int(review_days),
        )
        result = pf.export_to_json()
        plan_df = pd.DataFrame(result["forecasts"])
        plan_df["notes"] = plan_df["notes"].apply(lambda x: "; ".join(x) if isinstance(x, list) else (x or ""))

        # KPIs
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("SKUs planned", f"{plan_df['item_id'].nunique():,}")
        c2.metric("Total lines", f"{len(plan_df):,}")
        c3.metric("Total order qty", f"{int(plan_df['optimized_order_qty'].sum()):,}")
        c4.metric("Total order cost", f"${plan_df['total_order_cost'].sum():,.2f}")

        # Editor
        st.subheader("Edit Your Plan")
        editable_cols = ["optimized_order_qty", "notes"]
        edited_df = st.data_editor(
            plan_df,
            use_container_width=True,
            column_config={
                "optimized_order_qty": st.column_config.NumberColumn("Order Qty", step=1, min_value=0),
                "notes": st.column_config.TextColumn("Notes"),
            },
            disabled=[c for c in plan_df.columns if c not in editable_cols],
            key="plan_editor_v03",
        )

        # Charts
        st.subheader("Charts")
        sku_options = sorted(edited_df["item_id"].unique())
        if sku_options:
            sku = st.selectbox("Select SKU", sku_options)
            hist = sales_df[sales_df["item_id"] == sku].sort_values("month") if sales_df is not None else pd.DataFrame()
            fcst = fcst_df[fcst_df["item_id"] == sku].sort_values("month") if fcst_df is not None else pd.DataFrame()
            planned = edited_df[edited_df["item_id"] == sku][["forecast_month","optimized_order_qty"]]

            st.caption("Actuals vs Forecast")
            st.line_chart(
                pd.DataFrame({
                    "actuals": hist.set_index("month")["actual_sales_qty"] if not hist.empty else pd.Series(dtype=float),
                    "forecast": fcst.set_index("month")["forecasted_sales_qty"] if not fcst.empty else pd.Series(dtype=float),
                })
            )
            st.caption("Planned Order Qty by Forecast Month")
            if not planned.empty:
                st.bar_chart(planned.set_index("forecast_month"))
            else:
                st.info("No planned rows for the selected SKU in this horizon.")

        # Exports
        st.subheader("Export")
        st.download_button(
            "Download JSON",
            data=json.dumps({"generated": result["generated"], "forecasts": edited_df.to_dict(orient="records")}, indent=2),
            file_name="purchase_plan.json",
            mime="application/json",
        )
        excel_path = export_plan_excel(edited_df, filename="purchase_plan.xlsx")
        with open(excel_path, "rb") as fh:
            st.download_button(
                "Download Excel",
                data=fh.read(),
                file_name="purchase_plan.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        # Save run
        st.subheader("Save Run")
        if st.button("Save to Database"):
            sess = SessionLocal()
            user = sess.query(User).filter_by(email="demo@user").first()
            if not user:
                user = User(email="demo@user", name="Demo User")
                sess.add(user); sess.commit()
            run = Run(
                user_id=user.id,
                params_json=json.dumps({"start_month": start_month, "months": int(months),
                                        "service_level": float(service_level), "review_days": int(review_days)}),
                source_files=json.dumps([
                    getattr(f_sales, "name", "sales_history.csv" if sales_df is not None else ""),
                    getattr(f_items, "name", "item_parameters.csv" if items_df is not None else ""),
                    getattr(f_inv, "name", "current_inventory.csv" if inv_df is not None else ""),
                    getattr(f_fcst, "name", "sales_forecasts_n12.csv" if fcst_df is not None else ""),
                ]),
            )
            sess.add(run); sess.commit()
            for _, r in edited_df.iterrows():
                line = RunLine(
                    run_id=run.id,
                    sku=str(r["item_id"]),
                    item_name=str(r["item_name"]),
                    supplier=str(r["supplier_name"]),
                    demand=float(r["adjusted_demand"]),
                    order_qty=float(r["optimized_order_qty"]),
                    unit_cost=float(r["effective_unit_cost"]),
                    total_cost=float(r["total_order_cost"]),
                    notes=str(r.get("notes","")),
                    metadata_json="{}",
                )
                sess.add(line)
            sess.commit()
            st.success(f"Run saved (id={run.id}).")

    else:
        st.info("Upload data (or enable *Load sample data*), set parameters, then click **Generate Plan**.")

# --------------------------- HISTORY ---------------------------
with tab_history:
    st.subheader("Saved Runs")
    sess = SessionLocal()
    runs = sess.query(Run).order_by(Run.started_at.desc()).all()

    if not runs:
        st.info("No runs saved yet.")
    else:
        run_map = {f"#{r.id}  •  {r.started_at.strftime('%Y-%m-%d %H:%M:%S')}": r.id for r in runs}
        sel = st.selectbox("View run", list(run_map.keys()))
        run_id = run_map[sel]
        lines = sess.query(RunLine).filter_by(run_id=run_id).all()
        df = pd.DataFrame([{
            "item_id": ln.sku, "item_name": ln.item_name, "supplier": ln.supplier,
            "demand": ln.demand, "order_qty": ln.order_qty, "unit_cost": ln.unit_cost,
            "total_cost": ln.total_cost, "notes": ln.notes
        } for ln in lines])

        if df.empty:
            st.info("This run has no lines.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("SKUs", f"{df['item_id'].nunique():,}")
            c2.metric("Lines", f"{len(df):,}")
            c3.metric("Total $", f"${df['total_cost'].sum():,.2f}")
            st.dataframe(df, use_container_width=True)

        st.divider()
        st.subheader("Compare Runs (Diff)")
        left, right = st.columns(2)
        sel_a = left.selectbox("Run A", list(run_map.keys()), key="cmp_a")
        sel_b = right.selectbox("Run B", list(run_map.keys()), key="cmp_b")
        if sel_a and sel_b and sel_a != sel_b:
            ra = run_map[sel_a]; rb = run_map[sel_b]
            la = pd.DataFrame([{
                "item_id": ln.sku, "order_qty_a": ln.order_qty, "total_cost_a": ln.total_cost
            } for ln in sess.query(RunLine).filter_by(run_id=ra).all()])
            lb = pd.DataFrame([{
                "item_id": ln.sku, "order_qty_b": ln.order_qty, "total_cost_b": ln.total_cost
            } for ln in sess.query(RunLine).filter_by(run_id=rb).all()])

            diff = pd.merge(la, lb, on="item_id", how="outer").fillna(0.0)
            diff["Δ_qty"] = diff["order_qty_b"] - diff["order_qty_a"]
            diff["Δ_cost"] = diff["total_cost_b"] - diff["total_cost_a"]
            st.dataframe(diff.sort_values("Δ_cost", ascending=False), use_container_width=True)

            m1, m2 = st.columns(2)
            m1.metric("Δ Total Qty (B−A)", f"{int(diff['Δ_qty'].sum()):,}")
            m2.metric("Δ Total Cost (B−A)", f"${diff['Δ_cost'].sum():,.2f}")
        else:
            st.caption("Pick two different runs to see the diffs.")