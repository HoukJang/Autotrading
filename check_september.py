"""
Check September 14-20 data in database
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from database.connection import get_db_manager


async def main():
    db = get_db_manager()

    try:
        await db.connect()

        # Check daily bar counts for Sept 14-20
        query = """
            SELECT
                DATE(timestamp) as date,
                COUNT(*) as bars,
                MIN(timestamp) as first_bar,
                MAX(timestamp) as last_bar
            FROM market_data_1min
            WHERE symbol = 'ES'
              AND timestamp >= '2025-09-14'
              AND timestamp <= '2025-09-21'
            GROUP BY DATE(timestamp)
            ORDER BY date
        """

        result = await db.fetch(query)

        print("=" * 70)
        print("September 14-20, 2025 Data in Database")
        print("=" * 70)
        print(f"\n{'Date':<12} | {'Bars':>6} | {'First Bar':<25} | {'Last Bar':<25}")
        print("-" * 95)

        total_bars = 0
        for row in result:
            total_bars += row['bars']
            print(f"{row['date']!s:<12} | {row['bars']:>6,} | {row['first_bar']!s:<25} | {row['last_bar']!s:<25}")

        print("-" * 95)
        print(f"{'TOTAL':<12} | {total_bars:>6,}")
        print("=" * 70)

    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
