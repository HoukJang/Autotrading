"""Nightly scan results component for the trading dashboard (Tab 2).

Renders the latest batch scan summary, candidate table with color coding
by entry group, and a score distribution histogram.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from autotrader.dashboard.theme import COLORS, STRATEGY_NAMES
from autotrader.dashboard.utils.chart_helpers import get_chart_layout
from autotrader.trading.constants import (
    MAX_PORTFOLIO_HEAT_PCT,
    RISK_PER_TRADE_PCT,
    SL_ATR_MULT,
)


# Entry group color mapping
_ENTRY_GROUP_COLORS = {
    "MOO": COLORS["profit"],        # Green for market-on-open
    "Confirm": COLORS["info"],      # Blue for confirmation entries
    "CONFIRM": COLORS["info"],
}

# Unified status badge colors (lifecycle: SCANNED -> PASSED/FILTERED/SKIPPED, HELD)
_STATUS_COLORS = {
    "scanned": COLORS["warning"],     # yellow - gap check pending
    "passed": COLORS["profit"],       # green - gap OK
    "filtered": COLORS["loss"],       # red - gap too large
    "skipped": COLORS["neutral"],     # gray - outside market hours
    "held": COLORS["warning"],        # orange-ish - already held
    "entered": COLORS["profit"],      # green - MOO entry executed
    "blocked": COLORS["loss"],        # red - entry blocked by constraint
}

# Friendly labels for entry_block_reason values from the entry checker
_BLOCK_REASON_LABELS: dict[str, str] = {
    "portfolio heat limit": "Exposure limit reached",
    "strategy position cap": "Strategy full",
    "max long positions": "Long limit reached",
    "max short positions": "Short limit reached",
    "total position cap": "Position limit reached",
    "daily entry limit": "Daily entries maxed",
    "re-entry block": "Re-entry blocked today",
    "duplicate symbol": "Already held",
    "gdr strategy entry limit": "GDR limit",
    "safety net entry limit": "Safety net active",
}


def render_scan_results(batch_data, dashboard_data=None) -> None:
    """Render the nightly scan results tab.

    Displays scan summary KPIs, a sortable candidates table with color
    coding by entry group, and a score distribution histogram.

    Parameters
    ----------
    batch_data:
        A BatchScanData instance with scan_timestamp, total_scanned,
        signals_generated, candidates_df, and all_scores fields.
    """
    if batch_data is None:
        st.info("No scan results yet. The nightly scan runs automatically at 10 PM ET.")
        return

    scan_ts = getattr(batch_data, "scan_timestamp", "")
    total_scanned = getattr(batch_data, "total_scanned", 0)
    signals_generated = getattr(batch_data, "signals_generated", 0)
    candidates_df = getattr(batch_data, "candidates_df", pd.DataFrame())
    all_scores = getattr(batch_data, "all_scores", [])

    # -- Error banner (shown when the scan reported errors) --------------------
    raw = getattr(batch_data, "raw", {}) or {}
    scan_errors = raw.get("errors", [])
    if scan_errors:
        _render_scan_error_banner(scan_errors, scan_ts)

    if not scan_ts and total_scanned == 0:
        st.info("No batch scan data found. Nightly scan has not run yet.")
        _render_empty_scan_placeholder()
        return

    # -- Scan summary KPIs --------------------------------------------------
    _render_scan_summary(scan_ts, total_scanned, signals_generated, candidates_df)

    st.divider()

    # -- Portfolio exposure gauge -------------------------------------------
    _render_exposure_gauge(dashboard_data)

    # -- Candidates table ---------------------------------------------------
    st.subheader("Top Candidates")
    if candidates_df.empty:
        st.info("No trading opportunities found in the latest scan. The system will check again tonight.")
    else:
        # Collect held symbols from dashboard state and open_positions.json
        held_symbols: set[str] = set()
        if dashboard_data is not None:
            held_symbols.update(getattr(dashboard_data, "current_positions", []))
        from autotrader.dashboard.data_loader import load_open_positions
        held_symbols.update(load_open_positions().keys())

        _render_candidates_table(candidates_df, held_symbols=held_symbols)

    st.divider()

    # -- Score distribution histogram ---------------------------------------
    if all_scores:
        _render_score_distribution(all_scores, candidates_df)
    else:
        st.caption("Score distribution data not available.")

    # -- Risk preview for candidates ----------------------------------------
    if dashboard_data is not None and not candidates_df.empty:
        st.divider()
        _render_risk_preview(candidates_df, dashboard_data)


def _render_empty_scan_placeholder() -> None:
    """Render a placeholder explaining the nightly batch scan flow."""
    st.markdown(
        """
        <div class="at-empty">
            <div class="at-empty-title">Tonight's scan hasn't run yet</div>
            <div class="at-empty-desc">
                The system scans all S&P 500 stocks automatically at 10 PM ET on weekdays.<br>
                Results appear here after the scan completes.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# Known error codes -> beginner-friendly explanations
