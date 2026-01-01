"""
Verify data in database
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from database.connection import get_db_manager


async def main():
    """Verify database data"""
    print("=" * 70)
    print("Database Data Verification")
    print("=" * 70)

    db = get_db_manager()

    try:
        # Connect
        print("\nConnecting to database...")
        await db.connect()
        print("Connected\n")

        # Get summary
        query = """
            SELECT
                symbol,
                COUNT(*) as bar_count,
                MIN(timestamp) as first_bar,
                MAX(timestamp) as last_bar,
                MIN(open_price) as min_price,
                MAX(high_price) as max_price,
                SUM(volume) as total_volume
            FROM market_data_1min
            WHERE symbol = 'ES'
            GROUP BY symbol
        """

        result = await db.fetchrow(query)

        if result:
            print("[OK] Data Summary:")
            print(f"   Symbol: {result['symbol']}")
            print(f"   Total bars: {result['bar_count']:,}")
            print(f"   First bar: {result['first_bar']}")
            print(f"   Last bar: {result['last_bar']}")
            print(f"   Price range: ${result['min_price']:,.2f} - ${result['max_price']:,.2f}")
            print(f"   Total volume: {result['total_volume']:,}")

            # Get sample bars
            print("\n[SAMPLE] First 5 bars:")
            sample_query = """
                SELECT timestamp, open_price, high_price, low_price, close_price, volume
                FROM market_data_1min
                WHERE symbol = 'ES'
                ORDER BY timestamp ASC
                LIMIT 5
            """
            samples = await db.fetch(sample_query)

            for bar in samples:
                print(f"   {bar['timestamp']} | O:{bar['open_price']} H:{bar['high_price']} "
                      f"L:{bar['low_price']} C:{bar['close_price']} V:{bar['volume']}")

            # Check for gaps
            print("\n[CHECK] Data gaps...")
            gap_query = """
                WITH time_gaps AS (
                    SELECT
                        timestamp,
                        LAG(timestamp) OVER (ORDER BY timestamp) as prev_timestamp,
                        timestamp - LAG(timestamp) OVER (ORDER BY timestamp) as gap
                    FROM market_data_1min
                    WHERE symbol = 'ES'
                )
                SELECT COUNT(*) as gap_count
                FROM time_gaps
                WHERE gap > INTERVAL '5 minutes'
            """
            gap_result = await db.fetchrow(gap_query)

            if gap_result['gap_count'] > 0:
                print(f"   [WARN] Found {gap_result['gap_count']} gaps > 5 minutes")
                print("   (This is normal - includes weekends and daily maintenance)")
            else:
                print("   [OK] No significant gaps detected")

        else:
            print("[ERROR] No data found for symbol 'ES'")

        print("\n" + "=" * 70)
        print("Verification complete!")
        print("=" * 70)

    finally:
        await db.disconnect()
        print("\nDisconnected")


if __name__ == "__main__":
    asyncio.run(main())
