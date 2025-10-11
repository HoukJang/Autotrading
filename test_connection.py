"""
Test IB Gateway Connection and Retrieve Account Info
"""
import asyncio
import logging
from pathlib import Path
import sys

# Add autotrading to path
sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from broker import IBConnectionManager, IBClient
from core.event_bus import EventBus
from config import get_config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_connection():
    """Test connection and retrieve account information"""

    # Load configuration
    config = get_config()
    logger.info("=" * 60)
    logger.info("IB Gateway Connection Test")
    logger.info("=" * 60)
    logger.info(f"Connection Type: {config.broker.connection_name}")
    logger.info(f"Host: {config.broker.host}:{config.broker.port}")
    logger.info(f"Client ID: {config.broker.client_id}")
    logger.info("=" * 60)

    # Initialize event bus and client
    event_bus = EventBus()
    client = IBClient(event_bus)

    try:
        # Connect to IB Gateway
        logger.info("\n[1/3] Connecting to IB Gateway...")
        connected = await client.connect()

        if not connected:
            logger.error("Failed to connect to IB Gateway")
            logger.error("\nTroubleshooting:")
            logger.error("1. Check if IB Gateway is running")
            logger.error("2. Verify API is enabled in settings")
            logger.error(f"3. Confirm socket port is {config.broker.port}")
            logger.error("4. Check if 127.0.0.1 is in trusted IPs")
            return False

        logger.info("✓ Connected successfully!")

        # Wait a moment for connection to stabilize
        await asyncio.sleep(1)

        # Get account summary
        logger.info("\n[2/3] Retrieving account information...")
        account_info = await client.get_account_summary()

        logger.info("\n" + "=" * 60)
        logger.info("ACCOUNT INFORMATION")
        logger.info("=" * 60)
        logger.info(f"Account ID: {account_info.get('account_id', 'N/A')}")
        logger.info(f"Net Liquidation: ${account_info.get('net_liquidation', 0):,.2f}")
        logger.info(f"Available Funds: ${account_info.get('available_funds', 0):,.2f}")
        logger.info(f"Buying Power: ${account_info.get('buying_power', 0):,.2f}")
        logger.info(f"Excess Liquidity: ${account_info.get('excess_liquidity', 0):,.2f}")
        logger.info(f"Full Init Margin: ${account_info.get('full_init_margin_req', 0):,.2f}")
        logger.info(f"Full Maint Margin: ${account_info.get('full_maint_margin_req', 0):,.2f}")

        # Get positions
        logger.info("\n[3/3] Retrieving positions...")
        positions = await client.get_positions()

        logger.info("\n" + "=" * 60)
        logger.info("CURRENT POSITIONS")
        logger.info("=" * 60)

        if not positions:
            logger.info("No open positions")
        else:
            logger.info(f"Total Positions: {len(positions)}\n")
            for i, pos in enumerate(positions, 1):
                logger.info(f"Position {i}:")
                logger.info(f"  Symbol: {pos.get('symbol', 'N/A')}")
                logger.info(f"  Quantity: {pos.get('position', 0)}")
                logger.info(f"  Avg Cost: ${pos.get('avg_cost', 0):.2f}")
                logger.info(f"  Market Price: ${pos.get('market_price', 0):.2f}")
                logger.info(f"  Market Value: ${pos.get('market_value', 0):,.2f}")
                logger.info(f"  Unrealized PnL: ${pos.get('unrealized_pnl', 0):,.2f}")
                logger.info(f"  Realized PnL: ${pos.get('realized_pnl', 0):,.2f}")
                logger.info("")

        logger.info("=" * 60)
        logger.info("✓ Test completed successfully!")
        logger.info("=" * 60)

        return True

    except Exception as e:
        logger.error(f"\n✗ Error during test: {e}", exc_info=True)
        return False

    finally:
        # Disconnect
        logger.info("\nDisconnecting from IB Gateway...")
        await client.disconnect()
        logger.info("Disconnected")


async def main():
    """Main entry point"""
    try:
        success = await test_connection()
        return 0 if success else 1
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
