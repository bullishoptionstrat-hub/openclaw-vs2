# region imports
import sys
import os

# Make QuantumEdge/ a Python package root so sub-modules are importable
_QE_ROOT = os.path.dirname(os.path.abspath(__file__))
if _QE_ROOT not in sys.path:
    sys.path.insert(0, _QE_ROOT)

from AlgorithmImports import *
# endregion

# ---------------------------------------------------------------------------
# QuantumEdge — Main Algorithm Entry Point  (wiring layer only)
# ---------------------------------------------------------------------------
# This file should contain NO alpha logic, NO magic numbers, and NO
# configuration constants.  It wires together the modular components.
#
# Alpha lives in:
#   strategy/sleeve_a.py  — sector momentum
#   strategy/sleeve_b.py  — Greenblatt (disabled locally)
#   strategy/sleeve_c.py  — IBS mean reversion
#   strategy/regime.py    — equity/defensive regime
#   strategy/allocator.py — weight merging
#
# All tunable parameters are in:
#   algorithm/config.py
#
# Data checks are in:
#   data/validator.py
# ---------------------------------------------------------------------------

import algorithm.config as cfg
from strategy.regime import RegimeFilter
from strategy.sleeve_a import SleeveA
from strategy.sleeve_b import SleeveB
from strategy.sleeve_c import SleeveC
from strategy.allocator import Allocator
from data.validator import DataValidator
from data.universe import GreenblattUniverseModel


