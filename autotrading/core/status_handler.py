"""
Status Handler

시스템 컴포넌트의 상태를 처리하고 관리하는 추상화 레이어입니다.
status 테이블을 통해 실시간 상태 추적과 헬스 체크 기능을 제공합니다.
"""

import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
from enum import Enum
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

import asyncpg

logger = logging.getLogger(__name__)


class ComponentState(Enum):
    """컴포넌트 상태 열거형"""
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    HEALTHY = "healthy"


class AlertLevel(Enum):
    """알람 레벨"""
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    STALE = "STALE"


@dataclass
class StatusInfo:
    """상태 정보 데이터 클래스"""
    name: str
    state: ComponentState
    details: Dict[str, Any]
    updated_at: datetime
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "name": self.name,
            "state": self.state.value,
            "details": self.details,
            "updated_at": self.updated_at.isoformat(),
            "created_at": self.created_at.isoformat()
        }


@dataclass
class AlertInfo:
    """알람 정보 데이터 클래스"""
    level: AlertLevel
    component: str
    issue: str
    timestamp: datetime
    details: Optional[Dict[str, Any]] = None


class StatusHandler:
    """
    시스템 상태 처리 클래스

    status 테이블을 통해 컴포넌트 상태를 관리하고
    실시간 모니터링 및 알람 기능을 제공합니다.
    """

    def __init__(self, database_pool: asyncpg.Pool):
        """
        StatusHandler 초기화

        Args:
            database_pool: 데이터베이스 연결 풀
        """
        self.database_pool = database_pool
        self.logger = logging.getLogger(__name__)

        # 알람 임계값 설정
        self.alert_thresholds = {
            "stale_minutes": 30,
            "critical_error_minutes": 5,
            "max_failure_rate": 15
        }

    async def update_status(
        self,
        component_name: str,
        state: Union[ComponentState, str],
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        컴포넌트 상태 업데이트

        Args:
            component_name: 컴포넌트 이름
            state: 새로운 상태
            details: 추가 상태 정보

        Returns:
            업데이트 성공 여부
        """
        try:
            if isinstance(state, str):
                state = ComponentState(state)

            details = details or {}

            query = """
                INSERT INTO status (name, state, updated_at, details)
                VALUES ($1, $2, NOW(), $3)
                ON CONFLICT (name)
                DO UPDATE SET
                    state = EXCLUDED.state,
                    updated_at = NOW(),
                    details = status.details || EXCLUDED.details
            """

            async with self.database_pool.acquire() as conn:
                await conn.execute(query, component_name, state.value, json.dumps(details))

            self.logger.debug(f"Status updated: {component_name} -> {state.value}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to update status for {component_name}: {e}")
            return False

    async def get_status(self, component_name: str) -> Optional[StatusInfo]:
        """
        특정 컴포넌트 상태 조회

        Args:
            component_name: 컴포넌트 이름

        Returns:
            상태 정보 또는 None
        """
        try:
            query = """
                SELECT name, state, updated_at, details, created_at
                FROM status
                WHERE name = $1
            """

            async with self.database_pool.acquire() as conn:
                row = await conn.fetchrow(query, component_name)

                if row:
                    return StatusInfo(
                        name=row['name'],
                        state=ComponentState(row['state']),
                        details=row['details'] or {},
                        updated_at=row['updated_at'],
                        created_at=row['created_at']
                    )

            return None

        except Exception as e:
            self.logger.error(f"Failed to get status for {component_name}: {e}")
            return None

    async def get_all_statuses(self) -> List[StatusInfo]:
        """
        모든 컴포넌트 상태 조회

        Returns:
            상태 정보 리스트
        """
        try:
            query = """
                SELECT name, state, updated_at, details, created_at
                FROM status
                ORDER BY updated_at DESC
            """

            async with self.database_pool.acquire() as conn:
                rows = await conn.fetch(query)

                return [
                    StatusInfo(
                        name=row['name'],
                        state=ComponentState(row['state']),
                        details=row['details'] or {},
                        updated_at=row['updated_at'],
                        created_at=row['created_at']
                    )
                    for row in rows
                ]

        except Exception as e:
            self.logger.error(f"Failed to get all statuses: {e}")
            return []

    async def health_check_all(self) -> Dict[str, Any]:
        """
        전체 시스템 헬스 체크

        Returns:
            전체 시스템 상태 정보
        """
        try:
            query = """
                SELECT
                    name,
                    state,
                    updated_at,
                    EXTRACT(EPOCH FROM (NOW() - updated_at))/60 as minutes_since_update,
                    details,
                    CASE
                        WHEN state = 'error' THEN 'CRITICAL'
                        WHEN state IN ('stopped', 'initialized') THEN 'WARNING'
                        WHEN EXTRACT(EPOCH FROM (NOW() - updated_at))/60 > $1 THEN 'STALE'
                        ELSE 'OK'
                    END as health_status
                FROM status
                ORDER BY
                    CASE state
                        WHEN 'error' THEN 1
                        WHEN 'stopped' THEN 2
                        WHEN 'initialized' THEN 3
                        ELSE 4
                    END,
                    updated_at DESC
            """

            async with self.database_pool.acquire() as conn:
                rows = await conn.fetch(query, self.alert_thresholds["stale_minutes"])

                components = []
                overall_health = "OK"

                for row in rows:
                    component_info = {
                        "name": row['name'],
                        "state": row['state'],
                        "health_status": row['health_status'],
                        "minutes_since_update": float(row['minutes_since_update']),
                        "details": row['details'] or {}
                    }
                    components.append(component_info)

                    # 전체 상태 결정
                    if row['health_status'] == 'CRITICAL' and overall_health != 'CRITICAL':
                        overall_health = 'CRITICAL'
                    elif row['health_status'] == 'WARNING' and overall_health in ['OK']:
                        overall_health = 'WARNING'

                return {
                    "overall_health": overall_health,
                    "total_components": len(components),
                    "healthy_components": len([c for c in components if c["health_status"] == "OK"]),
                    "components": components,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {
                "overall_health": "CRITICAL",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    async def get_alerts(self) -> List[AlertInfo]:
        """
        현재 활성 알람 조회

        Returns:
            알람 정보 리스트
        """
        alerts = []

        try:
            # 긴급 상황 (에러 상태)
            critical_query = """
                SELECT name, state, updated_at, details
                FROM status
                WHERE state = 'error'
                    AND updated_at > NOW() - INTERVAL '%s minutes'
            """ % self.alert_thresholds["critical_error_minutes"]

            # 경고 상황 (오래된 업데이트)
            warning_query = """
                SELECT name, state, updated_at, details,
                       EXTRACT(EPOCH FROM (NOW() - updated_at))/60 as minutes_stale
                FROM status
                WHERE EXTRACT(EPOCH FROM (NOW() - updated_at))/60 > $1
                   OR state IN ('stopped', 'initialized')
            """

            async with self.database_pool.acquire() as conn:
                # 긴급 알람
                critical_rows = await conn.fetch(critical_query)
                for row in critical_rows:
                    alerts.append(AlertInfo(
                        level=AlertLevel.CRITICAL,
                        component=row['name'],
                        issue=f"Component in error state: {row['state']}",
                        timestamp=row['updated_at'],
                        details=row['details']
                    ))

                # 경고 알람
                warning_rows = await conn.fetch(warning_query, self.alert_thresholds["stale_minutes"])
                for row in warning_rows:
                    if row['state'] in ['stopped', 'initialized']:
                        issue = f"Component in {row['state']} state"
                    else:
                        issue = f"No updates for {int(row['minutes_stale'])} minutes"

                    alerts.append(AlertInfo(
                        level=AlertLevel.WARNING,
                        component=row['name'],
                        issue=issue,
                        timestamp=row['updated_at'],
                        details=row['details']
                    ))

        except Exception as e:
            self.logger.error(f"Failed to get alerts: {e}")
            alerts.append(AlertInfo(
                level=AlertLevel.CRITICAL,
                component="status_monitor",
                issue=f"Alert system error: {str(e)}",
                timestamp=datetime.now(timezone.utc)
            ))

        return alerts

    async def set_component_error(
        self,
        component_name: str,
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        컴포넌트 에러 상태 설정

        Args:
            component_name: 컴포넌트 이름
            error_message: 에러 메시지
            error_details: 추가 에러 정보

        Returns:
            업데이트 성공 여부
        """
        details = {
            "error_message": error_message,
            "error_time": datetime.now(timezone.utc).isoformat(),
            **(error_details or {})
        }

        return await self.update_status(component_name, ComponentState.ERROR, details)

    @asynccontextmanager
    async def component_context(self, component_name: str, details: Optional[Dict[str, Any]] = None):
        """
        컴포넌트 실행 컨텍스트 매니저

        자동으로 상태를 관리하며, 예외 발생 시 에러 상태로 설정합니다.

        Args:
            component_name: 컴포넌트 이름
            details: 초기 상태 정보

        Usage:
            async with handler.component_context("data_collector") as ctx:
                # 컴포넌트 작업 수행
                ctx.update_details({"processed": 100})
        """
        class ComponentContext:
            def __init__(self, handler: StatusHandler, name: str):
                self.handler = handler
                self.name = name
                self.details = details or {}

            async def update_details(self, new_details: Dict[str, Any]):
                """상태 세부사항 업데이트"""
                self.details.update(new_details)
                await self.handler.update_status(self.name, ComponentState.RUNNING, self.details)

            async def set_state(self, state: ComponentState, details: Optional[Dict[str, Any]] = None):
                """상태 직접 설정"""
                if details:
                    self.details.update(details)
                await self.handler.update_status(self.name, state, self.details)

        context = ComponentContext(self, component_name)

        try:
            # 시작 상태 설정
            await self.update_status(component_name, ComponentState.RUNNING, details)
            yield context

        except Exception as e:
            # 에러 발생 시 에러 상태로 설정
            await self.set_component_error(component_name, str(e))
            raise

        finally:
            # 정상 종료 시 완료 상태로 설정 (선택적)
            pass


class StatusDashboard:
    """
    상태 모니터링 대시보드

    StatusHandler를 기반으로 사용자 친화적인 상태 표시 기능을 제공합니다.
    """

    def __init__(self, status_handler: StatusHandler):
        self.handler = status_handler

    async def get_dashboard_data(self) -> Dict[str, Any]:
        """대시보드용 데이터 수집"""
        health_check = await self.handler.health_check_all()
        alerts = await self.handler.get_alerts()

        return {
            "health_check": health_check,
            "alerts": [asdict(alert) for alert in alerts],
            "summary": {
                "total_alerts": len(alerts),
                "critical_alerts": len([a for a in alerts if a.level == AlertLevel.CRITICAL]),
                "warning_alerts": len([a for a in alerts if a.level == AlertLevel.WARNING])
            }
        }

    def format_status_table(self, statuses: List[StatusInfo]) -> str:
        """상태 정보를 테이블 형태로 포맷"""
        if not statuses:
            return "📊 No components found"

        lines = ["📊 System Status Dashboard", "=" * 60]

        for status in statuses:
            state_emoji = {
                ComponentState.RUNNING: "🟢",
                ComponentState.HEALTHY: "🟢",
                ComponentState.INITIALIZED: "🟡",
                ComponentState.STOPPED: "🔴",
                ComponentState.ERROR: "🚨"
            }.get(status.state, "⚫")

            lines.append(f"{state_emoji} {status.name:<20} | {status.state.value:<12} | {status.updated_at.strftime('%H:%M:%S')}")

            # 중요한 세부사항만 표시
            if status.details:
                for key, value in status.details.items():
                    if key in ['error_message', 'last_action', 'active_symbols', 'failed_updates']:
                        lines.append(f"   └── {key}: {value}")

        return "\n".join(lines)

    def format_alerts_summary(self, alerts: List[AlertInfo]) -> str:
        """알람 요약 포맷"""
        if not alerts:
            return "✅ No active alerts"

        lines = ["🚨 Active Alerts", "=" * 30]

        critical = [a for a in alerts if a.level == AlertLevel.CRITICAL]
        warnings = [a for a in alerts if a.level == AlertLevel.WARNING]

        if critical:
            lines.append(f"🚨 CRITICAL ({len(critical)}):")
            for alert in critical:
                lines.append(f"   • {alert.component}: {alert.issue}")

        if warnings:
            lines.append(f"⚠️ WARNING ({len(warnings)}):")
            for alert in warnings:
                lines.append(f"   • {alert.component}: {alert.issue}")

        return "\n".join(lines)