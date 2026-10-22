"""
QD Adaptive Quant Portfolio 20 - Risk-Controlled V3
Multi-asset Gate USDT perpetual strategy.

Preserves the original 20-symbol universe, long/short breakout logic,
BTC hourly regime, EMA, volume confirmation, ATR protection and ranking.

Adds corrected bar-based cooldown, risk sizing, gross/net reservations,
order reconciliation, cancellation timeout, portfolio kill switch,
time protection, signal diagnostics and controlled re-arming.

Statistical alpha is not assumed; it must be independently validated.
"""

PERSIST_RUNTIME_STATE = True

# @param max_positions int 5 Maximum simultaneous positions range=1:5:1
# @param max_entries_day int 7 Maximum daily entries range=1:20:1
# @param risk_per_trade float 0.0025 Equity risk budget range=0.001:0.005:0.0005
# @param max_weight float 0.10 Maximum absolute position weight range=0.02:0.15:0.01
# @param max_gross_exposure float 0.80 Maximum gross exposure/equity range=0.2:1.2:0.1
# @param max_net_exposure float 0.40 Maximum absolute net exposure/equity range=0.1:0.8:0.1
# @param daily_drawdown_limit float 0.02 Daily equity drawdown stop range=0.01:0.05:0.005
# @param portfolio_drawdown_limit float 0.08 Peak-to-trough drawdown stop range=0.03:0.20:0.01
# @param cooldown_bars int 4 Minimum bars before re-entry range=1:32:1
# @param order_timeout_bars int 4 Bars before cancellation request range=1:16:1
# @param max_stop_pct float 0.06 Maximum ATR stop distance range=0.02:0.10:0.01
# @param time_stop_bars int 96 Maximum holding time in 15m bars range=8:672:8
# @param portfolio_rearm bool false Explicitly re-arm a portfolio kill switch values=true,false


def initialize(context):
    g.symbols = [
        "Crypto:BTC/USDT@gate:swap",
        "Crypto:ETH/USDT@gate:swap",
        "Crypto:SOL/USDT@gate:swap",
        "Crypto:BNB/USDT@gate:swap",
        "Crypto:XRP/USDT@gate:swap",
        "Crypto:ADA/USDT@gate:swap",
        "Crypto:AVAX/USDT@gate:swap",
        "Crypto:DOT/USDT@gate:swap",
        "Crypto:LINK/USDT@gate:swap",
        "Crypto:POL/USDT@gate:swap",
        "Crypto:ATOM/USDT@gate:swap",
        "Crypto:NEAR/USDT@gate:swap",
        "Crypto:APT/USDT@gate:swap",
        "Crypto:ARB/USDT@gate:swap",
        "Crypto:OP/USDT@gate:swap",
        "Crypto:LTC/USDT@gate:swap",
        "Crypto:BCH/USDT@gate:swap",
        "Crypto:DOGE/USDT@gate:swap",
        "Crypto:UNI/USDT@gate:swap",
        "Crypto:ETC/USDT@gate:swap",
    ]

    context.set_universe(g.symbols)

    context.subscribe(
        frequency="15m",
        fields=["open", "high", "low", "close", "volume"],
    )

    context.subscribe(
        frequency="1h",
        fields=["open", "high", "low", "close", "volume"],
    )

    context.set_warmup(220)
    context.set_metadata(direction_mode="one_way")
    context.allow_leverage(max_leverage=2)

    g.pending = {}
    g.counted_entry_ids = {}

    # Real 15m bar counter; never use HHMM subtraction.
    g.bar_number = 0
    g.last_processed_bar = ""

    g.last_exit_bar = {}
    g.entry_bar = {}
    g.last_order_bar = {}

    g.entries_today = 0
    g.day_key = ""
    g.day_start_equity = 0.0
    g.daily_killed = False

    g.peak_equity = 0.0
    g.portfolio_killed = False
    g.rearm_was_enabled = False

    g.order_sequence = 0


# ============================================================
# BASIC HELPERS
# ============================================================

def _num(value, default=0.0):
    try:
        value = float(value)
        if value != value: return default
        if value == float("inf") or value == float("-inf"): return default
        return value
    except Exception:
        return default


def _clamp(value, low, high):
    return max(low, min(high, value))


def _day_key(context):
    return str(context.current_dt)[:10]


def _bar_key(context):
    raw = str(context.current_dt)
    return raw[:16]


