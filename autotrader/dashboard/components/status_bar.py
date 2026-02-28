"""Status bar component for the live trading dashboard.

Renders a horizontal bar showing connection status, last update time,
market status, next scheduled event countdown, and last batch scan info.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import streamlit as st

from autotrader.dashboard.theme import COLORS
from autotrader.dashboard.utils.formatters import fmt_delta_time, fmt_pct


def render_status_bar(data, settings: dict) -> None:
    """Render the top status bar with system health and event countdown.

    Parameters
    ----------
    data:
        A DashboardData instance with at least ``last_update``,
        ``equity_df``, and ``current_equity`` fields.
    settings:
        Dict containing ``rotation_day`` (int, 5=Saturday),
        ``weekly_loss_limit_pct`` (float), ``max_open_positions`` (int),
        and optionally ``last_scan_timestamp`` (str ISO8601).
    """
    rotation_day = settings.get("rotation_day", 5)
    weekly_loss_limit_pct = settings.get("weekly_loss_limit_pct", 0.05)
    last_scan_ts = settings.get("last_scan_timestamp", "")

    col_conn, col_update, col_market, col_event, col_loss = st.columns(
        [1, 1, 1, 2, 2],
    )

    # -- 1. Connection status ------------------------------------------------
    with col_conn:
        last_update = getattr(data, "last_update", None)
        if last_update is not None and last_update != "":
            if isinstance(last_update, str):
                try:
                    last_update = datetime.fromisoformat(last_update)
                except ValueError:
                    last_update = None

        if last_update is not None:
            if last_update.tzinfo is None:
                last_update = last_update.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_update).total_seconds()
        else:
            elapsed = float("inf")

        if elapsed <= 120:
            dot_color = COLORS["profit"]
            label = "Connected"
        elif elapsed <= 600:
            dot_color = COLORS["warning"]
            label = "Delayed"
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
                f'<span style="color:{COLORS["text_muted"]}">No data yet</span>',
                unsafe_allow_html=True,
            )
        else:
            time_text = fmt_delta_time(elapsed)
            color = COLORS["warning"] if elapsed > 120 else COLORS["text_secondary"]
            st.markdown(
                f'<span style="color:{color}">Updated {time_text}</span>',
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
            status_text = "Weekend"
            status_color = COLORS["text_muted"]
        elif market_open_min <= time_minutes < market_close_min:
            status_text = "Market Open"
            status_color = COLORS["profit"]
        elif premarket_start_min <= time_minutes < market_open_min:
            status_text = "Pre-Market"
            status_color = COLORS["warning"]
        else:
            status_text = "After Hours"
            status_color = COLORS["text_muted"]

        st.markdown(
            f'<span style="color:{status_color};font-weight:600">'
            f"{status_text}</span>",
            unsafe_allow_html=True,
        )

    # -- 4. Next scheduled event (nightly scan / entry window) ---------------
    with col_event:
        event_text = _compute_next_event(now_utc)
        scan_text = ""
        if last_scan_ts:
            try:
                scan_dt = datetime.fromisoformat(last_scan_ts)
                if scan_dt.tzinfo is None:
                    scan_dt = scan_dt.replace(tzinfo=timezone.utc)
                scan_elapsed = (now_utc - scan_dt).total_seconds()
                scan_text = f" | Last scan: {fmt_delta_time(scan_elapsed)}"
            except (ValueError, TypeError):
                pass

        st.markdown(
            f'<span style="color:{COLORS["info"]};font-size:0.9em">'
            f"{event_text}{scan_text}</span>",
            unsafe_allow_html=True,
        )

    # -- 5. Weekly loss limit usage -----------------------------------------
    with col_loss:
        equity_df = getattr(data, "equity_df", None)
        current_equity = getattr(data, "current_equity", 0.0)

        usage = 0.0
        if equity_df is not None and not equity_df.empty and current_equity > 0:
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


def _compute_next_event(now_utc: datetime) -> str:
    """Compute a human-readable string for the next scheduled trading event.

    Events (all times in US Eastern, UTC offset -5/-4):
    - Nightly scan: weekday nights at 22:00 ET (03:00 UTC next day)
    - MOO entry window: 09:30 ET open
    - Confirmation entries: 10:00 ET
    - Portfolio review: 15:30 ET
    """
    # Convert UTC to approximate ET (simplified, ignoring DST edge cases)
    # ET is UTC-5 (EST) or UTC-4 (EDT). Use UTC-5 as conservative.
    et_offset_hours = 5
    now_et = now_utc - timedelta(hours=et_offset_hours)

    weekday = now_et.weekday()  # 0=Mon .. 6=Sun
    hour_et = now_et.hour
    minute_et = now_et.minute
    time_min_et = hour_et * 60 + minute_et

    # Define event times in ET minutes
    nightly_scan_min = 22 * 60        # 22:00
    moo_open_min = 9 * 60 + 30        # 09:30
    confirm_min = 10 * 60             # 10:00
    review_min = 15 * 60 + 30         # 15:30

    def _fmt_countdown(delta_min: int, label: str) -> str:
        if delta_min <= 0:
            return f"{label}: now"
        hours = delta_min // 60
        mins = delta_min % 60
        if hours > 0:
            return f"{label} in {hours}h {mins}m"
        return f"{label} in {mins}m"

    # Weekend: next event is Monday's nightly scan (Sunday night)
    if weekday >= 5:
        return "Next scan: Monday 22:00 ET"

    # Before market open
    if time_min_et < moo_open_min:
        if time_min_et >= nightly_scan_min - (24 * 60) and weekday == 0:
            # Monday before open -- no prior scan last night
            delta = moo_open_min - time_min_et
            return _fmt_countdown(delta, "MOO Window")
        delta = moo_open_min - time_min_et
        return _fmt_countdown(delta, "MOO Window")

    # After open, before confirm window
    if time_min_et < confirm_min:
        delta = confirm_min - time_min_et
        return _fmt_countdown(delta, "Confirm Window")

    # After confirm, before afternoon review
    if time_min_et < review_min:
        delta = review_min - time_min_et
        return _fmt_countdown(delta, "Portfolio Review")

    # After review: show nightly scan countdown
    if time_min_et < nightly_scan_min:
        delta = nightly_scan_min - time_min_et
        return _fmt_countdown(delta, "Nightly Scan")

    # After nightly scan: next event is tomorrow's MOO
    delta = (24 * 60 - time_min_et) + moo_open_min
    return _fmt_countdown(delta, "Tomorrow MOO")
