"""Status bar component for the live trading dashboard.

Renders a horizontal bar showing connection status, last update time,
market status, next rotation countdown, and weekly loss limit usage.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import streamlit as st

from autotrader.dashboard.theme import COLORS
from autotrader.dashboard.utils.formatters import fmt_delta_time, fmt_pct


def render_status_bar(data, settings: dict) -> None:
    """Render the top status bar with 5 information elements.

    Parameters
    ----------
    data:
        A DashboardData (or LiveDashboardData) instance with at least
        ``last_update``, ``equity_df``, and ``current_equity`` fields.
    settings:
        Dict containing ``rotation_day`` (int, 5=Saturday),
        ``weekly_loss_limit_pct`` (float), and ``max_open_positions`` (int).
    """
    rotation_day = settings.get("rotation_day", 5)
    weekly_loss_limit_pct = settings.get("weekly_loss_limit_pct", 0.05)

    col_conn, col_update, col_market, col_rotation, col_loss = st.columns(
        [1, 1, 1, 1, 2],
    )

    # -- 1. Connection status ------------------------------------------------
    with col_conn:
        last_update = getattr(data, "last_update", None)
        if last_update is not None and last_update != "":
            if isinstance(last_update, str):
                last_update = datetime.fromisoformat(last_update)
            if last_update.tzinfo is None:
                last_update = last_update.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_update).total_seconds()
        else:
            elapsed = float("inf")

        if elapsed <= 120:
            dot_color = COLORS["profit"]
            label = "Connected"
        else:
            dot_color = COLORS["loss"]
            label = "No data"

        st.markdown(
            f'<span style="color:{dot_color};font-size:1.1em">'
            f"&#9679;</span> **{label}**",
            unsafe_allow_html=True,
        )

    # -- 2. Last update ------------------------------------------------------
    with col_update:
        if elapsed == float("inf"):
            st.markdown(
                f'<span style="color:{COLORS["text_muted"]}">--</span>',
                unsafe_allow_html=True,
            )
        else:
            time_text = fmt_delta_time(elapsed)
            color = COLORS["warning"] if elapsed > 120 else COLORS["text_secondary"]
            st.markdown(
                f'<span style="color:{color}">{time_text}</span>',
                unsafe_allow_html=True,
            )

    # -- 3. Market status ----------------------------------------------------
    with col_market:
        now_utc = datetime.now(timezone.utc)
        weekday = now_utc.weekday()  # 0=Mon .. 6=Sun
        hour_utc = now_utc.hour
        minute_utc = now_utc.minute
        time_minutes = hour_utc * 60 + minute_utc

        # US market hours in UTC: 13:30 (810min) to 20:00 (1200min)
        market_open_min = 13 * 60 + 30   # 810
        market_close_min = 20 * 60        # 1200
        premarket_start_min = 9 * 60      # 540 (04:00 ET)

        if weekday >= 5:
            status_text = "Market Closed"
            status_color = COLORS["text_muted"]
        elif market_open_min <= time_minutes < market_close_min:
            status_text = "Market Open"
            status_color = COLORS["profit"]
        elif premarket_start_min <= time_minutes < market_open_min:
            status_text = "Pre-Market"
            status_color = COLORS["warning"]
        else:
            status_text = "Market Closed"
            status_color = COLORS["text_muted"]

        st.markdown(
            f'<span style="color:{status_color};font-weight:600">'
            f"{status_text}</span>",
            unsafe_allow_html=True,
        )

    # -- 4. Next rotation ----------------------------------------------------
    with col_rotation:
        today = datetime.now(timezone.utc).date()
        today_weekday = today.weekday()  # 0=Mon .. 6=Sun
        days_ahead = (rotation_day - today_weekday) % 7
        if days_ahead == 0:
            # If today is rotation day, show 0d or next week depending on time
            next_rotation_date = today
            rotation_dt = datetime.combine(
                next_rotation_date, datetime.min.time(),
            ).replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= rotation_dt + timedelta(hours=16):
                days_ahead = 7
                next_rotation_date = today + timedelta(days=days_ahead)
        else:
            next_rotation_date = today + timedelta(days=days_ahead)

        delta = datetime.combine(
            next_rotation_date, datetime.min.time(),
        ).replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
        total_hours = max(0, int(delta.total_seconds() // 3600))
        remaining_days = total_hours // 24
        remaining_hours = total_hours % 24

        st.markdown(
            f'<span style="color:{COLORS["text_secondary"]}">'
            f"Next rotation: {remaining_days}d {remaining_hours}h</span>",
            unsafe_allow_html=True,
        )

    # -- 5. Weekly loss limit ------------------------------------------------
    with col_loss:
        equity_df = getattr(data, "equity_df", None)
        current_equity = getattr(data, "current_equity", 0.0)

        usage = 0.0
        if equity_df is not None and not equity_df.empty and current_equity > 0:
            # Find equity at start of this week (Monday)
            today_date = datetime.now(timezone.utc).date()
            monday = today_date - timedelta(days=today_date.weekday())
            monday_dt = datetime.combine(monday, datetime.min.time())

            if "timestamp" in equity_df.columns:
                ts_col = equity_df["timestamp"]
                if hasattr(ts_col.dtype, "tz") or str(ts_col.dtype).startswith(
                    "datetime64",
                ):
                    week_data = equity_df[ts_col >= str(monday_dt)]
                else:
                    week_data = equity_df

                if not week_data.empty:
                    start_equity = float(week_data.iloc[0]["equity"])
                    if start_equity > 0:
                        loss_pct = max(
                            0.0, (start_equity - current_equity) / start_equity,
                        )
                        usage = min(1.0, loss_pct / weekly_loss_limit_pct)

        # Display progress bar with label
        limit_pct_display = fmt_pct(weekly_loss_limit_pct)
        usage_pct_display = fmt_pct(usage * weekly_loss_limit_pct)

        if usage >= 0.8:
            label_color = COLORS["loss"]
        elif usage >= 0.5:
            label_color = COLORS["warning"]
        else:
            label_color = COLORS["profit"]

        st.markdown(
            f'<span style="color:{COLORS["text_secondary"]};font-size:0.85em">'
            f"Weekly Loss: "
            f'<span style="color:{label_color}">{usage_pct_display}</span>'
            f" / {limit_pct_display}</span>",
            unsafe_allow_html=True,
        )
        st.progress(usage)
