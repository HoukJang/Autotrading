#!/usr/bin/env python3
"""
Autotrading 사용 예시

자동 인증을 포함한 전체 시스템 사용법을 보여줍니다.
"""

import asyncio
import logging
from datetime import datetime

from autotrading.core.context import create_shared_context, close_shared_context
from autotrading.data.collector import DataCollector
from autotrading.analysis.analyzer import Analyzer
from autotrading.trading.trader import Trader
from autotrading.backtest.backtester import Backtester


async def example_basic_usage():
    """기본 사용법 예시"""
    print("="*60)
    print("🚀 AUTOTRADING BASIC USAGE EXAMPLE")
    print("="*60)

    # SharedContext 생성 (자동 인증 포함)
    print("\n📋 Creating SharedContext with automatic authentication...")
    context = await create_shared_context(auto_auth=True)

    print("✅ SharedContext created successfully!")
    print(f"   - Database: Connected")
    print(f"   - Schwab API: {'Authenticated' if context['schwab_service'].is_authenticated() else 'Not Authenticated'}")
    print(f"   - Environment: {context['config'].environment}")

    try:
        # 간단한 API 테스트
        print("\n🔍 Testing API connection...")
        health = await context['schwab_service'].health_check()
        print(f"   - Health Status: {health['status']}")
        print(f"   - Circuit Breaker: {health.get('circuit_breaker', {}).get('state', 'N/A')}")

        print("\n✅ Basic setup completed successfully!")

    finally:
        # 리소스 정리
        await close_shared_context(context)
        print("\n🧹 Resources cleaned up")


async def example_data_collection():
    """데이터 수집 예시"""
    print("="*60)
    print("📊 DATA COLLECTION EXAMPLE")
    print("="*60)

    context = await create_shared_context()

    try:
        # DataCollector 생성
        collector = DataCollector(context)
        symbols = ['AAPL', 'GOOGL', 'MSFT']

        print(f"\n📈 Collecting data for: {', '.join(symbols)}")

        # 최신 1분봉 데이터 수집
        result = await collector.collect_latest_bars(symbols)

        print(f"✅ Data collection completed:")
        print(f"   - Collected: {result.get('collected_count', 0)} symbols")
        print(f"   - Failed: {result.get('failed_count', 0)} symbols")
        print(f"   - Total bars: {result.get('total_bars', 0)}")

    except Exception as e:
        print(f"❌ Data collection failed: {e}")
    finally:
        await close_shared_context(context)


async def example_analysis():
    """분석 예시"""
    print("="*60)
    print("🔍 TECHNICAL ANALYSIS EXAMPLE")
    print("="*60)

    context = await create_shared_context()

    try:
        # Analyzer 생성
        analyzer = Analyzer(context)
        symbol = 'AAPL'

        print(f"\n📊 Analyzing {symbol}...")

        # 기술적 분석 수행
        signals = await analyzer.generate_signals(symbol)

        print(f"✅ Analysis completed for {symbol}:")
        print(f"   - RSI: {signals.get('rsi', 'N/A')}")
        print(f"   - MA Signal: {signals.get('ma_signal', 'N/A')}")
        print(f"   - Recommendation: {signals.get('recommendation', 'HOLD')}")
        print(f"   - Confidence: {signals.get('confidence', 0):.2%}")

    except Exception as e:
        print(f"❌ Analysis failed: {e}")
    finally:
        await close_shared_context(context)


async def example_trading():
    """거래 예시"""
    print("="*60)
    print("💰 TRADING EXAMPLE")
    print("="*60)

    context = await create_shared_context()

    try:
        # Trader 생성
        trader = Trader(context)

        print("\n📊 Checking account status...")

        # 계좌 정보 조회
        accounts = await trader.get_accounts()
        if accounts:
            account_hash = list(accounts.keys())[0]
            account_info = accounts[account_hash]

            print(f"✅ Account found: {account_hash[:8]}...")
            print(f"   - Buying Power: ${account_info.get('buying_power', 0):,.2f}")
            print(f"   - Cash Balance: ${account_info.get('cash_balance', 0):,.2f}")

            # 포지션 조회
            positions = await trader.get_positions(account_hash)
            print(f"   - Positions: {len(positions)} holdings")

        else:
            print("❌ No trading accounts found")

    except Exception as e:
        print(f"❌ Trading example failed: {e}")
    finally:
        await close_shared_context(context)


