"""
Greenblatt Universe Selection Model

Extracts the coarse/fine selection logic from main.py into its own module
so it can be independently audited and toggled.

NOTE: Only instantiate this when ENABLE_SLEEVE_B = True AND
      fundamental data is confirmed available (DataValidator.fundamental_data_available).

See sleeve_b.py for the full status note on local data availability.
"""

from __future__ import annotations
from math import ceil
from itertools import chain
from AlgorithmImports import *
from Selection.FundamentalUniverseSelectionModel import FundamentalUniverseSelectionModel
from algorithm.config import (
    GREENBLATT_N_COARSE,
    GREENBLATT_N_EVEBITDA,
    GREENBLATT_N_PORTFOLIO,
)


class GreenblattUniverseModel(FundamentalUniverseSelectionModel):
    """
    Selects top GREENBLATT_N_PORTFOLIO stocks from QC500 by:
      1. EV/EBITDA rank ascending (cheaper is better)
      2. Forward ROA rank descending (higher return on assets is better)

    Reselects monthly.  Sector-balanced pre-filter to avoid sector concentration.

    Quality filters applied in select_fine():
      - US domicile (country_id == "USA")
      - Listed on NYSE or NASDAQ
      - IPO > 180 days ago
      - Market cap > $500M (earnings * EPS * P/E proxy)
      - EV/EBITDA > 0  (removes distressed / financial sector outliers)
      - forward_ROA > 0  (positive return on assets)

    Data dependency: requires QuantConnect fundamental data (coarse + fine).
    Not available in local Lean install — see data/validator.py.
    """

    def __init__(self):
        super().__init__(filter_fine_data=True)
        self._last_month = -1
        self._dollar_vols: dict = {}

    def select_coarse(self, algorithm: QCAlgorithm, coarse):
        month = algorithm.time.month
        if month == self._last_month:
            return Universe.UNCHANGED
        self._last_month = month

        top = sorted(
            [x for x in coarse if x.has_fundamental_data],
            key=lambda x: x.dollar_volume,
            reverse=True,
        )[:GREENBLATT_N_COARSE]

        self._dollar_vols = {x.symbol: x.dollar_volume for x in top}
        return list(self._dollar_vols.keys())

    def select_fine(self, algorithm: QCAlgorithm, fine):
        filtered = [
            x
            for x in fine
            if x.company_reference.country_id == "USA"
            and x.company_reference.primary_exchange_id in ("NYS", "NAS")
            and (algorithm.time - x.security_reference.ipo_date).days > 180
            and (
                x.earning_reports.basic_average_shares.three_months
                * x.earning_reports.basic_eps.twelve_months
                * x.valuation_ratios.pe_ratio
            )
            > 5e8
            and x.valuation_ratios.ev_to_ebitda > 0
            and x.valuation_ratios.forward_roa > 0
        ]

        if not filtered:
            algorithm.log(
                f"GreenblattUniverse: select_fine returned 0 stocks "
                f"on {algorithm.time.date()} — check fundamental data availability"
            )
            return []

        # Distribute evenly across sectors to avoid concentration
        pct = GREENBLATT_N_EVEBITDA / max(len(filtered), 1)
        by_sector: dict[str, list] = {}
        for x in filtered:
            key = x.company_reference.industry_template_code
            by_sector.setdefault(key, []).append(x)

        for key in by_sector:
            by_sector[key].sort(
                key=lambda x: self._dollar_vols.get(x.symbol, 0),
                reverse=True,
            )
            by_sector[key] = by_sector[key][: ceil(len(by_sector[key]) * pct)]

        top_fine = list(chain.from_iterable(by_sector.values()))

        by_ev = sorted(top_fine, key=lambda x: x.valuation_ratios.ev_to_ebitda)
        by_roc = sorted(
            by_ev[:GREENBLATT_N_EVEBITDA],
            key=lambda x: x.valuation_ratios.forward_roa,
            reverse=True,
        )
        selected = [x.symbol for x in by_roc[:GREENBLATT_N_PORTFOLIO]]
        algorithm.log(
            f"GreenblattUniverse: selected {len(selected)} stocks on {algorithm.time.date()}"
        )
        return selected
