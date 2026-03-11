"""Nightly batch pipeline for AutoTrader v2.

This package provides the components for the nightly scan pipeline:
- BatchFetcher: fetches daily bars for all S&P 500 symbols
- NightlyScanner: runs all strategies against fetched data
- SignalRanker: ranks and selects top N candidates
- GapFilter: filters out gapped candidates at 9:30 AM ET (post market open)
- BatchScheduler: asyncio-based scheduler with market calendar awareness
"""