_ERROR_FRIENDLY_MESSAGES: dict[str, str] = {
    "insufficient_data": (
        "Not enough market data was available. "
        "The scanner needs data from at least 10 stocks."
    ),
}


def _render_scan_error_banner(
    errors: list[dict],
    scan_ts: str,
) -> None:
    """Show a prominent error banner when the nightly scan had errors.

    Parameters
    ----------
    errors:
        List of error dicts, each with at least ``"error"`` and optionally
        ``"symbol"`` keys.
    scan_ts:
        ISO-formatted scan timestamp for display.
    """
    ts_display = _format_scan_timestamp(scan_ts) if scan_ts else "unknown time"

    # Build detail lines from each error entry
    detail_lines: list[str] = []
    for err in errors:
        code = err.get("error", "unknown_error") if isinstance(err, dict) else str(err)
        friendly = _ERROR_FRIENDLY_MESSAGES.get(code, code)
        detail_lines.append(f"- {friendly}")

    details = "\n".join(detail_lines)

    st.error(
        f"**Last scan encountered errors** (scan time: {ts_display})\n\n{details}",
        icon=None,
    )


def _render_scan_summary(
    scan_ts: str,
    total_scanned: int,
    signals_generated: int,
    candidates_df: pd.DataFrame,
) -> None:
    """Render the scan summary KPI row."""
    col_ts, col_scanned, col_signals, col_selected = st.columns(4)

    with col_ts:
        ts_display = _format_scan_timestamp(scan_ts)
        st.metric("Last Scan", ts_display)

    with col_scanned:
        st.metric("Stocks Checked", f"{total_scanned:,}")

    with col_signals:
        st.metric("Signals Generated", str(signals_generated))

    with col_selected:
        selected_count = len(candidates_df) if not candidates_df.empty else 0
        moo_count = 0
        confirm_count = 0
        if not candidates_df.empty and "entry_group" in candidates_df.columns:
            moo_count = int((candidates_df["entry_group"].str.upper() == "MOO").sum())
            confirm_count = selected_count - moo_count

        delta_text = f"{moo_count} At Open | {confirm_count} 10 AM Check"
        st.metric("Ready to Trade", str(selected_count), delta=delta_text)


