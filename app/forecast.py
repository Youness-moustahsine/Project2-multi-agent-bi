"""Prévision de séries mensuelles en Python pur : tendance linéaire + saisonnalité multiplicative.
Inclut un backtest (MAPE) pour que l'agent puisse annoncer la fiabilité de sa prévision."""
import math


def _linfit(ys):
    n = len(ys)
    xs = range(n)
    mx, my = (n - 1) / 2, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    return slope, my - slope * mx


def _fit_predict(values, horizon, season, period=12):
    n = len(values)
    idx = [1.0] * period
    series = list(values)
    if season and n >= 2 * period:
        slope, inter = _linfit(values)
        ratios = [[] for _ in range(period)]
        for i, v in enumerate(values):
            trend = inter + slope * i
            if trend > 0:
                ratios[i % period].append(v / trend)
        idx = [sum(r) / len(r) if r else 1.0 for r in ratios]
        mean = sum(idx) / period
        idx = [x / mean for x in idx]
        series = [v / idx[i % period] for i, v in enumerate(values)]
    else:
        season = False
    slope, inter = _linfit(series)
    fitted = [(inter + slope * i) * idx[i % period] for i in range(n)]
    future = [(inter + slope * (n + h)) * idx[(n + h) % period] for h in range(horizon)]
    return fitted, future, slope, season


def forecast(values, horizon=6, period=12):
    values = [float(v) for v in values]
    n = len(values)
    if n < 6:
        raise ValueError("At least 6 data points are needed to forecast.")
    horizon = max(1, min(int(horizon), 12))
    fitted, future, slope, season = _fit_predict(values, horizon, True, period)
    resid = [v - f for v, f in zip(values, fitted)]
    sigma = math.sqrt(sum(r * r for r in resid) / max(1, n - 2))
    nonneg = all(v >= 0 for v in values)
    points = []
    for i, v in enumerate(future, 1):
        low, high = v - 1.28 * sigma, v + 1.28 * sigma   # intervalle ~80 %
        points.append({"step": i, "value": round(v, 2),
                       "low": round(max(0, low) if nonneg else low, 2), "high": round(high, 2)})
    mape = None
    if n >= 9:  # backtest : on cache les 3 derniers points et on les prédit
        _, pred, _, _ = _fit_predict(values[:-3], 3, True, period)
        errs = [abs(a - p) / abs(a) for a, p in zip(values[-3:], pred) if a]
        mape = round(100 * sum(errs) / len(errs), 1) if errs else None
    mean = sum(values) / n
    return {"forecast": points, "mape": mape,
            "method": "tendance linéaire + saisonnalité" if season else "tendance linéaire",
            "trend_pct_per_period": round(100 * slope / mean, 2) if mean else None}
