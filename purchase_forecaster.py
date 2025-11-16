# purchase_forecaster.py
import json, math
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict, field
from dateutil.relativedelta import relativedelta
import pandas as pd

_Z_BY_SERVICE = {0.90: 1.282, 0.95: 1.645, 0.98: 2.054, 0.99: 2.326}

@dataclass
class HistoricalSalesData:
    month: str
    item_id: str
    item_name: str
    actual_sales_qty: int
    stock_available: bool
    lost_sales_qty: int
    unit_price: float
    category: str

@dataclass
class MonthlySalesForecast:
    month: str
    forecasted_sales_qty: int
    forecast_source: str
    confidence_score: float

@dataclass
class ItemParameters:
    item_id: str
    item_name: str
    supplier: str
    order_lead_time_days: int
    minimum_order_qty: int
    order_multiple: int
    unit_cost: float
    shelf_life_days: Optional[int]
    safety_stock_days: int
    max_stock_cover_months: float = 2.0

@dataclass
class CurrentInventory:
    item_id: str
    current_stock_qty: int
    in_transit_qty: int
    in_transit_arrival_date: Optional[str]
    committed_qty: int

@dataclass
class PurchaseForecast:
    forecast_month: str
    item_id: str
    item_name: str
    adjusted_demand: int
    optimized_order_qty: int
    effective_unit_cost: float
    total_order_cost: float
    order_by_date: str
    expected_delivery_date: str
    supplier_name: str
    notes: List[str] = field(default_factory=list)

class PurchasePlanForecaster:
    """
    Periodic-review (R,Q) style. Order-up-to S = mean_d*(L+R) + Z*std_d*sqrt(L+R).
    Then cap by stock cover & shelf-life, and round to MOQ/multiples.
    """
    def __init__(self):
        self.sales_history: List[HistoricalSalesData] = []
        self.item_params: Dict[str, ItemParameters] = {}
        self.current_inventory: Dict[str, CurrentInventory] = {}
        self.sales_forecasts_n12: Dict[str, List[MonthlySalesForecast]] = {}
        self.forecasts: List[PurchaseForecast] = []

    def load_sales_history(self, data): 
        self.sales_history = [HistoricalSalesData(**x) for x in data]
    def load_item_parameters(self, data):
        for d in data: self.item_params[d["item_id"]] = ItemParameters(**d)
    def load_current_inventory(self, data):
        for d in data: self.current_inventory[d["item_id"]] = CurrentInventory(**d)
    def load_sales_forecasts_n12(self, data):
        for k, v in data.items(): self.sales_forecasts_n12[k] = [MonthlySalesForecast(**f) for f in v]

    def _hist_daily_stats(self, item_id: str) -> (float, float):
        rows = [r for r in self.sales_history if r.item_id == item_id]
        if not rows: return (1.0, 0.3)
        rows = sorted(rows, key=lambda r: r.month)[-12:]
        monthly = [max(0, r.actual_sales_qty) for r in rows]
        mean_m = sum(monthly)/len(monthly) if monthly else 1.0
        if len(monthly) > 1:
            var = sum((x-mean_m)**2 for x in monthly)/(len(monthly)-1)
            std_m = math.sqrt(var)
        else:
            std_m = 0.25*mean_m
        mean_d = max(mean_m/30.0, 0.1)
        std_d  = max(std_m/30.0, 0.05*mean_d)
        return mean_d, std_d

    def _pick_monthly_forecast(self, item_id: str, month: str) -> Optional[MonthlySalesForecast]:
        pool = self.sales_forecasts_n12.get(item_id, [])
        if not pool: return None
        exact = [f for f in pool if f.month == month]
        return max(exact or pool, key=lambda f: f.confidence_score)

    def _cap_by_cover_and_shelf(self, qty: int, p: ItemParameters, monthly_demand: float) -> int:
        caps = []
        if p.max_stock_cover_months and monthly_demand > 0:
            caps.append(int(p.max_stock_cover_months * monthly_demand))
        if p.shelf_life_days and monthly_demand > 0:
            caps.append(int((p.shelf_life_days/30.0) * monthly_demand))
        return max(0, min(qty, max(caps) if caps else qty))

    def _round_to_moq_multiple(self, qty: int, moq: int, multiple: int) -> int:
        if qty <= 0: return 0
        multiple = max(1, multiple or 1)
        moq = max(0, moq or 0)
        rounded = ((qty + multiple - 1)//multiple)*multiple
        return max(rounded, moq)

    def generate_purchase_plan(self, start_month: str, num_months: int = 6,
                               service_level: float = 0.95, review_period_days: int = 30,
                               include_in_transit: bool = True):
        self.forecasts = []
        Z = _Z_BY_SERVICE.get(service_level, 1.645)
        R = review_period_days

        for item_id, p in self.item_params.items():
            inv = self.current_inventory.get(item_id)
            on_hand = inv.current_stock_qty if inv else 0
            in_transit = inv.in_transit_qty if (inv and include_in_transit) else 0
            available = max(0, on_hand + in_transit)
            mean_d, std_d = self._hist_daily_stats(item_id)

            for i in range(num_months):
                month = (datetime.strptime(start_month, "%Y-%m") + relativedelta(months=i)).strftime("%Y-%m")
                f = self._pick_monthly_forecast(item_id, month)
                month_fcst = f.forecasted_sales_qty if f else mean_d*30.0
                monthly_expected = max(month_fcst, mean_d*20.0)

                L = max(0, p.order_lead_time_days or 0)
                horizon = max(1, L + R)
                S = mean_d*horizon + Z*std_d*math.sqrt(horizon)
                raw = max(0, int(math.ceil(S - available)))
                capped = self._cap_by_cover_and_shelf(raw, p, monthly_expected)
                rounded = self._round_to_moq_multiple(capped, p.minimum_order_qty, p.order_multiple)
                total = rounded * p.unit_cost

                self.forecasts.append(PurchaseForecast(
                    forecast_month=month, item_id=item_id, item_name=p.item_name,
                    adjusted_demand=int(round(monthly_expected)),
                    optimized_order_qty=rounded, effective_unit_cost=p.unit_cost,
                    total_order_cost=total, order_by_date=f"{month}-01", expected_delivery_date=f"{month}-28",
                    supplier_name=p.supplier,
                    notes=[f"Z={Z}", f"L={L}d", f"R={R}d"]
                ))
        return self.forecasts

    def export_to_json(self, filename: str = None):
        out = {"generated": datetime.now().isoformat(), "forecasts": [asdict(f) for f in self.forecasts]}
        if filename:
            with open(filename, "w") as fh: json.dump(out, fh, indent=2)
        return out

    def export_to_excel(self, filename: str = "purchase_plan.xlsx"):
        if not self.forecasts: return filename
        df = pd.DataFrame([asdict(f) for f in self.forecasts])
        df["notes"] = df["notes"].apply(lambda x: "; ".join(x))
        with pd.ExcelWriter(filename, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="Forecasts")
        return filename
