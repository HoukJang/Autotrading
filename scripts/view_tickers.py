#!/usr/bin/env python3
"""
Ticker Table Viewer - 티커 테이블 조회 스크립트

티커 테이블의 데이터를 다양한 방식으로 조회하고 표시합니다.
"""

import argparse
import asyncio
import asyncpg
from typing import List, Dict, Any
from autotrading.config.settings import settings


async def get_ticker_stats() -> Dict[str, Any]:
    """티커 테이블 통계 조회"""
    conn = await asyncpg.connect(settings.database_url)

    stats = {}

    # 전체 통계
    stats['total'] = await conn.fetchval('SELECT COUNT(*) FROM tickers')
    stats['active'] = await conn.fetchval('SELECT COUNT(*) FROM tickers WHERE is_active = true')
    stats['inactive'] = await conn.fetchval('SELECT COUNT(*) FROM tickers WHERE is_active = false')
    stats['etfs'] = await conn.fetchval('SELECT COUNT(*) FROM tickers WHERE is_etf = true')
    stats['with_options'] = await conn.fetchval('SELECT COUNT(*) FROM tickers WHERE has_options = true')

    # 최근 업데이트
    stats['updated_today'] = await conn.fetchval('''
        SELECT COUNT(*) FROM tickers
        WHERE last_updated >= CURRENT_DATE
    ''')

    stats['never_updated'] = await conn.fetchval('''
        SELECT COUNT(*) FROM tickers
        WHERE last_updated IS NULL
    ''')

    await conn.close()
    return stats


async def get_ticker_list(limit: int = 20, active_only: bool = True, search: str = None) -> List[Dict[str, Any]]:
    """티커 목록 조회"""
    conn = await asyncpg.connect(settings.database_url)

    where_clauses = []
    params = []
    param_count = 0

    if active_only:
        where_clauses.append("is_active = true")

    if search:
        param_count += 1
        where_clauses.append(f"(symbol ILIKE ${param_count} OR company_name ILIKE ${param_count})")
        params.append(f"%{search}%")

    where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    param_count += 1
    query = f"""
        SELECT
            symbol,
            company_name,
            symbol_type,
            exchange,
            sector,
            is_active,
            is_etf,
            has_options,
            last_price,
            market_cap,
            pe_ratio,
            dividend_yield,
            last_updated,
            created_at
        FROM tickers
        {where_sql}
        ORDER BY
            CASE WHEN last_updated IS NULL THEN 1 ELSE 0 END,
            last_updated DESC,
            symbol
        LIMIT ${param_count}
    """
    params.append(limit)

    rows = await conn.fetch(query, *params)
    await conn.close()

    return [dict(row) for row in rows]


async def get_recent_updates(limit: int = 10) -> List[Dict[str, Any]]:
    """최근 업데이트된 티커들"""
    conn = await asyncpg.connect(settings.database_url)

    rows = await conn.fetch("""
        SELECT
            symbol,
            company_name,
            last_price,
            last_updated,
            updated_at
        FROM tickers
        WHERE last_updated IS NOT NULL
        ORDER BY last_updated DESC
        LIMIT $1
    """, limit)

    await conn.close()
    return [dict(row) for row in rows]


async def get_stale_tickers(days: int = 7) -> List[Dict[str, Any]]:
    """오래된 데이터를 가진 티커들"""
    conn = await asyncpg.connect(settings.database_url)

    rows = await conn.fetch("""
        SELECT
            symbol,
            company_name,
            last_updated,
            created_at,
            EXTRACT(EPOCH FROM (NOW() - last_updated))/86400 as days_stale
        FROM tickers
        WHERE is_active = true
          AND (last_updated IS NULL OR last_updated < NOW() - INTERVAL '%s days')
        ORDER BY
            CASE WHEN last_updated IS NULL THEN 1 ELSE 0 END,
            last_updated ASC
        LIMIT 20
    """ % days)

    await conn.close()
    return [dict(row) for row in rows]


