"""Orchestration layer: decomposed AutoTrader responsibilities.

This package contains classes extracted from the AutoTrader god class
to provide clearer separation of concerns:

- BatchPipelineOrchestrator: nightly scan -> gap filter -> entry pipeline
- HistoryManager: historical data loading and regime initialisation
"""
from autotrader.orchestration.batch_pipeline import (
    BatchPipelineOrchestrator,
    batch_to_entry_candidate,
)
from autotrader.orchestration.history_manager import HistoryManager

__all__ = [
    "BatchPipelineOrchestrator",
    "HistoryManager",
    "batch_to_entry_candidate",
]
