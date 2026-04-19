"""
fib8 forward monitoring harness.

Scans the last N bars of current daily data to find active setups,
track their state machine, and generate a paper-trade ledger.

This replaces further backtest optimization: instead of adding more IS data,
we monitor real setups in real time and let OOS2 accumulate naturally.

ForwardMonitor   -- main class
MonitoredSetup   -- per-setup state tracking dataclass
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from typing import Optional

# fib7 infrastructure (setup detection + execution)
from research.fib7.regime import check_all_gates


# ---------------------------------------------------------------------------
# MonitoredSetup state machine
# ---------------------------------------------------------------------------

SETUP_STATES = frozenset(
    [
        "ARMED",  # Setup detected; waiting for trigger
        "CONFIRMED",  # Trigger fired; entry placed (awaiting fill)
        "IN_TRADE",  # Trade is active
        "CLOSED",  # Trade closed (target or stop)
        "INVALIDATED",  # Setup cancelled (stop hit before entry or criteria failed)
        "EXPIRED",  # Max bars elapsed without trigger
    ]
)


@dataclass
class MonitoredSetup:
    """Full state record for one monitored setup."""

    setup_id: str  # ticker_YYYYMMDD_direction
    ticker: str
    detection_date: str  # YYYYMMDD
    direction: str  # "bullish" or "bearish"
    regime_at_detection: str  # vol_quiet / vol_active / neutral
    zone_low: float
    zone_high: float
    fib_382: float
    fib_618: float
    stop_price: float
    target_price: float
    state: str = "ARMED"
    entry_date: Optional[str] = None
    entry_price: Optional[float] = None
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    outcome_r: Optional[float] = None
    bars_in_state: int = 0
    notes: str = ""
    config_name: str = ""


# ---------------------------------------------------------------------------
# ForwardMonitor
# ---------------------------------------------------------------------------


class ForwardMonitor:
    """
    Paper-trade harness: scan daily bars for active setups and track state.

    Usage:
        monitor = ForwardMonitor(config, ticker, lookback_bars=60)
        setups = monitor.scan(daily_bars, spy_daily)
        monitor.print_ledger(setups)
        monitor.save_ledger(setups, "paper_ledger.json")
    """

    def __init__(self, config, ticker: str, lookback_bars: int = 60):
        self.config = config
        self.ticker = ticker
        self.lookback_bars = lookback_bars

    def scan(self, daily_bars: dict, spy_daily: dict) -> list[MonitoredSetup]:
        """
        Scan the last lookback_bars of daily_bars for qualified setups.

        Parameters
        ----------
        daily_bars : {"dates": [...], "opens": [...], "highs": [...],
                      "lows": [...], "closes": [...], "volumes": [...],
                      "atr": [...]}
        spy_daily  : same structure for SPY (regime/benchmark reference)

        Returns
        -------
        list[MonitoredSetup] -- one per detected setup, with current state
        """
        try:
            from research.fib7.backtester import (
                find_qualified_legs,
                find_entry,
                check_stop_target,
            )
        except ImportError:
            # Fallback: import from fib6 if fib7 backtester not available
            from research.fib6.backtester import find_qualified_legs, find_entry

        dates = daily_bars.get("dates", [])
        closes = daily_bars.get("closes", [])
        opens = daily_bars.get("opens", [])
        highs = daily_bars.get("highs", [])
        lows = daily_bars.get("lows", [])
        volumes = daily_bars.get("volumes", [])
        atr = daily_bars.get("atr", [])

        if len(dates) < 20:
            return []

        # Focus on lookback window
        lookback = min(self.lookback_bars, len(dates))
        start_bar = len(dates) - lookback

        # Find qualified legs in lookback window
        try:
            legs = find_qualified_legs(daily_bars, self.config, spy_daily=spy_daily)
        except TypeError:
            # Some implementations don't take spy_daily
            legs = find_qualified_legs(daily_bars, self.config)

        setups = []
        for leg in legs:
            # Only process legs detected in lookback window
            detect_bar = getattr(leg, "discovery_bar", 0)
            if detect_bar < start_bar:
                continue

            # Regime check at detection bar
            passes, skip_reason = check_all_gates(volumes, atr, leg, self.config)
            if not passes:
                continue

            # Build regime label
            vol_gate = getattr(self.config, "vol_regime_gate", "neutral")
            regime_label = vol_gate if vol_gate != "neutral" else "neutral"

            # Zone bounds
            zone_low = getattr(leg, "zone_low", 0.0)
            zone_high = getattr(leg, "zone_high", 0.0)
            fib_382 = getattr(leg, "fib_382", zone_low)
            fib_618 = getattr(leg, "fib_618", zone_high)
            direction = getattr(leg, "direction", "bullish")

            # Stop and target
            stop_var = getattr(self.config, "stop_variant", "origin")
            target_fib = getattr(self.config, "target_fib", 1.618)

            anchor_low = getattr(leg, "anchor_low", zone_low)
            anchor_high = getattr(leg, "anchor_high", zone_high)
            atr_at_detect = atr[detect_bar] if detect_bar < len(atr) else 0.0

            if direction == "bullish":
                stop_price = (anchor_low - 0.5 * atr_at_detect) if stop_var == "origin" else fib_382
                leg_size = zone_high - zone_low
                target_price = zone_high + target_fib * leg_size
            else:
                stop_price = (
                    (anchor_high + 0.5 * atr_at_detect) if stop_var == "origin" else fib_618
                )
                leg_size = zone_high - zone_low
                target_price = zone_low - target_fib * leg_size

            detect_date = dates[detect_bar] if detect_bar < len(dates) else "UNKNOWN"
            setup_id = f"{self.ticker}_{detect_date}_{direction[:4]}"

            # Determine current state
            state, entry_date, entry_price, exit_date, exit_price, outcome_r, notes = (
                self._resolve_state(
                    leg,
                    detect_bar,
                    dates,
                    opens,
                    highs,
                    lows,
                    closes,
                    stop_price,
                    target_price,
                    direction,
                    zone_low,
                    zone_high,
                )
            )

            setup = MonitoredSetup(
                setup_id=setup_id,
                ticker=self.ticker,
                detection_date=detect_date,
                direction=direction,
                regime_at_detection=regime_label,
                zone_low=round(zone_low, 4),
                zone_high=round(zone_high, 4),
                fib_382=round(fib_382, 4),
                fib_618=round(fib_618, 4),
                stop_price=round(stop_price, 4),
                target_price=round(target_price, 4),
                state=state,
                entry_date=entry_date,
                entry_price=entry_price,
                exit_date=exit_date,
                exit_price=exit_price,
                outcome_r=outcome_r,
                notes=notes,
                config_name=getattr(self.config, "name", ""),
            )
            setups.append(setup)

        return setups

    def _resolve_state(
        self,
        leg,
        detect_bar: int,
        dates: list,
        opens: list,
        highs: list,
        lows: list,
        closes: list,
        stop_price: float,
        target_price: float,
        direction: str,
        zone_low: float,
        zone_high: float,
    ) -> tuple:
        """
        Walk forward from detect_bar to determine current setup state.

        Returns (state, entry_date, entry_price, exit_date, exit_price, outcome_r, notes)
        """
        n = len(dates)
        max_zone_wait = getattr(self.config, "max_zone_wait_bars", 10)
        trigger = getattr(self.config, "entry_trigger", "touch_rejection")

        entry_date = None
        entry_price = None
        exit_date = None
        exit_price = None
        outcome_r = None
        notes = ""

        # Simple touch_rejection state walk (daily triggers only)
        zone_touched = False
        trigger_fired = False
        bars_waited = 0
        trade_active = False

        for i in range(detect_bar + 1, n):
            bar_high = highs[i]
            bar_low = lows[i]
            bar_close = closes[i]
            bar_open = opens[i]
            bar_date = dates[i] if i < len(dates) else "UNKNOWN"

            if not trade_active:
                if not trigger_fired:
                    bars_waited += 1

                    # Check invalidation (stop hit before entry)
                    if direction == "bullish" and bar_low < stop_price:
                        notes = "Invalidated: price hit stop before entry"
                        return "INVALIDATED", None, None, None, None, None, notes
                    if direction == "bearish" and bar_high > stop_price:
                        notes = "Invalidated: price hit stop before entry"
                        return "INVALIDATED", None, None, None, None, None, notes

                    # Zone touch check
                    if direction == "bullish" and bar_low <= zone_high:
                        zone_touched = True
                    if direction == "bearish" and bar_high >= zone_low:
                        zone_touched = True

                    if zone_touched:
                        # Touch-rejection: close back outside zone
                        if trigger in ("touch_rejection", "close_in_zone"):
                            if direction == "bullish" and bar_close > zone_low:
                                trigger_fired = True
                                # Entry at next open
                                if i + 1 < n:
                                    entry_price = opens[i + 1]
                                    entry_date = dates[i + 1]
                                    trade_active = True
                                    notes = "Trigger: touch_rejection"
                            elif direction == "bearish" and bar_close < zone_high:
                                trigger_fired = True
                                if i + 1 < n:
                                    entry_price = opens[i + 1]
                                    entry_date = dates[i + 1]
                                    trade_active = True
                                    notes = "Trigger: touch_rejection"

                    # Expiry
                    if bars_waited >= max_zone_wait and not trigger_fired:
                        notes = f"Expired: {bars_waited} bars without trigger"
                        return "EXPIRED", None, None, None, None, None, notes
                else:
                    # Waiting for entry fill next bar
                    trade_active = True

            else:
                # In trade: check stop and target
                if direction == "bullish":
                    if bar_low <= stop_price:
                        exit_price = stop_price
                        exit_date = bar_date
                        risk = entry_price - stop_price
                        outcome_r = (exit_price - entry_price) / risk if risk > 0 else -1.0
                        return (
                            "CLOSED",
                            entry_date,
                            entry_price,
                            exit_date,
                            round(exit_price, 4),
                            round(outcome_r, 3),
                            "Stop hit",
                        )
                    if bar_high >= target_price:
                        exit_price = target_price
                        exit_date = bar_date
                        risk = entry_price - stop_price
                        outcome_r = (exit_price - entry_price) / risk if risk > 0 else 1.618
                        return (
                            "CLOSED",
                            entry_date,
                            entry_price,
                            exit_date,
                            round(exit_price, 4),
                            round(outcome_r, 3),
                            "Target hit",
                        )
                else:
                    if bar_high >= stop_price:
                        exit_price = stop_price
                        exit_date = bar_date
                        risk = stop_price - entry_price
                        outcome_r = (entry_price - exit_price) / risk if risk > 0 else -1.0
                        return (
                            "CLOSED",
                            entry_date,
                            entry_price,
                            exit_date,
                            round(exit_price, 4),
                            round(outcome_r, 3),
                            "Stop hit",
                        )
                    if bar_low <= target_price:
                        exit_price = target_price
                        exit_date = bar_date
                        risk = stop_price - entry_price
                        outcome_r = (entry_price - exit_price) / risk if risk > 0 else 1.618
                        return (
                            "CLOSED",
                            entry_date,
                            entry_price,
                            exit_date,
                            round(exit_price, 4),
                            round(outcome_r, 3),
                            "Target hit",
                        )

        # Still open at last bar
        if trade_active:
            return "IN_TRADE", entry_date, entry_price, None, None, None, "Trade open"
        elif trigger_fired:
            return "CONFIRMED", entry_date, entry_price, None, None, None, "Entry pending"
        elif zone_touched:
            return "ARMED", None, None, None, None, None, "Zone touched, awaiting trigger"
        else:
            return "ARMED", None, None, None, None, None, "Watching zone"

    # ---------------------------------------------------------------------------
    # Output
    # ---------------------------------------------------------------------------

    @staticmethod
    def print_ledger(setups: list[MonitoredSetup], title: str = "PAPER-TRADE LEDGER") -> None:
        """Print formatted paper-trade ledger."""
        w = 110
        print(f"\n{'=' * w}")
        print(f"  FIB8 TRACK B -- {title}")
        print(f"  {len(setups)} setup(s) monitored")
        print(f"{'=' * w}")

        if not setups:
            print(f"  No setups detected in lookback window.\n")
            return

        header = (
            f"  {'ID':<30} {'Dir':<8} {'State':<12} {'Regime':<12} "
            f"{'Zone':>10} {'Stop':>8} {'Target':>8} {'EntDate':<10} {'OutcomeR':>8}"
        )
        print(header)
        print(f"  {'-' * 105}")

        for s in setups:
            outcome_str = f"{s.outcome_r:+.3f}" if s.outcome_r is not None else "---"
            entry_str = s.entry_date or "---"
            zone_str = f"{s.zone_low:.2f}-{s.zone_high:.2f}"
            print(
                f"  {s.setup_id:<30} {s.direction[:4]:<8} {s.state:<12} {s.regime_at_detection:<12} "
                f"{zone_str:>10} {s.stop_price:>8.2f} {s.target_price:>8.2f} "
                f"{entry_str:<10} {outcome_str:>8}"
            )
            if s.notes:
                print(f"    Notes: {s.notes}")

        # Summary
        closed = [s for s in setups if s.state == "CLOSED" and s.outcome_r is not None]
        active = [s for s in setups if s.state in ("IN_TRADE", "CONFIRMED", "ARMED")]
        if closed:
            avg_r = sum(s.outcome_r for s in closed) / len(closed)
            wins = sum(1 for s in closed if s.outcome_r > 0)
            print(f"\n  Closed: {len(closed)}  |  Active: {len(active)}")
            print(f"  Closed ExpR: {avg_r:+.3f}R  Win%: {wins / len(closed):.1%}")
        else:
            print(f"\n  Active: {len(active)}  |  No closed setups yet")
        print(f"{'=' * w}\n")

    @staticmethod
    def save_ledger(setups: list[MonitoredSetup], path: str) -> None:
        """Save paper-trade ledger to JSON."""
        data = [asdict(s) for s in setups]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"  Ledger saved: {path} ({len(data)} setups)")

    @staticmethod
    def load_ledger(path: str) -> list[MonitoredSetup]:
        """Load paper-trade ledger from JSON."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [MonitoredSetup(**d) for d in data]
