"""Transparent teaching model, not a calibrated CAE solver."""
import math
from statistics import mean, stdev
from pydantic import BaseModel, Field, model_validator


class HeatingInput(BaseModel):
    initial_c: float = Field(default=25, ge=-20, le=100, allow_inf_nan=False)
    oven_c: float = Field(default=210, ge=181, le=220, allow_inf_nan=False)
    target_c: float = Field(default=180, ge=180, le=219, allow_inf_nan=False)
    tau_s: float = Field(default=180, ge=10, le=3600, allow_inf_nan=False)
    duration_s: float = Field(default=600, ge=1, le=14400, allow_inf_nan=False)

    @model_validator(mode="after")
    def reachable(self):
        if self.target_c >= self.oven_c:
            raise ValueError("目标温度必须低于炉温")
        return self


def simulate_heating(params: dict | None = None):
    p = HeatingInput(**(params or {}))
    # A first-order lumped model, dT/dt = (T_oven - T)/tau.
    # Compare independent RK4 integration with the analytical solution.
    n = max(120, math.ceil(p.duration_s / min(5, p.tau_s / 20)))
    dt = p.duration_s / n
    temperature, curve, max_error = p.initial_c, [], 0.0
    for i in range(n + 1):
        t = i * dt
        exact = p.oven_c - (p.oven_c - p.initial_c) * math.exp(-t / p.tau_s)
        max_error = max(max_error, abs(exact - temperature))
        if i % max(1, n // 60) == 0 or i == n:
            curve.append({"time_s": round(t, 3), "temperature_c": round(temperature, 5), "analytical_c": round(exact, 5)})
        k1 = (p.oven_c - temperature) / p.tau_s
        k2 = (p.oven_c - (temperature + dt * k1 / 2)) / p.tau_s
        k3 = (p.oven_c - (temperature + dt * k2 / 2)) / p.tau_s
        k4 = (p.oven_c - (temperature + dt * k3)) / p.tau_s
        if i < n:
            temperature += dt * (k1 + 2*k2 + 2*k3 + k4) / 6
    min_time = -p.tau_s * math.log((p.oven_c - p.target_c) / (p.oven_c - p.initial_c))
    # Independent bisection verifies the inverse calculation.
    lo, hi = 0.0, max(1.0, min_time * 2)
    for _ in range(60):
        mid = (lo + hi) / 2
        if p.oven_c - (p.oven_c - p.initial_c)*math.exp(-mid/p.tau_s) < p.target_c:
            lo = mid
        else:
            hi = mid
    return {"model": "first_order_lumped_heating_v1", "formula": "dT/dt=(T_oven-T)/tau", "parameters": p.model_dump(),
        "curve": curve, "final_c": round(temperature, 5), "target_reached": temperature >= p.target_c,
        "minimum_time_s": round(min_time, 3), "inverse_residual_s": abs(min_time - (lo+hi)/2),
        "max_error_c": max_error, "verified": max_error < 0.001 and abs(min_time-(lo+hi)/2) < 0.001,
        "assumptions": "假设温度均匀、炉温恒定、时间常数不变；忽略传热空间分布、相变和固化动力学。tau 为自设参数，未经真实设备标定。",
        "recommendation": f"在假设炉温 {p.oven_c:g} ℃ 和 tau={p.tau_s:g} s 下，达到 {p.target_c:g} ℃ 的理论最短时间约 {min_time:.1f} s；须用实验标定后再验证。"}


def process_statistics(readings, specs):
    spec = next((s for s in specs if s.get("doc_id") == "SOP-003" and s.get("status") == "active"), {})
    results = []
    for name, lim in spec.get("limits", {}).items():
        values = []
        for row in readings:
            try:
                v = float(row.get(name, ""))
                if math.isfinite(v):
                    values.append(v)
            except (ValueError, TypeError):
                pass
        if values:
            sd = stdev(values) if len(values) > 1 else None
            results.append({"parameter": name, "count": len(values), "mean": round(mean(values), 6),
                "min": min(values), "max": max(values), "sample_std": round(sd, 6) if sd is not None else None,
                "unit": lim["unit"], "capability_index": None})
    return {"parameters": results, "note": "样本量小，仅展示描述统计；未验证过程稳定性与分布，不能据此报告 Cp/Cpk 或推断因果。"}