def _render_exposure_gauge(dashboard_data) -> None:
    """Render a horizontal progress bar showing current portfolio exposure.

    Computes exposure as sum(abs(market_value)) / equity from open
    positions data, displayed against the MAX_PORTFOLIO_HEAT_PCT limit.
    Color coding: green (0-50%), yellow (50-75%), red (75-100% of limit).
    """
    if dashboard_data is None:
        return

    equity = getattr(dashboard_data, "current_equity", 0.0)
    if equity <= 0:
        return

    # Compute exposure from open positions
    from autotrader.dashboard.data_loader import load_open_positions
    open_positions = load_open_positions()

    total_market_value = 0.0
    for pos in open_positions.values():
        qty = abs(pos.get("qty", 0))
        price = pos.get("current_price") or pos.get("entry_price", 0)
        total_market_value += qty * price

    exposure_pct = total_market_value / equity if equity > 0 else 0.0
    limit_pct = MAX_PORTFOLIO_HEAT_PCT

    # Fraction of the limit consumed (0.0 to 1.0+)
    usage_fraction = exposure_pct / limit_pct if limit_pct > 0 else 0.0
    bar_width = min(usage_fraction * 100, 100)

    # Color by usage fraction: green < 50%, yellow 50-75%, red >= 75%
    if usage_fraction < 0.50:
        bar_color = COLORS["profit"]
    elif usage_fraction < 0.75:
        bar_color = COLORS["warning"]
    else:
        bar_color = COLORS["loss"]

    display_pct = exposure_pct * 100
    limit_display = limit_pct * 100

    st.markdown(
        f'<div style="background:{COLORS["bg_card"]};border-radius:8px;'
        f'padding:14px 18px;margin-bottom:8px">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'margin-bottom:6px">'
        f'<span style="color:{COLORS["text_primary"]};font-weight:600;font-size:0.95em">'
        f'Portfolio Exposure: {display_pct:.1f}% / {limit_display:.0f}%</span>'
        f'<span style="color:{COLORS["text_muted"]};font-size:0.8em">'
        f'How much of your capital is invested</span>'
        f'</div>'
        f'<div style="background:{COLORS["bg_section"]};border-radius:4px;'
        f'height:12px;overflow:hidden">'
        f'<div style="background:{bar_color};width:{bar_width:.1f}%;'
        f'height:100%;border-radius:4px;transition:width 0.3s ease"></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_candidates_table(
    candidates_df: pd.DataFrame,
    held_symbols: set[str] | None = None,
) -> None:
    """Render the sortable, color-coded candidates table."""
    df = candidates_df.copy()

    # Normalize column presence
    expected_cols = [
        "rank", "symbol", "status", "strategy", "direction", "score",
        "entry_group", "est_qty", "est_size",
        "sl_price", "tp_price", "atr",
    ]

    # Build unified Status column:
    # Priority: HELD > ENTERED/BLOCKED > FILTERED > SKIPPED > PASSED > SCANNED
    gap_status_series = df.get("gap_filter_status", pd.Series("", index=df.index))
    gap_pct_series = pd.to_numeric(df.get("gap_pct", pd.Series(dtype=float)), errors="coerce")
    entry_status_series = df.get("entry_status", pd.Series("", index=df.index))
    block_reason_series = df.get("entry_block_reason", pd.Series("", index=df.index))

    def _compute_status(row_idx):
        sym = df["symbol"].iloc[row_idx] if "symbol" in df.columns else ""
        if held_symbols and sym in held_symbols:
            return "HELD"

        # Post-MOO entry status (takes priority over gap filter)
        entry_val = str(entry_status_series.iloc[row_idx]).lower().strip() if row_idx < len(entry_status_series) else ""
        if entry_val == "entered":
            return "ENTERED"
        if entry_val == "blocked":
            raw_reason = str(block_reason_series.iloc[row_idx]).strip() if row_idx < len(block_reason_series) else ""
            friendly = _BLOCK_REASON_LABELS.get(raw_reason, raw_reason) if raw_reason else ""
            return f"BLOCKED ({friendly})" if friendly else "BLOCKED"

        gap_val = str(gap_status_series.iloc[row_idx]).lower().strip() if row_idx < len(gap_status_series) else ""
        gap_pct_val = gap_pct_series.iloc[row_idx] if row_idx < len(gap_pct_series) else None
        has_pct = pd.notna(gap_pct_val)
        if gap_val == "filtered":
            return f"FILTERED ({gap_pct_val:.1f}%)" if has_pct else "FILTERED"
        elif gap_val == "skipped":
            return "SKIPPED"
        elif gap_val == "passed":
            return f"PASSED ({gap_pct_val:.1f}%)" if has_pct else "PASSED"
        else:
            return "SCANNED"

    df["status"] = [_compute_status(i) for i in range(len(df))]

    for col in expected_cols:
        if col not in df.columns:
            df[col] = "--"

    # Compute estimated position size from risk model:
    # qty = floor(equity * risk_pct / (sl_mult * atr))
    # size = qty * prev_close
    _ESTIMATE_EQUITY = 100_000  # default equity assumption for display
    _raw_atr = pd.to_numeric(candidates_df.get("atr", pd.Series(dtype=float)), errors="coerce")
    _raw_prev = pd.to_numeric(candidates_df.get("prev_close", pd.Series(dtype=float)), errors="coerce")
    _raw_strat = candidates_df.get("strategy", pd.Series(dtype=str))
    _raw_dir = candidates_df.get("direction", pd.Series(dtype=str))

    est_qty_list = []
    est_size_list = []
    for i in range(len(df)):
        atr_val = _raw_atr.iloc[i] if i < len(_raw_atr) else None
        prev_val = _raw_prev.iloc[i] if i < len(_raw_prev) else None
        strat = str(_raw_strat.iloc[i]) if i < len(_raw_strat) else ""
        dirn = str(_raw_dir.iloc[i]).lower() if i < len(_raw_dir) else "long"

        if pd.notna(atr_val) and atr_val > 0:
            sl_mult = SL_ATR_MULT.get(strat, {}).get(dirn, 2.0)
            risk_per_share = sl_mult * atr_val
            qty = int(_ESTIMATE_EQUITY * RISK_PER_TRADE_PCT / risk_per_share)
            est_qty_list.append(str(qty))
            if pd.notna(prev_val) and prev_val > 0:
                est_size_list.append(f"${qty * prev_val:,.0f}")
            else:
                est_size_list.append("--")
        else:
            est_qty_list.append("--")
            est_size_list.append("--")

    df["est_qty"] = est_qty_list
    df["est_size"] = est_size_list

    # Map strategy keys to display names
    if "strategy" in df.columns:
        df["strategy"] = df["strategy"].map(
            lambda s: STRATEGY_NAMES.get(str(s), str(s))
        )

    # Format numeric columns
    if "score" in df.columns:
        df["score"] = pd.to_numeric(df["score"], errors="coerce").map(
            lambda v: f"{v:.3f}" if pd.notna(v) else "--"
        )
    if "sl_price" in df.columns:
        df["sl_price"] = pd.to_numeric(df["sl_price"], errors="coerce").map(
            lambda v: f"${v:,.2f}" if pd.notna(v) else "--"
        )
    if "tp_price" in df.columns:
        df["tp_price"] = pd.to_numeric(df["tp_price"], errors="coerce").map(
            lambda v: f"${v:,.2f}" if pd.notna(v) else "--"
        )
    if "atr" in df.columns:
        df["atr"] = pd.to_numeric(df["atr"], errors="coerce").map(
            lambda v: f"{v:.2f}" if pd.notna(v) else "--"
        )

    # Rename Entry Group values for beginner-friendly display
    if "entry_group" in df.columns:
        df["entry_group"] = df["entry_group"].map(
            lambda v: "At Open" if str(v).upper() == "MOO"
            else ("10 AM Check" if str(v).upper() in ("CONFIRM", "CONFIRMATION") else v)
        )

    # Toggle between basic and detail views
    show_details = st.toggle("Show all columns", value=False, key="scan_detail_toggle")

    # Rename for display
    all_display = df[expected_cols].rename(columns={
        "rank": "Rank",
        "symbol": "Symbol",
        "status": "Status",
        "strategy": "Strategy",
        "direction": "Direction",
        "score": "Score",
        "entry_group": "Entry Group",
        "est_qty": "Est.Qty",
        "est_size": "Est.Size",
        "sl_price": "SL",
        "tp_price": "TP",
        "atr": "ATR",
    })

    if show_details:
        display = all_display
    else:
        basic_cols = ["Rank", "Symbol", "Strategy", "Direction", "Score", "Entry Group", "Status"]
        display = all_display[basic_cols]

    # Determine the direction column name in the current view
    dir_col = "Direction"

    def _style_candidates(row: pd.Series) -> list[str]:
        styles = [""] * len(row)
        if "Entry Group" in row.index:
            idx = row.index.get_loc("Entry Group")
            group = str(row["Entry Group"]).upper()
            if group == "AT OPEN":
                styles[idx] = f"background-color: {COLORS['profit']}22; color: {COLORS['profit']}; font-weight: bold"
            elif group in ("10 AM CHECK",):
                styles[idx] = f"background-color: {COLORS['info']}22; color: {COLORS['info']}; font-weight: bold"

        if dir_col in row.index:
            idx = row.index.get_loc(dir_col)
            direction = str(row[dir_col]).lower()
            if direction in ("long", "buy"):
                styles[idx] = f"color: {COLORS['profit']}"
            elif direction in ("short", "sell"):
                styles[idx] = f"color: {COLORS['loss']}"

        if "Status" in row.index:
            idx = row.index.get_loc("Status")
            status_val = str(row["Status"]).upper()
            # Match by prefix keyword since PASSED/FILTERED may have gap% appended
            for keyword, color in _STATUS_COLORS.items():
                if status_val.startswith(keyword.upper()):
                    styles[idx] = (
                        f"background-color: {color}22; "
                        f"color: {color}; "
                        f"font-weight: bold"
                    )
                    break

        return styles

    st.dataframe(
        display.style.apply(_style_candidates, axis=1),
        use_container_width=True,
        hide_index=True,
    )

    # Legend: candidate status (in lifecycle order)
    legend_cols = st.columns(7)
    status_legend = [
        (legend_cols[0], _STATUS_COLORS["scanned"], "SCANNED = Gap check pending"),
        (legend_cols[1], _STATUS_COLORS["passed"], "PASSED = Gap OK"),
        (legend_cols[2], _STATUS_COLORS["filtered"], "FILTERED = Gap too large"),
        (legend_cols[3], _STATUS_COLORS["skipped"], "SKIPPED = Outside market hours"),
        (legend_cols[4], _STATUS_COLORS["held"], "HELD = Already held"),
        (legend_cols[5], _STATUS_COLORS["entered"], "ENTERED = Trade placed"),
        (legend_cols[6], _STATUS_COLORS["blocked"], "BLOCKED = Entry denied"),
    ]
    for col, color, text in status_legend:
        with col:
            st.markdown(
                f'<span style="color:{color};font-size:0.85em">{text}</span>',
                unsafe_allow_html=True,
            )


