"""
Portfolio Allocator — merges sleeve targets into final execution weights.

Responsibilities:
  1. Scale active sleeve allocations to fill 100% (redistribute disabled sleeves)
  2. Merge all sleeve target dicts into a single Symbol → weight map
  3. Apply position cap
  4. Produce LETF overlay
  5. Return a clean final weights dict ready for execution

This class owns NO trading logic and NO alpha — it is purely about
weight accounting.
"""

from __future__ import annotations
from AlgorithmImports import *
from algorithm.config import (
    ENABLE_SLEEVE_A,
    ENABLE_SLEEVE_B,
    ENABLE_SLEEVE_C,
    ENABLE_LETF_OVERLAY,
    SLEEVE_A_ALLOC,
    SLEEVE_B_ALLOC,
    SLEEVE_C_ALLOC,
    SLEEVE_B_FALLBACK,
    FALLBACK_ASSET,
    LETF_TICKER,
    LETF_WEIGHT,
    MAX_POSITION,
)


class Allocator:
    """
    Merges sleeve targets into a single Symbol → weight dict for execution.

    Scale logic (SLEEVE_B_FALLBACK="redistribute"):
      effective_a = SLEEVE_A_ALLOC / active_total
      effective_c = SLEEVE_C_ALLOC / active_total
    where active_total = sum of allocations for ENABLED sleeves.

    Scale logic (SLEEVE_B_FALLBACK="shy"):
      disabled sleeve allocation → FALLBACK_ASSET (additive)
    """

    def __init__(self, sym_map: dict[str, Symbol]):
        self._sym = sym_map
        self._effective = self._compute_effective_allocations()

    def effective_a(self) -> float:
        return self._effective["A"]

    def effective_b(self) -> float:
        return self._effective["B"]

    def effective_c(self) -> float:
        return self._effective["C"]

    # ------------------------------------------------------------------

    def merge(
        self,
        a_targets: dict[str, float] | None,
        b_targets: dict | None,  # keys may be Symbol or str
        c_targets: dict[str, float] | None,
        equity_regime: bool,
    ) -> dict[Symbol, float]:
        """
        Merge all sleeve targets into a single Symbol → weight map.

        Handles:
          - None sleeve targets (disabled sleeves in fallback="redistribute" mode)
          - String ticker keys from A and C
          - Symbol keys from B
          - LETF overlay on top of merged weights
          - Per-position cap enforcement
        """
        raw: dict[Symbol, float] = {}

        if a_targets:
            self._absorb_str_targets(a_targets, raw)

        if b_targets:
            self._absorb_mixed_targets(b_targets, raw)

        if c_targets:
            self._absorb_str_targets(c_targets, raw)

        # LETF overlay: short SPXU only in uptrend
        if ENABLE_LETF_OVERLAY and equity_regime:
            letf_sym = self._sym.get(LETF_TICKER)
            if letf_sym is not None:
                raw[letf_sym] = raw.get(letf_sym, 0.0) - LETF_WEIGHT

        # Enforce position cap on longs
        final: dict[Symbol, float] = {}
        for sym, w in raw.items():
            if w > MAX_POSITION:
                w = MAX_POSITION
            final[sym] = round(w, 5)

        return final

    # ------------------------------------------------------------------

    def describe_allocations(self) -> str:
        parts = []
        flags = {
            "A": ENABLE_SLEEVE_A,
            "B": ENABLE_SLEEVE_B,
            "C": ENABLE_SLEEVE_C,
        }
        for k, enabled in flags.items():
            eff = self._effective[k]
            label = f"[ON  {eff:.0%}]" if enabled else "[OFF ]"
            parts.append(f"Sleeve{k}{label}")
        fallback_note = f" | B fallback={SLEEVE_B_FALLBACK}" if not ENABLE_SLEEVE_B else ""
        return "  ".join(parts) + fallback_note

    # ------------------------------------------------------------------

    def _absorb_str_targets(
        self,
        targets: dict[str, float],
        out: dict[Symbol, float],
    ) -> None:
        for ticker, w in targets.items():
            sym = self._sym.get(ticker)
            if sym is not None:
                out[sym] = out.get(sym, 0.0) + w

    def _absorb_mixed_targets(
        self,
        targets: dict,
        out: dict[Symbol, float],
    ) -> None:
        for key, w in targets.items():
            if isinstance(key, str):
                sym = self._sym.get(key)
                if sym is not None:
                    out[sym] = out.get(sym, 0.0) + w
            elif isinstance(key, Symbol):
                out[key] = out.get(key, 0.0) + w

    # ------------------------------------------------------------------

    def _compute_effective_allocations(self) -> dict[str, float]:
        """
        Compute the actual sleeve allocations after accounting for
        which sleeves are enabled and the fallback policy.
        """
        if SLEEVE_B_FALLBACK == "redistribute":
            active_total = (
                (SLEEVE_A_ALLOC if ENABLE_SLEEVE_A else 0.0)
                + (SLEEVE_B_ALLOC if ENABLE_SLEEVE_B else 0.0)
                + (SLEEVE_C_ALLOC if ENABLE_SLEEVE_C else 0.0)
            )
            if active_total == 0:
                active_total = 1.0
            return {
                "A": round(SLEEVE_A_ALLOC / active_total, 5) if ENABLE_SLEEVE_A else 0.0,
                "B": round(SLEEVE_B_ALLOC / active_total, 5) if ENABLE_SLEEVE_B else 0.0,
                "C": round(SLEEVE_C_ALLOC / active_total, 5) if ENABLE_SLEEVE_C else 0.0,
            }
        else:  # "shy" — disabled sleeves contribute their weight to FALLBACK_ASSET
            return {
                "A": SLEEVE_A_ALLOC if ENABLE_SLEEVE_A else 0.0,
                "B": SLEEVE_B_ALLOC if ENABLE_SLEEVE_B else 0.0,
                "C": SLEEVE_C_ALLOC if ENABLE_SLEEVE_C else 0.0,
            }
