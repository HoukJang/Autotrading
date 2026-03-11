"""Quick nightly scan runner for manual signal checking."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join("config", ".env"))

from autotrader.batch.scanner import NightlyScanner
from autotrader.data.batch_fetcher import BatchFetcher
from autotrader.universe.provider import SP500Provider


async def main():
    api_key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
    if not api_key or not secret:
        print("ERROR: Alpaca API keys not found in config/.env")
        return

    provider = SP500Provider()
    stocks = provider.fetch()
    symbols = [s.symbol for s in stocks]
    print(f"Scanning {len(symbols)} S&P 500 symbols...")

    fetcher = BatchFetcher(api_key, secret)
    scanner = NightlyScanner(fetcher)
    result = await scanner.run(symbols)

    print(f"\n=== Scan Complete ===")
    print(f"Symbols scanned: {result.symbols_scanned}")
    print(f"Symbols with signals: {result.symbols_with_signals}")
    print(f"Candidates selected: {len(result.candidates)}")
    print(f"Regime: {result.regime}")
    print()
    if result.candidates:
        print("Tomorrow Candidates:")
        for c in result.candidates:
            sr = c.scan_result
            print(
                f"  {sr.symbol:6s} | {sr.strategy:25s} | {sr.direction:5s} "
                f"| strength={sr.signal_strength:.3f} | composite={c.composite_score:.3f} "
                f"| prev_close=${sr.prev_close:.2f}"
            )
    else:
        print("No candidates found.")


if __name__ == "__main__":
    asyncio.run(main())