def _equity(context):
    return _num(context.portfolio.total_value)


def _position_amount(symbol):
    try:
        return _num(get_position(symbol).amount)
    except Exception:
        return 0.0


def _position_value(symbol):
    try:
        pos = get_position(symbol)
        value = abs(_num(pos.market_value))
        if value > 0:
            return value
        amount = abs(_num(pos.amount))
        price = abs(_num(pos.last_price))
        if amount > 0 and price > 0:
            return amount * price
    except Exception:
        pass
    return 0.0


def _sign(value):
    if value > 0: return 1
    if value < 0: return -1
    return 0


def _is_working(status):
    return status in ("unknown", "queued", "deferred", "submitted", "open", "partial")


def _is_terminal(status):
    return status in ("filled", "rejected", "failed", "cancelled", "canceled", "expired")


def _order_status(order_id):
    try:
        result = get_order_status(order_id)
        if not isinstance(result, dict): return "unknown"
        return str(result.get("status", "unknown")).lower()
    except Exception as exc:
        log.warning("Order status unavailable: " + str(exc))
        return "unknown"


# ============================================================
# EXPOSURE AND RESERVATIONS
# ============================================================

def _position_count():
    return sum(1 for symbol in g.symbols if abs(_position_amount(symbol)) > 1e-8)


def _exposure(context):
    equity = _equity(context)
    if equity <= 0: return 999.0, 999.0
    
    gross = 0.0
    net = 0.0
    for symbol in g.symbols:
        amount = _position_amount(symbol)
        value = _position_value(symbol)
        gross += value
        if amount > 0:
            net += value
        elif amount < 0:
            net -= value
    return gross / equity, net / equity


def _pending_reservations():
    gross = 0.0
    net = 0.0
    entries = 0
    for item in g.pending.values():
        if not item.get("entry"): continue
        target = _num(item.get("target"))
        gross += abs(target)
        net += target
        entries += 1
    return gross, net, entries


def _pending_position_count():
    return sum(1 for item in g.pending.values() if item.get("entry"))


# ============================================================
# DAILY AND PORTFOLIO CONTROLS
# ============================================================

def _reset_daily(context):
    today = _day_key(context)
    if today != g.day_key:
        g.day_key = today
        g.day_start_equity = _equity(context)
        g.entries_today = 0
        g.counted_entry_ids = {}
        g.daily_killed = False


def _update_peak(context):
    equity = _equity(context)
    if equity <= 0: return
    if g.peak_equity <= 0: g.peak_equity = equity
    if equity > g.peak_equity: g.peak_equity = equity


def _daily_drawdown(context):
    if g.day_start_equity <= 0: return 0.0
    return max(0.0, (g.day_start_equity - _equity(context)) / g.day_start_equity)


def _portfolio_drawdown(context):
    if g.peak_equity <= 0: return 0.0
    return max(0.0, (g.peak_equity - _equity(context)) / g.peak_equity)


def _process_rearm(context):
    enabled = bool(context.params.get("portfolio_rearm", False))
    if enabled and not g.rearm_was_enabled:
        g.portfolio_killed = False
        g.peak_equity = _equity(context)
        log.warning("Portfolio kill switch explicitly re-armed.")
    g.rearm_was_enabled = enabled


# ============================================================
# ORDER SUBMISSION
# ============================================================

def _submit_target(context, symbol, target, reason, entry=False, stop=0.0, trail=0.0, activation=0.0, time_limit_seconds=0):
    if symbol in g.pending: return False
    bar = _bar_key(context)
    if g.last_order_bar.get(symbol) == bar: return False

    index = g.symbols.index(symbol)
    g.order_sequence += 1
    side = "L" if target > 0 else "S" if target < 0 else "X"
    
    order_id = (
        "qd3-"
        + bar.replace("-", "").replace(":", "").replace(" ", "")
        + "-" + str(index) + "-" + side + "-" + str(g.order_sequence)
    )

    g.pending[symbol] = {
        "id": order_id,
        "target": float(target),
        "entry": bool(entry),
        "reason": reason,
        "bar_number": g.bar_number,
        "age": 0,
        "cancel_requested": False,
        "status": "unknown",
    }

    g.last_order_bar[symbol] = bar

    kwargs = {"reason": reason, "client_order_id": order_id}
    if stop > 0: kwargs["stop_loss_pct"] = float(stop)
    if trail > 0: kwargs["trailing_stop_pct"] = float(trail)
    if activation > 0: kwargs["trailing_activation_pct"] = float(activation)
    
    # FIX: Only pass time_limit_seconds if it's explicitly supported/expected
    if time_limit_seconds > 0:
        kwargs["time_limit_seconds"] = int(time_limit_seconds)

    try:
        order_target_percent(symbol, float(target), **kwargs)
        return True
    except Exception as exc:
        log.warning("Submission uncertain for " + symbol + ": " + str(exc))
        return False


