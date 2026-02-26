from __future__ import annotations

import pandas as pd

from autotrader.universe import StockInfo

_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


class SP500Provider:
    def __init__(self) -> None:
        self._cache: list[StockInfo] | None = None

    def fetch(self, *, force_refresh: bool = False) -> list[StockInfo]:
        if self._cache is not None and not force_refresh:
            return self._cache

        tables = pd.read_html(_WIKI_URL)
        df = tables[0]

        result: list[StockInfo] = []
        for _, row in df.iterrows():
            symbol = str(row["Symbol"]).replace(".", "-")
            sector = str(row["GICS Sector"])
            sub = str(row.get("GICS Sub-Industry", ""))
            result.append(StockInfo(symbol=symbol, sector=sector, sub_industry=sub))

        self._cache = result
        return result
