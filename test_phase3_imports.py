"""
Quick test to verify Phase 3 imports work correctly
"""

import sys
from pathlib import Path

# Add autotrading to path
sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

print("Testing Phase 3 Data Pipeline imports...")
print("=" * 60)

try:
    from data import (
        BarBuilder,
        BarState,
        BarStorage,
        DataValidator,
        ValidationError,
        HistoricalDataFetcher,
        BackfillSystem,
        DataGap,
        DataExporter
    )
    print("[OK] All Phase 3 modules imported successfully")
    print()
    print("Imported classes:")
    print(f"  - BarBuilder: {BarBuilder}")
    print(f"  - BarState: {BarState}")
    print(f"  - BarStorage: {BarStorage}")
    print(f"  - DataValidator: {DataValidator}")
    print(f"  - ValidationError: {ValidationError}")
    print(f"  - HistoricalDataFetcher: {HistoricalDataFetcher}")
    print(f"  - BackfillSystem: {BackfillSystem}")
    print(f"  - DataGap: {DataGap}")
    print(f"  - DataExporter: {DataExporter}")
    print()
    print("=" * 60)
    print("Phase 3 Implementation: SUCCESS")
    print("=" * 60)

except ImportError as e:
    print(f"[ERROR] Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