# ============================================================
# EXIT EVENTS AND ORDER RECONCILIATION
# ============================================================

def _consume_exit_events(context):
    for symbol in g.symbols:
        try:
            reason = consume_last_exit_reason(symbol)
            if reason:
                g.last_exit_bar[symbol] = g.bar_number
                log.info("Protection exit recorded for " + symbol + ": " + str(reason))
        except Exception as exc:
            log.warning("Exit reason unavailable for " + symbol + ": " + str(exc))


def _sync_pending(context):
    for symbol in list(g.pending.keys()):
        item = g.pending.get(symbol)
        if not isinstance(item, dict): continue
        order_id = item.get("id")
        if not order_id: continue

        status = _order_status(order_id)
        item["status"] = status
        amount = _position_amount(symbol)
        target = _num(item.get("target"))

        # FIX: Stale unknown orders fallback timeout
        if status == "unknown" and item["age"] > (int(context.params.get("order_timeout_bars", 4)) + 2):
            log.warning(f"Order {order_id} stuck in unknown. Forcing cleanup.")
            g.pending.pop(symbol, None)
            continue

        if status == "filled":
            if item.get("entry"):
                if order_id not in g.counted_entry_ids:
                    g.entries_today += 1
                    g.counted_entry_ids[order_id] = True

            exit_seen = (symbol in g.last_exit_bar and g.last_exit_bar[symbol] >= item.get("bar_number", 0))

            if abs(target) < 1e-8:
                synchronized = abs(amount) < 1e-8
            elif exit_seen and abs(amount) < 1e-8:
                synchronized = True
            elif target > 0:
                synchronized = amount > 0
            else:
                synchronized = amount < 0

            if synchronized:
                if abs(target) < 1e-8:
                    g.last_exit_bar[symbol] = g.bar_number
                elif item.get("entry") and abs(amount) > 1e-8:
                    g.entry_bar[symbol] = g.bar_number
                g.pending.pop(symbol, None)
            continue

        if status in ("rejected", "failed", "cancelled", "canceled", "expired"):
            if abs(amount) <= 1e-8 or target == 0 or _sign(amount) == _sign(target):
                g.pending.pop(symbol, None)
            continue

        if _is_working(status):
            item["age"] = g.bar_number - int(item.get("bar_number", g.bar_number))
            timeout = max(1, min(16, int(context.params.get("order_timeout_bars", 4))))

            if item["age"] >= timeout and not item.get("cancel_requested"):
                try:
                    cancel_order(order_id)
                    item["cancel_requested"] = True
                    log.warning("Cancel requested for " + symbol + "; reservation retained until reconciliation.")
                except Exception as exc:
                    log.warning("Cancel request failed for " + symbol + ": " + str(exc))
            continue


# ============================================================
# EMERGENCY CLOSURE
# ============================================================

def _close_all(context, reason):
    for symbol in g.symbols:
        if symbol in g.pending:
            item = g.pending[symbol]
            if item.get("entry") and not item.get("cancel_requested"):
                order_id = item.get("id")
                if order_id:
                    try:
                        cancel_order(order_id)
                        item["cancel_requested"] = True
                    except Exception as exc:
                        log.warning("Emergency cancellation failed: " + str(exc))
            continue

        amount = _position_amount(symbol)
        if abs(amount) <= 1e-8: continue

        _submit_target(context, symbol, 0.0, reason)


def _risk_kill(context):
    daily_limit = _clamp(_num(context.params.get("daily_drawdown_limit", 0.02)), 0.01, 0.05)
    portfolio_limit = _clamp(_num(context.params.get("portfolio_drawdown_limit", 0.08)), 0.03, 0.20)

    if _daily_drawdown(context) >= daily_limit: g.daily_killed = True
    if _portfolio_drawdown(context) >= portfolio_limit: g.portfolio_killed = True

    if g.portfolio_killed:
        _close_all(context, "portfolio_drawdown_kill")
        return True
    if g.daily_killed:
        _close_all(context, "daily_drawdown_kill")
        return True
    return False


