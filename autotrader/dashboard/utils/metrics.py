"""Reusable metric computation helpers for the dashboard."""
from __future__ import annotations

import pandas as pd


def max_consecutive_losses(pnl_series: pd.Series) -> int:
    """Return the length of the longest consecutive-loss streak."""
    if pnl_series.empty:
        return 0
    max_streak = 0
    current_streak = 0
    for pnl in pnl_series:
        if pnl < 0:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    return max_streak


# GICS Sector mapping for major S&P 500 stocks
SP500_SECTORS: dict[str, str] = {
    # Technology
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
    "GOOGL": "Technology", "GOOG": "Technology", "META": "Technology",
    "AVGO": "Technology", "ORCL": "Technology", "CRM": "Technology",
    "ADBE": "Technology", "AMD": "Technology", "INTC": "Technology",
    "QCOM": "Technology", "TXN": "Technology", "NOW": "Technology",
    "AMAT": "Technology", "MU": "Technology", "LRCX": "Technology",
    "KLAC": "Technology", "SNPS": "Technology", "CDNS": "Technology",
    "PANW": "Technology", "CRWD": "Technology", "FTNT": "Technology",
    "MRVL": "Technology", "ON": "Technology",
    # Healthcare
    "UNH": "Healthcare", "JNJ": "Healthcare", "LLY": "Healthcare",
    "ABBV": "Healthcare", "MRK": "Healthcare", "PFE": "Healthcare",
    "TMO": "Healthcare", "ABT": "Healthcare", "DHR": "Healthcare",
    "AMGN": "Healthcare", "BMY": "Healthcare", "GILD": "Healthcare",
    "ISRG": "Healthcare", "VRTX": "Healthcare", "MDT": "Healthcare",
    "REGN": "Healthcare", "SYK": "Healthcare", "BSX": "Healthcare",
    "ELV": "Healthcare", "ZTS": "Healthcare", "MRNA": "Healthcare",
    # Financials
    "BRK.B": "Financials", "JPM": "Financials", "V": "Financials",
    "MA": "Financials", "BAC": "Financials", "WFC": "Financials",
    "GS": "Financials", "MS": "Financials", "BLK": "Financials",
    "SCHW": "Financials", "AXP": "Financials", "C": "Financials",
    "SPGI": "Financials", "CB": "Financials", "PGR": "Financials",
    "CME": "Financials", "ICE": "Financials", "AON": "Financials",
    "MMC": "Financials", "USB": "Financials",
    # Consumer Discretionary
    "AMZN": "Consumer Disc.", "TSLA": "Consumer Disc.", "HD": "Consumer Disc.",
    "MCD": "Consumer Disc.", "NKE": "Consumer Disc.", "LOW": "Consumer Disc.",
    "SBUX": "Consumer Disc.", "TJX": "Consumer Disc.", "BKNG": "Consumer Disc.",
    "CMG": "Consumer Disc.", "ORLY": "Consumer Disc.", "ROST": "Consumer Disc.",
    "MAR": "Consumer Disc.", "DHI": "Consumer Disc.", "GM": "Consumer Disc.",
    "F": "Consumer Disc.", "LEN": "Consumer Disc.", "TGT": "Consumer Disc.",
    # Consumer Staples
    "PG": "Consumer Staples", "KO": "Consumer Staples", "PEP": "Consumer Staples",
    "COST": "Consumer Staples", "WMT": "Consumer Staples", "PM": "Consumer Staples",
    "MO": "Consumer Staples", "CL": "Consumer Staples", "MDLZ": "Consumer Staples",
    "EL": "Consumer Staples", "KMB": "Consumer Staples", "GIS": "Consumer Staples",
    "SYY": "Consumer Staples", "KHC": "Consumer Staples", "STZ": "Consumer Staples",
    # Communication Services
    "NFLX": "Communication", "DIS": "Communication", "CMCSA": "Communication",
    "T": "Communication", "VZ": "Communication", "TMUS": "Communication",
    "CHTR": "Communication", "EA": "Communication", "TTWO": "Communication",
    "WBD": "Communication",
    # Industrials
    "GE": "Industrials", "CAT": "Industrials", "RTX": "Industrials",
    "HON": "Industrials", "UNP": "Industrials", "BA": "Industrials",
    "DE": "Industrials", "LMT": "Industrials", "UPS": "Industrials",
    "GD": "Industrials", "MMM": "Industrials", "ITW": "Industrials",
    "WM": "Industrials", "EMR": "Industrials", "CSX": "Industrials",
    "NSC": "Industrials", "NOC": "Industrials", "FDX": "Industrials",
    # Energy
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy",
    "SLB": "Energy", "EOG": "Energy", "MPC": "Energy",
    "PSX": "Energy", "VLO": "Energy", "PXD": "Energy",
    "OXY": "Energy", "HAL": "Energy", "DVN": "Energy",
    # Utilities
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities",
    "D": "Utilities", "AEP": "Utilities", "SRE": "Utilities",
    "EXC": "Utilities", "XEL": "Utilities", "ED": "Utilities",
    "WEC": "Utilities",
    # Real Estate
    "PLD": "Real Estate", "AMT": "Real Estate", "CCI": "Real Estate",
    "EQIX": "Real Estate", "PSA": "Real Estate", "O": "Real Estate",
    "SPG": "Real Estate", "WELL": "Real Estate", "DLR": "Real Estate",
    # Materials
    "LIN": "Materials", "APD": "Materials", "SHW": "Materials",
    "ECL": "Materials", "NEM": "Materials", "FCX": "Materials",
    "NUE": "Materials", "DOW": "Materials", "DD": "Materials",
    "PPG": "Materials",
}
