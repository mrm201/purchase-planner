# dataio/exports.py
import pandas as pd

def export_plan_excel(df: pd.DataFrame, filename: str = "purchase_plan.xlsx") -> str:
    """
    Save a DataFrame to Excel (single sheet 'Plan'). Return the filename.
    """
    out = df.copy()
    with pd.ExcelWriter(filename, engine="openpyxl") as w:
        out.to_excel(w, index=False, sheet_name="Plan")
    return filename