class QuantumEdge(QCAlgorithm):
    def initialize(self):
        # ── Print experiment identity ──────────────────────────────────────
        self.log(f"QuantumEdge  experiment={cfg.EXPERIMENT_NAME}")
        self.log(
            f"  Sleeves: A={cfg.ENABLE_SLEEVE_A}  "
            f"B={cfg.ENABLE_SLEEVE_B}  "
            f"C={cfg.ENABLE_SLEEVE_C}  "
            f"LETF={cfg.ENABLE_LETF_OVERLAY}"
        )
        self.log(
            f"  Regime: filter={cfg.USE_REGIME_FILTER}  "
            f"spy_sma={cfg.USE_SPY_SMA_FILTER}  "
            f"vxx={cfg.USE_VXX_FILTER}"
        )
        self.log(
            f"  Allocs: A={cfg.SLEEVE_A_ALLOC:.0%}  "
            f"B={cfg.SLEEVE_B_ALLOC:.0%}  "
            f"C={cfg.SLEEVE_C_ALLOC:.0%}  "
            f"B_fallback={cfg.SLEEVE_B_FALLBACK}"
        )

        # ── Backtest dates and capital ─────────────────────────────────────
        self.set_start_date(cfg.START_YEAR, cfg.START_MONTH, cfg.START_DAY)
        self.set_end_date(cfg.END_YEAR, cfg.END_MONTH, cfg.END_DAY)
        self.set_cash(cfg.INITIAL_CASH)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)

        # ── Data validation (runs before any trading) ──────────────────────
        lean_data_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "lean", "Data")
        )
        validator = DataValidator(lean_data_root)
        report = validator.validate()
        for line in report.to_log_lines():
            self.log(line)
        if not report.valid:
            raise Exception(
                "DataValidator found critical errors. "
                "Fix data issues or adjust config before running. "
                "See log above for details."
            )

        # ── Greenblatt universe (Sleeve B only) ───────────────────────────
        self._magic_symbols: set[Symbol] = set()
        self._magic_std: dict[Symbol, StandardDeviation] = {}

        if cfg.ENABLE_SLEEVE_B:
            self.set_universe_selection(GreenblattUniverseModel())

        # ── ETF subscriptions ─────────────────────────────────────────────
        all_tickers = list(
            set(cfg.SECTORS + cfg.IBS_ETFS + [cfg.LETF_TICKER, cfg.FALLBACK_ASSET, "VXX", "SPY"])
        )
        self._sym: dict[str, Symbol] = {}
        for ticker in all_tickers:
            eq = self.add_equity(ticker, Resolution.DAILY)
            eq.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            self._sym[ticker] = eq.symbol

        # ── ETF indicators ─────────────────────────────────────────────────
        self._mom: dict[str, RateOfChange] = {}
        self._std: dict[str, StandardDeviation] = {}
        self._long_mom: dict[str, RateOfChange] = {}

        for ticker in all_tickers:
            sym = self._sym[ticker]
            self._mom[ticker] = self.roc(sym, cfg.MOMENTUM_DAYS, Resolution.DAILY)
            self._std[ticker] = self.std(sym, cfg.RISK_VOL_LB, Resolution.DAILY)
            self._long_mom[ticker] = self.roc(sym, cfg.VALUE_LOOKBACK, Resolution.DAILY)

        spy_sma = self.sma(self._sym["SPY"], cfg.TREND_SMA_DAYS, Resolution.DAILY)
        vxx_sma = self.sma(self._sym["VXX"], cfg.VXX_SMA_DAYS, Resolution.DAILY)

        # ── Allocator (computes effective sleeve weights) ──────────────────
        self._allocator = Allocator(self._sym)
        self.log("Effective allocations: " + self._allocator.describe_allocations())

        # ── Regime filter ─────────────────────────────────────────────────
        self._regime_filter = RegimeFilter(
            algorithm=self,
            spy_sma=spy_sma,
            vxx_sma=vxx_sma,
            spy_sym=self._sym["SPY"],
            vxx_sym=self._sym["VXX"],
            use_regime_filter=cfg.USE_REGIME_FILTER,
        )

        # ── Sleeve objects ─────────────────────────────────────────────────
        if cfg.ENABLE_SLEEVE_A:
            self._sleeve_a = SleeveA(
                algorithm=self,
                sym_map=self._sym,
                mom_map=self._mom,
                std_map=self._std,
                long_mom_map=self._long_mom,
                allocation=self._allocator.effective_a(),
            )
        else:
            self._sleeve_a = None

        if cfg.ENABLE_SLEEVE_B:
            self._sleeve_b = SleeveB(
                algorithm=self,
                std_map=self._magic_std,
                allocation=self._allocator.effective_b(),
            )
            # SleeveB.validate() logs loud warning if DATA_AVAILABLE=False
            self._sleeve_b.validate()
        else:
            self._sleeve_b = None

        if cfg.ENABLE_SLEEVE_C:
            self._sleeve_c = SleeveC(
                algorithm=self,
                sym_map=self._sym,
                std_map=self._std,
                allocation=self._allocator.effective_c(),
            )
        else:
            self._sleeve_c = None

        # ── State ─────────────────────────────────────────────────────────
        self._day_count = 0
        self._regime_label = "init"
        self._last_rebal_date = None

        # ── Warmup + schedule ─────────────────────────────────────────────
        self.set_warm_up(cfg.WARMUP_DAYS, Resolution.DAILY)
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open("SPY", 30),
            self._rebalance,
        )

    # ── Universe change: track Greenblatt stocks ──────────────────────────

    def on_securities_changed(self, changes: SecurityChanges):
        if not cfg.ENABLE_SLEEVE_B:
            return
        for s in changes.added_securities:
            sym = s.symbol
            if sym not in self._magic_std and sym not in self._sym.values():
                self._magic_std[sym] = self.std(sym, cfg.RISK_VOL_LB, Resolution.DAILY)
                self._magic_symbols.add(sym)
        for s in changes.removed_securities:
            sym = s.symbol
            if sym in self._magic_symbols:
                self._magic_symbols.discard(sym)
                self._magic_std.pop(sym, None)

    # ── Main rebalance ────────────────────────────────────────────────────

    def _rebalance(self):
        if self.is_warming_up:
            return

        self._day_count += 1
        if self._day_count % cfg.REBAL_DAYS != 0:
            return

        equity_mode = self._regime_filter.is_equity()
        self._regime_label = "equity" if equity_mode else "defensive"

        # Verbose rebalance log every ~20 days
        if self._day_count % (cfg.REBAL_DAYS * 2) == 0:
            self.log(
                f"REBAL  {self.time.date()}  "
                f"regime={self._regime_label}  "
                f"{self._regime_filter.describe()}"
            )
            if self._sleeve_a:
                self.log(self._sleeve_a.describe())
            if self._sleeve_c:
                self.log(self._sleeve_c.describe())

        # ── Gather sleeve targets ─────────────────────────────────────────
        a_t = self._sleeve_a.targets(equity_mode) if self._sleeve_a else None
        b_t = self._sleeve_b.targets(equity_mode, self._magic_symbols) if self._sleeve_b else None
        c_t = self._sleeve_c.targets() if self._sleeve_c else None

        # ── Merge into final weights ──────────────────────────────────────
        final = self._allocator.merge(a_t, b_t, c_t, equity_mode)

        # ── Execute ───────────────────────────────────────────────────────
        self._execute(final)
        self._last_rebal_date = self.time.date()

    # ── Execution ─────────────────────────────────────────────────────────

    def _execute(self, final: dict[Symbol, float]):
        total_val = max(self.portfolio.total_portfolio_value, 1.0)

        # Liquidate positions not in final targets
        for holding in self.portfolio.values():
            if not holding.invested:
                continue
            if holding.symbol not in final or final[holding.symbol] == 0.0:
                self.liquidate(holding.symbol)

        # Apply new targets (skip tiny changes to avoid churn)
        for sym, weight in final.items():
            sec = self.securities.get(sym)
            if sec is None or sec.price == 0:
                continue
            current_w = self.portfolio[sym].holdings_value / total_val
            if abs(current_w - weight) < cfg.CHURN_THRESHOLD:
                continue
            self.set_holdings(sym, weight)

    # ── Charts ────────────────────────────────────────────────────────────

    def on_end_of_day(self, symbol):
        spy_sym = self._sym.get("SPY")
        if symbol != spy_sym:
            return
        self.plot("Regime", "Mode", 1 if self._regime_label == "equity" else -1)
        self.plot("Portfolio", "Total Value", self.portfolio.total_portfolio_value)