def _render_score_distribution(
    all_scores: list[float],
    candidates_df: pd.DataFrame,
) -> None:
    """Render a histogram of composite scores with top-12 cutoff line."""
    st.subheader("Score Distribution (All 503 Symbols)")

    if not all_scores:
        st.caption("No score data available.")
        return

    # Find the cutoff score (lowest score in top-12 candidates)
    cutoff_score = None
    if not candidates_df.empty and "score" in candidates_df.columns:
        try:
            numeric_scores = pd.to_numeric(candidates_df["score"], errors="coerce").dropna()
            if not numeric_scores.empty:
                cutoff_score = float(numeric_scores.min())
        except (ValueError, TypeError):
            pass

    fig = go.Figure()

    fig.add_trace(
        go.Histogram(
            x=all_scores,
            nbinsx=50,
            name="Score Distribution",
            marker_color=COLORS["info"],
            opacity=0.7,
            hovertemplate="Score range: %{x}<br>Count: %{y}<extra></extra>",
        )
    )

    # Add cutoff line for top-12 selection
    if cutoff_score is not None:
        fig.add_vline(
            x=cutoff_score,
            line_dash="dash",
            line_color=COLORS["warning"],
            annotation_text=f"Top 12 cutoff: {cutoff_score:.3f}",
            annotation_position="top right",
            annotation_font_color=COLORS["warning"],
        )

    fig.update_layout(
        **get_chart_layout(
            title={"text": "Composite Score Distribution"},
            height=320,
            xaxis={"title": "Composite Score"},
            yaxis={"title": "Symbol Count"},
            showlegend=False,
        )
    )

    st.plotly_chart(fig, use_container_width=True, key="score_distribution")

    # Summary stats
    if all_scores:
        import statistics
        col_min, col_max, col_mean, col_median = st.columns(4)
        with col_min:
            st.metric("Min Score", f"{min(all_scores):.3f}")
        with col_max:
            st.metric("Max Score", f"{max(all_scores):.3f}")
        with col_mean:
            st.metric("Mean Score", f"{statistics.mean(all_scores):.3f}")
        with col_median:
            st.metric("Median Score", f"{statistics.median(all_scores):.3f}")