def format_price(price):
    """가격 포맷팅"""
    if price is None:
        return "N/A"
    return f"${price:.2f}"


def format_market_cap(cap):
    """시가총액 포맷팅"""
    if cap is None:
        return "N/A"
    if cap >= 1_000_000_000:
        return f"${cap/1_000_000_000:.1f}B"
    elif cap >= 1_000_000:
        return f"${cap/1_000_000:.1f}M"
    else:
        return f"${cap:,.0f}"


def format_datetime(dt):
    """날짜시간 포맷팅"""
    if dt is None:
        return "Never"
    return dt.strftime("%Y-%m-%d %H:%M")


def print_stats(stats: Dict[str, Any]):
    """통계 출력"""
    print("📊 TICKER TABLE STATISTICS")
    print("=" * 50)
    print(f"Total Tickers:      {stats['total']:,}")
    print(f"Active:             {stats['active']:,}")
    print(f"Inactive:           {stats['inactive']:,}")
    print(f"ETFs:               {stats['etfs']:,}")
    print(f"With Options:       {stats['with_options']:,}")
    print(f"Updated Today:      {stats['updated_today']:,}")
    print(f"Never Updated:      {stats['never_updated']:,}")
    print()


def print_ticker_list(tickers: List[Dict[str, Any]], title: str = "TICKER LIST"):
    """티커 목록 출력"""
    print(f"📋 {title}")
    print("=" * 80)

    if not tickers:
        print("No tickers found.")
        return

    # 헤더
    print(f"{'Symbol':<8} {'Company':<25} {'Type':<6} {'Exchange':<4} {'Price':<10} {'Updated':<16}")
    print("-" * 80)

    # 데이터
    for ticker in tickers:
        symbol = ticker['symbol'][:8]
        company = (ticker['company_name'] or 'N/A')[:25]
        symbol_type = ticker['symbol_type'][:6]
        exchange = ticker['exchange'] or 'N/A'
        price = format_price(ticker['last_price'])
        updated = format_datetime(ticker['last_updated'])

        print(f"{symbol:<8} {company:<25} {symbol_type:<6} {exchange:<4} {price:<10} {updated:<16}")

    print()


async def main():
    parser = argparse.ArgumentParser(description="View ticker table data")
    parser.add_argument('--stats', action='store_true', help='Show table statistics')
    parser.add_argument('--list', type=int, default=20, help='Show ticker list (default: 20)')
    parser.add_argument('--recent', type=int, default=10, help='Show recently updated tickers')
    parser.add_argument('--stale', type=int, default=7, help='Show stale tickers (days)')
    parser.add_argument('--search', type=str, help='Search symbol or company name')
    parser.add_argument('--all', action='store_true', help='Include inactive tickers')

    args = parser.parse_args()

    try:
        # 통계 표시
        if args.stats:
            stats = await get_ticker_stats()
            print_stats(stats)

        # 티커 목록
        if args.list:
            active_only = not args.all
            tickers = await get_ticker_list(args.list, active_only, args.search)
            title = f"TICKER LIST ({'ALL' if args.all else 'ACTIVE ONLY'})"
            if args.search:
                title += f" - Search: '{args.search}'"
            print_ticker_list(tickers, title)

        # 최근 업데이트
        if args.recent:
            recent = await get_recent_updates(args.recent)
            print_ticker_list(recent, f"RECENTLY UPDATED ({args.recent})")

        # 오래된 데이터
        if args.stale:
            stale = await get_stale_tickers(args.stale)
            print_ticker_list(stale, f"STALE DATA (>{args.stale} days)")

        # 기본 동작 (아무 옵션 없으면)
        if not any([args.stats, args.list, args.recent, args.stale]):
            stats = await get_ticker_stats()
            print_stats(stats)

            tickers = await get_ticker_list(20, True)
            print_ticker_list(tickers, "TOP 20 ACTIVE TICKERS")

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)