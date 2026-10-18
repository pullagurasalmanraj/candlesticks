"""Itemized NSE equity-intraday fees; execution slippage is reported, never charged twice.

Rates are fractions of turnover, not percentage numbers. The fixed default
schedule is the published March 2026 NSE schedule (transaction + IPFT = 307/crore)
and current cash intraday statutory rates. Historical/broker scenarios can
override individual rates explicitly; this is not a historical tariff lookup.
Sources and assumptions are documented in docs/story-trade-outcomes.md.
"""
from dataclasses import asdict, dataclass, fields
import math


COST_MODEL_VERSION = "EQUITY_INTRADAY_COMPONENT_V1"
# Frozen compatibility estimate used ONLY for existing eligibility/calibration.
# It must not become the new fee model or respond to brokerage configuration.
LEGACY_GATE_COST_PCT = 0.00150

COST_BREAKDOWN_FIELDS = (
    "brokerage_buy_cost_pts", "brokerage_sell_cost_pts", "brokerage_cost_pts",
    "stt_sell_cost_pts", "stt_cost_pts",
    "nse_transaction_buy_cost_pts", "nse_transaction_sell_cost_pts",
    "nse_ipft_buy_cost_pts", "nse_ipft_sell_cost_pts", "exchange_cost_pts",
    "sebi_buy_cost_pts", "sebi_sell_cost_pts", "sebi_cost_pts",
    "stamp_buy_cost_pts", "stamp_cost_pts", "gst_taxable_cost_pts", "gst_cost_pts",
    "total_fee_cost_pts", "entry_slippage_pts", "exit_slippage_pts",
    "total_friction_pts", "fee_cost_r", "slippage_r", "total_friction_r",
)
_FEE_COMPONENTS = (
    "brokerage_cost_pts", "stt_cost_pts", "exchange_cost_pts",
    "sebi_cost_pts", "stamp_cost_pts", "gst_cost_pts",
)


