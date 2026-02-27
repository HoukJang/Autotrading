from __future__ import annotations

import io

import pandas as pd
import requests

from autotrader.universe import StockInfo

_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_USER_AGENT = "AutoTrader/2.0 (stock-screener; Python/pandas)"


class SP500Provider:
    def __init__(self) -> None:
        self._cache: list[StockInfo] | None = None

    def fetch(self, *, force_refresh: bool = False) -> list[StockInfo]:
        if self._cache is not None and not force_refresh:
            return self._cache

        resp = requests.get(_WIKI_URL, headers={"User-Agent": _USER_AGENT}, timeout=30)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
        df = tables[0]

        result: list[StockInfo] = []
        for _, row in df.iterrows():
            symbol = str(row["Symbol"]).replace(".", "-")
            sector = str(row["GICS Sector"])
            sub = str(row.get("GICS Sub-Industry", ""))
            result.append(StockInfo(symbol=symbol, sector=sector, sub_industry=sub))

        self._cache = result
        return result
