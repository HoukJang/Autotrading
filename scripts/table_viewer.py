#!/usr/bin/env python3
"""
Database Table Viewer - 데이터베이스 테이블 범용 뷰어

프로젝트의 모든 테이블을 조회하고 표시할 수 있는 범용 스크립트입니다.
"""

import argparse
import asyncio
import asyncpg
import sys
import os
from typing import List, Dict, Any, Optional
import json
from datetime import datetime, date

# 프로젝트 루트 디렉터리를 Python 경로에 추가
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from autotrading.config.settings import settings


async def get_all_tables() -> List[str]:
    """데이터베이스의 모든 테이블 목록 조회"""
    conn = await asyncpg.connect(settings.database_url)

    tables = await conn.fetch("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)

    await conn.close()
    return [table['table_name'] for table in tables]


async def get_table_info(table_name: str) -> Dict[str, Any]:
    """테이블 정보 조회 (컬럼, 타입, 제약조건 등)"""
    conn = await asyncpg.connect(settings.database_url)

    # 컬럼 정보
    columns = await conn.fetch("""
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length
        FROM information_schema.columns
        WHERE table_name = $1
        ORDER BY ordinal_position
    """, table_name)

    # 행 수
    count = await conn.fetchval(f'SELECT COUNT(*) FROM {table_name}')

    # 인덱스 정보
    indexes = await conn.fetch("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = $1
    """, table_name)

    await conn.close()

    return {
        'columns': [dict(col) for col in columns],
        'row_count': count,
        'indexes': [dict(idx) for idx in indexes]
    }


async def query_table(table_name: str, limit: int = 20, offset: int = 0,
                     where: str = None, order_by: str = None) -> List[Dict[str, Any]]:
    """테이블 데이터 조회"""
    conn = await asyncpg.connect(settings.database_url)

    query = f"SELECT * FROM {table_name}"
    params = []

    if where:
        query += f" WHERE {where}"

    if order_by:
        query += f" ORDER BY {order_by}"
    else:
        # 기본 정렬 (created_at 또는 첫 번째 컬럼)
        table_info = await get_table_info(table_name)
        columns = [col['column_name'] for col in table_info['columns']]
        if 'created_at' in columns:
            query += " ORDER BY created_at DESC"
        elif 'updated_at' in columns:
            query += " ORDER BY updated_at DESC"
        elif columns:
            query += f" ORDER BY {columns[0]}"

    if limit:
        query += f" LIMIT {limit}"

    if offset:
        query += f" OFFSET {offset}"

    try:
        rows = await conn.fetch(query, *params)
        await conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        await conn.close()
        raise e


def format_value(value: Any, column_type: str = None) -> str:
    """값 포맷팅"""
    if value is None:
        return "NULL"

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")

    if isinstance(value, dict):
        return json.dumps(value, separators=(',', ':'))[:50] + "..." if len(str(value)) > 50 else json.dumps(value, separators=(',', ':'))

    if isinstance(value, (int, float)) and column_type and 'numeric' in column_type.lower():
        if isinstance(value, float):
            return f"{value:.2f}"

    # 긴 텍스트 자르기
    str_value = str(value)
    if len(str_value) > 50:
        return str_value[:47] + "..."

    return str_value


def print_table_list(tables: List[str]):
    """테이블 목록 출력"""
    print("AVAILABLE TABLES")
    print("=" * 40)
    for i, table in enumerate(tables, 1):
        print(f"{i:2d}. {table}")
    print()


def print_table_info(table_name: str, info: Dict[str, Any]):
    """테이블 정보 출력"""
    print(f"TABLE: {table_name.upper()}")
    print("=" * 60)
    print(f"Total Rows: {info['row_count']:,}")
    print()

    print("Columns:")
    print("-" * 60)
    print(f"{'Name':<20} {'Type':<15} {'Null':<5} {'Default':<15}")
    print("-" * 60)

    for col in info['columns']:
        name = col['column_name'][:20]
        data_type = col['data_type'][:15]
        nullable = "YES" if col['is_nullable'] == 'YES' else "NO"
        default = str(col['column_default'] or '')[:15]

        print(f"{name:<20} {data_type:<15} {nullable:<5} {default:<15}")

    if info['indexes']:
        print("\nIndexes:")
        print("-" * 60)
        for idx in info['indexes']:
            print(f"- {idx['indexname']}")

    print()


def print_table_data(table_name: str, data: List[Dict[str, Any]],
                    info: Dict[str, Any], limit: int, offset: int):
    """테이블 데이터 출력"""
    if not data:
        print(f"No data found in {table_name}")
        return

    print(f"DATA: {table_name.upper()}")
    if limit:
        print(f"Showing {len(data)} rows (limit: {limit}, offset: {offset})")
    print("=" * 100)

    # 컬럼 헤더
    columns = [col['column_name'] for col in info['columns']]
    display_columns = columns[:10]  # 최대 10개 컬럼만 표시

    # 컬럼 너비 계산
    col_widths = {}
    for col in display_columns:
        col_widths[col] = min(max(len(col), 8), 20)

    # 헤더 출력
    header = ""
    for col in display_columns:
        header += f"{col[:col_widths[col]]:<{col_widths[col]}} "
    print(header)
    print("-" * len(header))

    # 데이터 출력
    for row in data:
        line = ""
        for col in display_columns:
            value = format_value(row.get(col), None)
            line += f"{value[:col_widths[col]]:<{col_widths[col]}} "
        print(line)

    if len(columns) > 10:
        print(f"\n... and {len(columns) - 10} more columns")

    print()


async def main():
    parser = argparse.ArgumentParser(description="Database Table Viewer")
    parser.add_argument('table', nargs='?', help='Table name to view')
    parser.add_argument('--list', action='store_true', help='List all available tables')
    parser.add_argument('--info', action='store_true', help='Show table structure info')
    parser.add_argument('--limit', type=int, default=20, help='Number of rows to display (default: 20)')
    parser.add_argument('--offset', type=int, default=0, help='Number of rows to skip (default: 0)')
    parser.add_argument('--where', type=str, help='WHERE clause condition')
    parser.add_argument('--order', type=str, help='ORDER BY clause')
    parser.add_argument('--count', action='store_true', help='Show only row count')

    args = parser.parse_args()

    try:
        # 테이블 목록 조회
        tables = await get_all_tables()

        # 테이블 목록만 표시
        if args.list or not args.table:
            print_table_list(tables)
            if not args.table:
                print("Usage examples:")
                print("  python scripts/table_viewer.py tickers")
                print("  python scripts/table_viewer.py status --info")
                print("  python scripts/table_viewer.py candles --limit 10 --where \"symbol='AAPL'\"")
                return 0

        # 테이블 존재 확인
        if args.table not in tables:
            print(f"Error: Table '{args.table}' not found.")
            print("Available tables:")
            print_table_list(tables)
            return 1

        # 테이블 정보 조회
        table_info = await get_table_info(args.table)

        # 테이블 구조 정보만 표시
        if args.info:
            print_table_info(args.table, table_info)
            return 0

        # 행 수만 표시
        if args.count:
            where_clause = f" WHERE {args.where}" if args.where else ""
            conn = await asyncpg.connect(settings.database_url)
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {args.table}{where_clause}")
            await conn.close()
            print(f"{args.table}: {count:,} rows")
            return 0

        # 테이블 데이터 조회 및 표시
        data = await query_table(args.table, args.limit, args.offset, args.where, args.order)

        # 간단한 테이블 정보 표시
        print_table_info(args.table, table_info)

        # 데이터 표시
        print_table_data(args.table, data, table_info, args.limit, args.offset)

        # 페이징 정보
        if args.limit and len(data) == args.limit:
            print(f"Tip: Use --offset {args.offset + args.limit} to see more rows")

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)