def _finite_number(name, value, *, positive=False, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite JSON number")
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise ValueError(f"{name} must be finite") from None
    if not math.isfinite(number) or (number <= 0 if positive else number < 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{name} must not exceed {maximum}")
    return number


@dataclass(frozen=True)
class EquityIntradayCostModel:
    brokerage_rate: float = 0.0003
    brokerage_cap_per_order: float | None = None  # Never infer a Rs20 cap.
    nse_transaction_rate: float = 0.000030699
    nse_ipft_rate: float = 0.000000001
    stt_sell_rate: float = 0.00025
    sebi_turnover_rate: float = 0.000001
    stamp_duty_buy_rate: float = 0.00003
    gst_rate: float = 0.18
    quantity: float | None = None
    order_notional: float | None = None  # Notional of the executed entry order.

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name in ("brokerage_cap_per_order", "quantity", "order_notional"):
                if value is None:
                    continue
                number = _finite_number(field.name, value, positive=field.name != "brokerage_cap_per_order")
            else:
                number = _finite_number(field.name, value, maximum=1)
            object.__setattr__(self, field.name, number)
        if self.quantity is not None and self.order_notional is not None:
            raise ValueError("Specify either cost_model.quantity or cost_model.order_notional, not both")

    @classmethod
    def from_request(cls, options):
        if not isinstance(options, dict):
            raise ValueError("cost_model must be a JSON object")
        unknown = set(options) - {field.name for field in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown cost_model fields: {', '.join(sorted(unknown))}")
        return cls(**options)

    def metadata(self):
        return {
            "cost_model_version": COST_MODEL_VERSION,
            "rates_and_sizing": asdict(self),
            "rate_basis": "fractions_of_turnover; fixed request schedule, not historical tariff lookup",
            "default_schedule": "NSE cash March 2026; override rates for other schedules",
            "gst_base": ["brokerage", "nse_transaction", "nse_ipft", "sebi_turnover"],
            "sizing_assumption": "one entry order and one exit order, same quantity",
            "rounding": "unrounded per-share research estimate; no contract-note rounding",
            "unknown_size_policy": "percentage brokerage; per-order caps cannot be applied",
        }

    def calculate(self, *, entry_price, exit_price, risk_points, is_short,
                  entry_slippage_pts, exit_slippage_pts):
        """Fees on actual execution turnover, returned in rupees per share (points).

        LONG buys entry/sells exit; SHORT sells entry/buys exit. Only brokerage
        depends on size. With known size each leg is one order and the explicit
        per-order cap is divided by quantity to obtain a per-share cost.
        """
        entry = _finite_number("entry_price", float(entry_price), positive=True)
        exit_ = _finite_number("exit_price", float(exit_price), positive=True)
        risk = _finite_number("risk_points", float(risk_points), positive=True)
        entry_slip = _finite_number("entry_slippage_pts", float(entry_slippage_pts))
        exit_slip = _finite_number("exit_slippage_pts", float(exit_slippage_pts))
        quantity = self.quantity
        if self.order_notional is not None:
            quantity = self.order_notional / entry
        if quantity is not None and (not math.isfinite(quantity) or quantity <= 0):
            raise ValueError("Position size cannot be represented for the execution price")
        buy_price, sell_price = (exit_, entry) if is_short else (entry, exit_)
        buy_brokerage = self.brokerage_rate * buy_price
        sell_brokerage = self.brokerage_rate * sell_price
        can_cap = self.brokerage_cap_per_order is not None and quantity is not None
        cap_pts = self.brokerage_cap_per_order / quantity if can_cap else None
        brokerage_buy = min(buy_brokerage, cap_pts) if can_cap else buy_brokerage
        brokerage_sell = min(sell_brokerage, cap_pts) if can_cap else sell_brokerage
        result = {
            "brokerage_buy_cost_pts": brokerage_buy,
            "brokerage_sell_cost_pts": brokerage_sell,
            "brokerage_cost_pts": brokerage_buy + brokerage_sell,
            "stt_sell_cost_pts": sell_price * self.stt_sell_rate,
            "stt_cost_pts": sell_price * self.stt_sell_rate,
            "nse_transaction_buy_cost_pts": buy_price * self.nse_transaction_rate,
            "nse_transaction_sell_cost_pts": sell_price * self.nse_transaction_rate,
            "nse_ipft_buy_cost_pts": buy_price * self.nse_ipft_rate,
            "nse_ipft_sell_cost_pts": sell_price * self.nse_ipft_rate,
            "sebi_buy_cost_pts": buy_price * self.sebi_turnover_rate,
            "sebi_sell_cost_pts": sell_price * self.sebi_turnover_rate,
            "sebi_cost_pts": (buy_price + sell_price) * self.sebi_turnover_rate,
            "stamp_buy_cost_pts": buy_price * self.stamp_duty_buy_rate,
            "stamp_cost_pts": buy_price * self.stamp_duty_buy_rate,
        }
        result["exchange_cost_pts"] = math.fsum(result[key] for key in (
            "nse_transaction_buy_cost_pts", "nse_transaction_sell_cost_pts",
            "nse_ipft_buy_cost_pts", "nse_ipft_sell_cost_pts"))
        # GST is NOT levied on STT, stamp duty, or slippage.
        result["gst_taxable_cost_pts"] = math.fsum(result[key] for key in (
            "brokerage_cost_pts", "exchange_cost_pts", "sebi_cost_pts"))
        result["gst_cost_pts"] = result["gst_taxable_cost_pts"] * self.gst_rate
        result["total_fee_cost_pts"] = math.fsum(result[key] for key in _FEE_COMPONENTS)
        result["entry_slippage_pts"] = entry_slip
        result["exit_slippage_pts"] = exit_slip
        slip = entry_slip + exit_slip
        result["total_friction_pts"] = result["total_fee_cost_pts"] + slip
        result["fee_cost_r"] = result["total_fee_cost_pts"] / risk
        result["slippage_r"] = slip / risk
        result["total_friction_r"] = result["fee_cost_r"] + result["slippage_r"]
        if not all(math.isfinite(value) for value in result.values()):
            raise ValueError("Nonfinite transaction cost breakdown")
        return {
            **result, "cost_model_version": COST_MODEL_VERSION,
            "quantity_used": quantity,
            "brokerage_mode": ("CAPPED_PER_ORDER" if can_cap else
                "PERCENTAGE_FALLBACK_NO_SIZE" if self.brokerage_cap_per_order is not None else "PERCENTAGE"),
            "brokerage_cap_applied_buy": bool(can_cap and buy_brokerage > cap_pts),
            "brokerage_cap_applied_sell": bool(can_cap and sell_brokerage > cap_pts),
        }


def net_r_after_fees(realized_r_gross, costs):
    """Gross already embeds execution slippage; subtract statutory/broker fees once."""
    assert math.isclose(costs["total_fee_cost_pts"], math.fsum(costs[key] for key in _FEE_COMPONENTS),
                        rel_tol=1e-12, abs_tol=1e-12), "Fee component mismatch"
    assert math.isclose(costs["total_friction_r"], costs["fee_cost_r"] + costs["slippage_r"],
                        rel_tol=1e-12, abs_tol=1e-12), "Friction decomposition mismatch"
    return float(realized_r_gross) - costs["fee_cost_r"]
