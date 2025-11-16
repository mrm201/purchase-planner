# dataio/parsers.py
from typing import List, Dict, Optional
import pandas as pd
import math

# ---------- File reader ----------

def read_any_table(file) -> Optional[pd.DataFrame]:
    """
    Read a Streamlit-uploaded file as CSV or Excel and return a DataFrame.
    Returns None if file is None.
    """
    if file is None:
        return None
    name = (getattr(file, "name", "") or "").lower()
    # Try by extension first
    if name.endswith(".csv"):
        return pd.read_csv(file)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(file)

    # Unknown extension: try CSV then Excel
    try:
        return pd.read_csv(file)
    except Exception:
        try:
            file.seek(0)
        except Exception:
            pass
        return pd.read_excel(file)

# ---------- Validation ----------

def validate_required_columns(df: pd.DataFrame, required: List[str], name: str) -> List[str]:
    errs: List[str] = []
    if df is None:
        errs.append(f"{name}: file not provided.")
        return errs
    missing = [c for c in required if c not in df.columns]
    if missing:
        errs.append(f"{name}: missing columns {missing}")
    return errs

# ---------- Normalizers (NaN-safe) ----------

def _nan_to_none_series(s: pd.Series) -> pd.Series:
    """Convert NaN in a Series to None (for JSON-serializable dicts)."""
    return s.where(pd.notna(s), None)

def df_to_sales_history(df: pd.DataFrame) -> List[Dict]:
    # month,item_id,item_name,actual_sales_qty,stock_available,lost_sales_qty,unit_price,category
    d = df.copy()
    # make sure booleans/ints are sane
    if "stock_available" in d.columns:
        d["stock_available"] = d["stock_available"].astype(str).str.upper().isin(["1","TRUE","T","YES","Y"])
    for col in ["actual_sales_qty","lost_sales_qty"]:
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0).astype(int)
    if "unit_price" in d.columns:
        d["unit_price"] = pd.to_numeric(d["unit_price"], errors="coerce").fillna(0.0)
    return d.to_dict(orient="records")

def df_to_item_params(df: pd.DataFrame) -> List[Dict]:
    # item_id,item_name,supplier,order_lead_time_days,minimum_order_qty,order_multiple,
    # unit_cost,shelf_life_days,safety_stock_days,max_stock_cover_months
    d = df.copy()
    num_cols = [
        "order_lead_time_days","minimum_order_qty","order_multiple",
        "unit_cost","shelf_life_days","safety_stock_days","max_stock_cover_months"
    ]
    for col in num_cols:
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce")
            # Leave NaN as None (so engine can ignore)
            d[col] = _nan_to_none_series(d[col])
    return d.to_dict(orient="records")

def df_to_inventory(df: pd.DataFrame) -> List[Dict]:
    # item_id,current_stock_qty,in_transit_qty,in_transit_arrival_date,committed_qty
    d = df.copy()
    for col in ["current_stock_qty","in_transit_qty","committed_qty"]:
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0).astype(int)
    if "in_transit_arrival_date" in d.columns:
        d["in_transit_arrival_date"] = _nan_to_none_series(d["in_transit_arrival_date"])
    return d.to_dict(orient="records")

def df_to_fcst_map(df: pd.DataFrame) -> Dict[str, List[Dict]]:
    # item_id,month,forecasted_sales_qty,forecast_source,confidence_score
    d = df.copy()
    if "forecasted_sales_qty" in d.columns:
        d["forecasted_sales_qty"] = pd.to_numeric(d["forecasted_sales_qty"], errors="coerce").fillna(0).astype(int)
    if "confidence_score" in d.columns:
        d["confidence_score"] = pd.to_numeric(d["confidence_score"], errors="coerce").fillna(0.7)

    out: Dict[str, List[Dict]] = {}
    for row in d.to_dict(orient="records"):
        item_id = row["item_id"]
        out.setdefault(item_id, []).append({
            "month": row["month"],
            "forecasted_sales_qty": int(row["forecasted_sales_qty"]),
            "forecast_source": row.get("forecast_source", ""),
            "confidence_score": float(row.get("confidence_score", 0.7)),
        })
    return out