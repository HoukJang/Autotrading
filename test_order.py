"""
Test Order Execution - ES Futures Market Order
"""
import asyncio
import logging
from pathlib import Path
import sys

# Add autotrading to path
sys.path.insert(0, str(Path(__file__).parent / 'autotrading'))

from broker import IBClient, ContractFactory
from core.event_bus import EventBus
from config import get_config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_order_execution():
    """Test order placement and monitoring"""

    config = get_config()
    logger.info("=" * 60)
    logger.info("IB Gateway Order Execution Test")
    logger.info("=" * 60)
    logger.info(f"Connection: {config.broker.connection_name}")
    logger.info("=" * 60)

    # Initialize event bus and client
    event_bus = EventBus()
    client = IBClient(event_bus)

    try:
        # Connect
        logger.info("\n[1/5] Connecting to IB Gateway...")
        connected = await client.connect()

        if not connected:
            logger.error("Failed to connect")
            return False

        logger.info("✓ Connected successfully!")
        await asyncio.sleep(1)

        # Get ES contract info
        logger.info("\n[2/5] Getting ES Futures contract specifications...")
        contract_specs = ContractFactory.get_contract_specs("ES")

        logger.info(f"\nES Futures Contract:")
        logger.info(f"  Exchange: {contract_specs['exchange']}")
        logger.info(f"  Tick Size: ${contract_specs['tick_size']}")
        logger.info(f"  Multiplier: {contract_specs['multiplier']}")
        logger.info(f"  Currency: {contract_specs['currency']}")

        # Subscribe to market data first
        logger.info("\n[3/5] Subscribing to ES market data...")
        subscribed = await client.subscribe_market_data("ES")

        if not subscribed:
            logger.error("Failed to subscribe to market data")
            return False

        logger.info("✓ Subscribed to ES market data")

        # Wait for market data
        logger.info("Waiting for market data updates...")
        await asyncio.sleep(3)

        # Check account before order
        logger.info("\n[4/5] Checking account before order...")
        account_before = await client.get_account_summary()
        logger.info(f"Account ID: {account_before.get('account_id', 'N/A')}")
        logger.info(f"Buying Power: ${account_before.get('buying_power', 0):,.2f}")

        # Place market order
        logger.info("\n[5/5] Placing TEST MARKET ORDER...")
        logger.info("⚠️  WARNING: This is a PAPER TRADING test order")
        logger.info("Symbol: ES (E-mini S&P 500 Futures)")
        logger.info("Quantity: 1 contract")
        logger.info("Action: BUY")
        logger.info("Order Type: MARKET")

        # Confirm before placing
        logger.info("\nPlacing order in 3 seconds...")
        await asyncio.sleep(1)
        logger.info("2...")
        await asyncio.sleep(1)
        logger.info("1...")
        await asyncio.sleep(1)

        try:
            order_id = await client.place_market_order("ES", 1, "BUY")
            logger.info(f"\n✓ Order placed successfully!")
            logger.info(f"Order ID: {order_id}")
        except Exception as e:
            logger.error(f"✗ Order placement failed: {e}")
            logger.info("\nThis is normal for paper trading if:")
            logger.info("1. Market data subscription is not active")
            logger.info("2. ES contract is not available")
            logger.info("3. Paper account has insufficient funds")
            return False

        # Wait for order to process
        logger.info("\nWaiting for order execution...")
        await asyncio.sleep(5)

        # Check positions
        logger.info("\n" + "=" * 60)
        logger.info("CHECKING POSITIONS AFTER ORDER")
        logger.info("=" * 60)

        positions = await client.get_positions()

        if positions:
            logger.info(f"Total Positions: {len(positions)}\n")
            for i, pos in enumerate(positions, 1):
                logger.info(f"Position {i}:")
                logger.info(f"  Symbol: {pos.get('symbol', 'N/A')}")
                logger.info(f"  Quantity: {pos.get('position', 0)}")
                logger.info(f"  Avg Cost: ${pos.get('avg_cost', 0):.2f}")
                logger.info(f"  Market Value: ${pos.get('market_value', 0):,.2f}")
                logger.info(f"  Unrealized PnL: ${pos.get('unrealized_pnl', 0):,.2f}")
                logger.info("")
        else:
            logger.info("No positions found (order may still be pending)")

        # Check account after
        logger.info("\n" + "=" * 60)
        logger.info("ACCOUNT SUMMARY AFTER ORDER")
        logger.info("=" * 60)
        account_after = await client.get_account_summary()
        logger.info(f"Net Liquidation: ${account_after.get('net_liquidation', 0):,.2f}")
        logger.info(f"Available Funds: ${account_after.get('available_funds', 0):,.2f}")
        logger.info(f"Buying Power: ${account_after.get('buying_power', 0):,.2f}")
        logger.info(f"Unrealized PnL: ${account_after.get('unrealized_pnl', 0):,.2f}")

        logger.info("\n" + "=" * 60)
        logger.info("✓ Order execution test completed!")
        logger.info("=" * 60)

        return True

    except Exception as e:
        logger.error(f"\n✗ Error during test: {e}", exc_info=True)
        return False

    finally:
        # Cleanup
        logger.info("\nCleaning up...")

        # Unsubscribe from market data
        try:
            await client.unsubscribe_market_data("ES")
            logger.info("✓ Unsubscribed from ES market data")
        except:
            pass

        # Disconnect
        logger.info("Disconnecting from IB Gateway...")
        await client.disconnect()
        logger.info("Disconnected")


async def main():
    """Main entry point"""
    try:
        success = await test_order_execution()
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