# ============================================================
# BTC HOURLY REGIME
# ============================================================

def _hourly_regime():
    symbol = g.symbols[0]
    try:
        bars = get_history(205, "1h", "close", symbol)
        if bars is None or len(bars) < 200: return 0

        close = bars["close"]
        price = _num(close.iloc[-1])
        fast = _num(close.tail(50).mean())
        slow = _num(close.tail(200).mean())

        if min(price, fast, slow) <= 0: return 0
        if price > slow and fast > slow: return 1
        if price < slow and fast < slow: return -1
        return 0
    except Exception as exc:
        log.warning("BTC regime unavailable: " + str(exc))
        return 0


# ============================================================
# ATR AND SIGNALS
# ============================================================

def _signal_and_risk(context, symbol, regime):
    try:
        bars = get_history(65, "15m", ["open", "high", "low", "close", "volume"], symbol)
        if bars is None or len(bars) < 55: return 0, 0.0, 0.0, 0.0, 0.0

        close = bars["close"]
        high = bars["high"]
        low = bars["low"]
        volume = bars["volume"]

        price = _num(close.iloc[-1])
        if price <= 0: return 0, 0.0, 0.0, 0.0, 0.0

        true_ranges = []
        for i in range(len(bars) - 14, len(bars)):
            h = _num(high.iloc[i])
            l = _num(low.iloc[i])
            prev = _num(close.iloc[i - 1])
            if min(h, l, prev) <= 0: return 0, 0.0, 0.0, 0.0, 0.0
            true_ranges.append(max(h - l, abs(h - prev), abs(l - prev)))

        if len(true_ranges) != 14: return 0, 0.0, 0.0, 0.0, 0.0

        atr = sum(true_ranges) / 14.0
        atr_ratio = atr / price
        if atr_ratio <= 0 or atr_ratio > 0.10: return 0, 0.0, 0.0, 0.0, 0.0

        ema_fast = _num(close.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_slow = _num(close.ewm(span=50, adjust=False).mean().iloc[-1])
        previous_high = _num(high.iloc[-21:-1].max())
        previous_low = _num(low.iloc[-21:-1].min())
        average_volume = _num(volume.iloc[-21:-1].mean())
        current_volume = _num(volume.iloc[-1])

        if min(ema_fast, ema_slow, previous_high, previous_low, average_volume, current_volume) <= 0:
            return 0, 0.0, 0.0, 0.0, 0.0

        volume_ratio = current_volume / average_volume
        direction = 0
        strength = 0.0

        if regime == 1 and price > ema_fast > ema_slow and price > previous_high and volume_ratio >= 1.10:
            direction = 1
            strength = ((price - previous_high) / atr + 0.25 * (ema_fast - ema_slow) / atr + 0.10 * min(volume_ratio, 3.0))
        elif regime == -1 and price < ema_fast < ema_slow and price < previous_low and volume_ratio >= 1.10:
            direction = -1
            strength = ((previous_low - price) / atr + 0.25 * (ema_slow - ema_fast) / atr + 0.10 * min(volume_ratio, 3.0))

        max_stop = _clamp(_num(context.params.get("max_stop_pct", 0.06)), 0.02, 0.10)
        stop = max(0.012, min(max_stop, 2.5 * atr_ratio))
        trail = _clamp(1.8 * atr_ratio, 0.01, 0.05)
        activation = _clamp(1.5 * atr_ratio, 0.01, 0.03)

        return direction, stop, trail, activation, max(0.0, strength)

    except Exception as exc:
        log.warning("Signal error for " + symbol + ": " + str(exc))
        return 0, 0.0, 0.0, 0.0, 0.0


# ============================================================
# POSITION SIZING
# ============================================================

def _target_weight(context, stop):
    equity = _equity(context)
    if equity <= 0 or stop <= 0: return 0.0

    risk_fraction = _clamp(_num(context.params.get("risk_per_trade", 0.0025)), 0.001, 0.005)
    max_weight = _clamp(_num(context.params.get("max_weight", 0.10)), 0.02, 0.15)

    return min(max_weight, risk_fraction / stop)


# ============================================================
# COOLDOWN AND TIME STOP
# ============================================================

def _cooldown_active(context, symbol):
    last_exit = g.last_exit_bar.get(symbol)
    if last_exit is None: return False
    cooldown = max(1, min(32, int(context.params.get("cooldown_bars", 4))))
    return (g.bar_number - int(last_exit) < cooldown)


def _time_stop_bars(context):
    return max(8, min(672, int(context.params.get("time_stop_bars", 96))))


def _time_stop_seconds(context):
    return _time_stop_bars(context) * 15 * 60


# ============================================================
# MAIN HANDLER
# ============================================================

def handle_data(context, data):
    bar = _bar_key(context)
    if bar == g.last_processed_bar: return

    g.last_processed_bar = bar
    g.bar_number += 1

    _reset_daily(context)
    _update_peak(context)
    _consume_exit_events(context)
    _sync_pending(context)
    _process_rearm(context)

    if _risk_kill(context): return

    max_positions = max(1, min(5, int(context.params.get("max_positions", 5))))
    max_entries = max(1, min(20, int(context.params.get("max_entries_day", 7))))
    max_gross = _clamp(_num(context.params.get("max_gross_exposure", 0.80)), 0.2, 1.2)
    max_net = _clamp(_num(context.params.get("max_net_exposure", 0.40)), 0.1, 0.8)

    regime = _hourly_regime()
    candidates = []

    for symbol in g.symbols:
        if symbol in g.pending: continue
        amount = _position_amount(symbol)

        try:
            direction, stop, trail, activation, strength = _signal_and_risk(context, symbol, regime)
        except Exception:
            continue

        if amount > 0:
            entry_bar = g.entry_bar.get(symbol)
            if entry_bar is not None and g.bar_number - entry_bar >= _time_stop_bars(context):
                _submit_target(context, symbol, 0.0, "time_stop_long")
            elif regime == -1 or direction == -1:
                _submit_target(context, symbol, 0.0, "trend_exit_long")
            elif regime == 0:
                _submit_target(context, symbol, 0.0, "neutral_regime_exit_long")
            continue

        if amount < 0:
            entry_bar = g.entry_bar.get(symbol)
            if entry_bar is not None and g.bar_number - entry_bar >= _time_stop_bars(context):
                _submit_target(context, symbol, 0.0, "time_stop_short")
            elif regime == 1 or direction == 1:
                _submit_target(context, symbol, 0.0, "trend_exit_short")
            elif regime == 0:
                _submit_target(context, symbol, 0.0, "neutral_regime_exit_short")
            continue

        if direction == 0 or stop <= 0: continue
        if g.daily_killed or g.portfolio_killed: continue
        if g.entries_today >= max_entries: continue
        if _cooldown_active(context, symbol): continue

        weight = _target_weight(context, stop)
        if weight <= 0: continue

        candidates.append({
            "symbol": symbol, "direction": direction, "stop": stop, "trail": trail,
            "activation": activation, "weight": weight, "strength": strength,
        })

    candidates.sort(key=lambda candidate: candidate["strength"], reverse=True)

    for candidate in candidates:
        pending_gross, pending_net, pending_entries = _pending_reservations()

        if g.entries_today + pending_entries >= max_entries: break
        if _position_count() + _pending_position_count() >= max_positions: break

        symbol = candidate["symbol"]
        if symbol in g.pending: continue

        gross, net = _exposure(context)
        weight = candidate["weight"]
        signed_weight = weight if candidate["direction"] > 0 else -weight

        if gross + pending_gross + weight > max_gross: continue
        if abs(net + pending_net + signed_weight) > max_net: continue

        # FIX: Enforce true effective risk limit
        effective_risk = weight * candidate["stop"]
        risk_budget = _clamp(_num(context.params.get("risk_per_trade", 0.0025)), 0.001, 0.005)
        
        if effective_risk <= 0 or effective_risk > (risk_budget * 1.05): 
            # اگر ریسک از بودجه بیشتر بود، وزن را کاهش بده تا دقیقاً در بودجه جا شود
            weight = risk_budget / candidate["stop"]
            signed_weight = weight if candidate["direction"] > 0 else -weight
            if weight <= 0: continue

        reason = "ranked_atr_breakout_long" if candidate["direction"] > 0 else "ranked_atr_breakout_short"

        _submit_target(
            context, symbol, signed_weight, reason, entry=True,
            stop=candidate["stop"], trail=candidate["trail"], activation=candidate["activation"],
            time_limit_seconds=_time_stop_seconds(context),
        )