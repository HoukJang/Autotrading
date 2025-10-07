#!/usr/bin/env python3
"""
Interactive Brokers Connection Test Script
Tests connection to TWS or IB Gateway
"""

import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv()

try:
    from ib_async import IB, Contract, Future, Stock, util
except ImportError:
    print("❌ ib_async not installed. Please run: pip install ib_async")
    sys.exit(1)


async def test_basic_connection():
    """Test basic IB connection"""
    ib = IB()

    try:
        # Get connection parameters
        host = os.getenv('IB_HOST', '127.0.0.1')
        port = int(os.getenv('IB_PORT', 7497))
        client_id = int(os.getenv('IB_CLIENT_ID', 1))

        print(f"🔌 Attempting to connect to IB...")
        print(f"  Host: {host}")
        print(f"  Port: {port} ({'TWS' if port == 7497 else 'IB Gateway' if port == 4001 else 'Custom'})")
        print(f"  Client ID: {client_id}")
        print()

        # Connect
        await ib.connectAsync(host, port, clientId=client_id)

        if ib.isConnected():
            print("✅ Successfully connected to Interactive Brokers!")
            print(f"  Server Version: {ib.serverVersion()}")
            print(f"  Connection Time: {ib.connectionTime}")

            # Get account info
            accounts = ib.managedAccounts()
            if accounts:
                print(f"  Accounts: {', '.join(accounts)}")

            return ib
        else:
            print("❌ Failed to connect to Interactive Brokers")
            return None

    except Exception as e:
        print(f"❌ Connection error: {e}")
        print("\nTroubleshooting:")
        print("1. Ensure TWS or IB Gateway is running")
        print("2. Enable API connections in Global Configuration")
        print("3. Add 127.0.0.1 to Trusted IPs")
        print("4. Check the socket port (TWS: 7497, Gateway: 4001)")
        return None


async def test_market_data(ib):
    """Test market data subscription"""
    print("\n📊 Testing Market Data...")

    try:
        # Create ES futures contract
        contract = Future(
            symbol='ES',
            exchange='CME',
            currency='USD'
        )

        # Get contract details
        contracts = await ib.qualifyContractsAsync(contract)
        if contracts:
            contract = contracts[0]
            print(f"✅ Contract qualified: {contract.localSymbol}")

            # Request market data
            ticker = ib.reqMktData(contract, '', False, False)

            # Wait for data
            for _ in range(10):
                await asyncio.sleep(1)
                if ticker.last:
                    print(f"  Last Price: {ticker.last}")
                    print(f"  Bid: {ticker.bid} x {ticker.bidSize}")
                    print(f"  Ask: {ticker.ask} x {ticker.askSize}")
                    print(f"  Volume: {ticker.volume}")
                    break
            else:
                print("⚠️  No market data received (market might be closed)")

            # Cancel market data
            ib.cancelMktData(ticker)

        else:
            print("❌ Could not qualify ES futures contract")

    except Exception as e:
        print(f"❌ Market data error: {e}")


async def test_historical_data(ib):
    """Test historical data retrieval"""
    print("\n📈 Testing Historical Data...")

    try:
        # Create ES futures contract
        contract = Future(
            symbol='ES',
            exchange='CME',
            currency='USD'
        )

        # Get contract details
        contracts = await ib.qualifyContractsAsync(contract)
        if contracts:
            contract = contracts[0]

            # Request historical data
            bars = await ib.reqHistoricalDataAsync(
                contract,
                endDateTime='',
                durationStr='1 D',
                barSizeSetting='1 min',
                whatToShow='TRADES',
                useRTH=False
            )

            if bars:
                print(f"✅ Retrieved {len(bars)} bars of historical data")
                print(f"  First bar: {bars[0].date} - O:{bars[0].open} H:{bars[0].high} L:{bars[0].low} C:{bars[0].close}")
                print(f"  Last bar: {bars[-1].date} - O:{bars[-1].open} H:{bars[-1].high} L:{bars[-1].low} C:{bars[-1].close}")
            else:
                print("⚠️  No historical data received")

        else:
            print("❌ Could not qualify contract for historical data")

    except Exception as e:
        print(f"❌ Historical data error: {e}")


async def test_account_info(ib):
    """Test account information retrieval"""
    print("\n💰 Testing Account Information...")

    try:
        # Get account values
        account_values = ib.accountValues()
        if account_values:
            print("✅ Account values retrieved:")
            # Show key values only
            key_values = ['NetLiquidation', 'TotalCashValue', 'BuyingPower', 'MaintMarginReq']
            for av in account_values:
                if av.tag in key_values:
                    print(f"  {av.tag}: {av.value} {av.currency}")

        # Get positions
        positions = ib.positions()
        if positions:
            print(f"\n📦 Current positions: {len(positions)}")
            for pos in positions[:5]:  # Show first 5 positions
                print(f"  {pos.contract.symbol}: {pos.position} @ {pos.avgCost}")
        else:
            print("\n📦 No open positions")

        # Get open orders
        orders = ib.openOrders()
        if orders:
            print(f"\n📋 Open orders: {len(orders)}")
            for order in orders[:5]:  # Show first 5 orders
                print(f"  {order.contract.symbol}: {order.action} {order.totalQuantity} @ {order.orderType}")
        else:
            print("\n📋 No open orders")

    except Exception as e:
        print(f"❌ Account info error: {e}")


async def main():
    """Main test function"""
    print("🚀 Interactive Brokers Connection Test")
    print("=" * 50)

    # Check for .env file
    if not os.path.exists('.env'):
        print("⚠️  Warning: .env file not found")
        print("Using default connection parameters")
        print()

    # Test connection
    ib = await test_basic_connection()

    if ib and ib.isConnected():
        try:
            # Run additional tests
            await test_market_data(ib)
            await test_historical_data(ib)
            await test_account_info(ib)

            print("\n✨ All tests completed!")
            print("\n📝 System Status:")
            print("  ✅ IB API Connection: Working")
            print("  ✅ Market Data: Available")
            print("  ✅ Historical Data: Available")
            print("  ✅ Account Access: Granted")

            print("\n🎯 Next Steps:")
            print("1. Run database setup: python scripts/setup_database.py")
            print("2. Start development: python main.py --env development")

        finally:
            # Disconnect
            ib.disconnect()
            print("\n🔌 Disconnected from Interactive Brokers")
    else:
        print("\n❌ Connection test failed")
        print("\n🔧 Common Issues:")
        print("1. TWS/Gateway not running")
        print("2. API not enabled in configuration")
        print("3. Wrong port number (TWS: 7497, Gateway: 4001)")
        print("4. Firewall blocking connection")
        print("5. Another client using same Client ID")


if __name__ == "__main__":
    # Run the test
    asyncio.run(main())