async def example_backtest():
    """백테스트 예시"""
    print("="*60)
    print("📈 BACKTESTING EXAMPLE")
    print("="*60)

    context = await create_shared_context()

    try:
        # Backtester 생성
        backtester = Backtester(context)

        print("\n📊 Running backtest...")

        # 백테스트 설정
        strategy_config = {
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'ma_short': 20,
            'ma_long': 50
        }

        symbols = ['AAPL', 'GOOGL']
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = datetime.now()

        print(f"   - Symbols: {', '.join(symbols)}")
        print(f"   - Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        print(f"   - Strategy: RSI + Moving Average")

        # 백테스트 실행
        result = await backtester.run_strategy(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            strategy_config=strategy_config
        )

        print(f"✅ Backtest completed:")
        print(f"   - Total Return: {result.get('total_return', 0):+.2%}")
        print(f"   - Sharpe Ratio: {result.get('sharpe_ratio', 0):.2f}")
        print(f"   - Max Drawdown: {result.get('max_drawdown', 0):.2%}")
        print(f"   - Total Trades: {result.get('total_trades', 0)}")

    except Exception as e:
        print(f"❌ Backtesting failed: {e}")
    finally:
        await close_shared_context(context)


async def example_complete_workflow():
    """완전한 트레이딩 워크플로우 예시"""
    print("="*60)
    print("🎯 COMPLETE TRADING WORKFLOW")
    print("="*60)

    # 자동 인증 포함 초기화
    context = await create_shared_context(auto_auth=True)

    try:
        symbols = ['AAPL', 'GOOGL', 'MSFT']

        # 서비스 객체들 생성
        collector = DataCollector(context)
        analyzer = Analyzer(context)
        trader = Trader(context)

        print("\n1️⃣ Data Collection Phase...")
        # 데이터 수집
        collection_result = await collector.collect_latest_bars(symbols)
        print(f"   ✅ Collected data for {collection_result.get('collected_count', 0)} symbols")

        print("\n2️⃣ Analysis Phase...")
        # 각 심볼 분석
        analysis_results = {}
        for symbol in symbols:
            try:
                signals = await analyzer.generate_signals(symbol)
                analysis_results[symbol] = signals
                recommendation = signals.get('recommendation', 'HOLD')
                confidence = signals.get('confidence', 0)
                print(f"   📊 {symbol}: {recommendation} (confidence: {confidence:.1%})")
            except Exception as e:
                print(f"   ❌ {symbol}: Analysis failed - {e}")

        print("\n3️⃣ Trading Decision Phase...")
        # 거래 결정 (실제 주문은 주석 처리)
        for symbol, signals in analysis_results.items():
            recommendation = signals.get('recommendation', 'HOLD')
            confidence = signals.get('confidence', 0)

            if recommendation == 'BUY' and confidence > 0.7:
                print(f"   🟢 {symbol}: Strong BUY signal (would place buy order)")
                # await trader.place_buy_order(symbol, quantity=10)
            elif recommendation == 'SELL' and confidence > 0.7:
                print(f"   🔴 {symbol}: Strong SELL signal (would place sell order)")
                # await trader.place_sell_order(symbol, quantity=10)
            else:
                print(f"   ⚪ {symbol}: {recommendation} - No action")

        print("\n✅ Workflow completed successfully!")

    except Exception as e:
        print(f"❌ Workflow failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await close_shared_context(context)


async def main():
    """메인 함수 - 모든 예시 실행"""
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("🤖 AUTOTRADING SYSTEM EXAMPLES")
    print("="*60)
    print("자동 인증을 포함한 전체 시스템 사용법을 보여줍니다.")
    print("최초 실행 시 브라우저 인증이 필요할 수 있습니다.")
    print("="*60)

    examples = [
        ("Basic Usage", example_basic_usage),
        ("Data Collection", example_data_collection),
        ("Technical Analysis", example_analysis),
        ("Trading", example_trading),
        ("Backtesting", example_backtest),
        ("Complete Workflow", example_complete_workflow)
    ]

    for i, (name, func) in enumerate(examples, 1):
        print(f"\n[{i}/{len(examples)}] {name}")
        choice = input("실행하시겠습니까? (y/n/q): ").strip().lower()

        if choice == 'q':
            print("종료합니다.")
            break
        elif choice == 'y':
            try:
                await func()
            except KeyboardInterrupt:
                print("\n중단되었습니다.")
                break
            except Exception as e:
                print(f"❌ 예시 실행 실패: {e}")

            input("\nPress ENTER to continue...")
        else:
            print("건너뜁니다.")

    print("\n🎉 모든 예시가 완료되었습니다!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n프로그램이 중단되었습니다.")
    except Exception as e:
        print(f"❌ 프로그램 실행 오류: {e}")
        import traceback
        traceback.print_exc()