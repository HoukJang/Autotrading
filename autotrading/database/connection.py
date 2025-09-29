"""
Database connection management

PostgreSQL 연결 풀을 관리하고 데이터베이스 연결을 제공합니다.
"""

import asyncio
import logging
from typing import Any, Dict, Optional
import asyncpg
from asyncpg import Pool

logger = logging.getLogger(__name__)


async def create_db_pool(database_url: str, **kwargs) -> Pool:
    """
    PostgreSQL 연결 풀 생성

    Args:
        database_url: PostgreSQL 연결 URL
        **kwargs: 추가 연결 옵션

    Returns:
        AsyncPG 연결 풀

    Raises:
        Exception: 데이터베이스 연결 실패 시
    """
    try:
        # 기본 연결 설정
        pool_kwargs = {
            'min_size': 2,
            'max_size': 10,
            'command_timeout': 60,
            **kwargs
        }

        logger.info(f"Creating database pool with URL: {database_url[:20]}...")
        pool = await asyncpg.create_pool(database_url, **pool_kwargs)

        # 연결 테스트
        async with pool.acquire() as conn:
            await conn.fetchval('SELECT 1')

        logger.info("Database pool created successfully")
        return pool

    except Exception as e:
        logger.error(f"Failed to create database pool: {e}")
        raise


async def close_db_pool(pool: Pool) -> None:
    """
    데이터베이스 연결 풀 정리

    Args:
        pool: 정리할 연결 풀
    """
    try:
        await pool.close()
        logger.info("Database pool closed")
    except Exception as e:
        logger.error(f"Error closing database pool: {e}")


async def execute_query(pool: Pool, query: str, *args) -> Any:
    """
    쿼리 실행

    Args:
        pool: 데이터베이스 연결 풀
        query: 실행할 쿼리
        *args: 쿼리 파라미터

    Returns:
        쿼리 결과
    """
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *args)


async def execute_many(pool: Pool, query: str, args_list: list) -> None:
    """
    여러 쿼리 배치 실행

    Args:
        pool: 데이터베이스 연결 풀
        query: 실행할 쿼리
        args_list: 쿼리 파라미터 리스트
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(query, args_list)