def _render_risk_preview(candidates_df: pd.DataFrame, dashboard_data) -> None:
    """Simulate risk impact if all scan candidates are entered."""
    st.subheader("Risk Preview (If All Candidates Entered)")

    current_positions = getattr(dashboard_data, "current_positions", [])
    current_equity = getattr(dashboard_data, "current_equity", 0.0)
    current_count = len(current_positions)

    # Filter out already-held symbols so they are not double-counted
    held_set = set(current_positions)
    from autotrader.dashboard.data_loader import load_open_positions
    held_set.update(load_open_positions().keys())

    if "symbol" in candidates_df.columns and held_set:
        new_candidates_df = candidates_df[~candidates_df["symbol"].isin(held_set)]
    else:
        new_candidates_df = candidates_df

    new_count = len(new_candidates_df)
    projected_total = current_count + new_count

    # Count longs and shorts in candidates (excluding already-held)
    new_longs = 0
    new_shorts = 0
    projected_risk = 0.0
    if "direction" in new_candidates_df.columns:
        new_longs = int((new_candidates_df["direction"].str.lower() == "long").sum())
        new_shorts = new_count - new_longs

    # Estimate risk from candidates
    if "atr" in new_candidates_df.columns and "strategy" in new_candidates_df.columns:
        for _, row in new_candidates_df.iterrows():
            atr_val = pd.to_numeric(row.get("atr", 0), errors="coerce") or 0
            strat = str(row.get("strategy", ""))
            dirn = str(row.get("direction", "long")).lower()
            if atr_val > 0 and current_equity > 0:
                sl_mult = SL_ATR_MULT.get(strat, {}).get(dirn, 2.0)
                risk_per_share = sl_mult * atr_val
                qty = int(current_equity * RISK_PER_TRADE_PCT / risk_per_share) if risk_per_share > 0 else 0
                projected_risk += risk_per_share * qty

    heat_pct = (projected_risk / current_equity * 100) if current_equity > 0 else 0.0

    # Direction bias
    total_new = new_longs + new_shorts
    if total_new > 0:
        bias = f"{new_longs/total_new*100:.0f}% L / {new_shorts/total_new*100:.0f}% S"
    else:
        bias = "--"

    # 4-column KPI
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        color = COLORS["warning"] if projected_total > 8 else COLORS["info"]
        st.markdown(
            f'<div style="background:{COLORS["bg_card"]};border-radius:8px;padding:12px;text-align:center">'
            f'<div style="color:{COLORS["text_muted"]};font-size:0.8em">Projected Positions</div>'
            f'<div style="color:{color};font-size:1.5em;font-weight:700">{projected_total}</div>'
            f'<div style="color:{COLORS["text_muted"]};font-size:0.75em">{current_count} current + {new_count} new</div>'
            f'</div>', unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div style="background:{COLORS["bg_card"]};border-radius:8px;padding:12px;text-align:center">'
            f'<div style="color:{COLORS["text_muted"]};font-size:0.8em">New Longs / Shorts</div>'
            f'<div style="font-size:1.5em;font-weight:700">'
            f'<span style="color:{COLORS["profit"]}">{new_longs}</span> / '
            f'<span style="color:{COLORS["loss"]}">{new_shorts}</span></div>'
            f'</div>', unsafe_allow_html=True,
        )
    with c3:
        _limit = MAX_PORTFOLIO_HEAT_PCT * 100
        _ratio = heat_pct / _limit if _limit > 0 else 0
        heat_color = COLORS["loss"] if _ratio > 0.75 else (COLORS["warning"] if _ratio > 0.50 else COLORS["profit"])
        st.markdown(
            f'<div style="background:{COLORS["bg_card"]};border-radius:8px;padding:12px;text-align:center">'
            f'<div style="color:{COLORS["text_muted"]};font-size:0.8em">Projected Heat</div>'
            f'<div style="color:{heat_color};font-size:1.5em;font-weight:700">+{heat_pct:.1f}%</div>'
            f'<div style="color:{COLORS["text_muted"]};font-size:0.75em">additional risk</div>'
            f'</div>', unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f'<div style="background:{COLORS["bg_card"]};border-radius:8px;padding:12px;text-align:center">'
            f'<div style="color:{COLORS["text_muted"]};font-size:0.8em">Direction Bias</div>'
            f'<div style="color:{COLORS["info"]};font-size:1.2em;font-weight:700">{bias}</div>'
            f'</div>', unsafe_allow_html=True,
        )


def _format_scan_timestamp(scan_ts: str) -> str:
    """Format scan timestamp for compact display (converted to ET)."""
    if not scan_ts:
        return "Never"
    try:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        dt = datetime.fromisoformat(scan_ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        et = dt.astimezone(ZoneInfo("America/New_York"))
        return et.strftime("%m/%d %H:%M ET")
    except (ValueError, TypeError):
        return scan_ts[:16] if len(scan_ts) > 16 else scan_ts
