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
from autotrader.trading.constants import RISK_PER_TRADE_PCT, SL_ATR_MULT


# Entry group color mapping
_ENTRY_GROUP_COLORS = {
    "MOO": COLORS["profit"],        # Green for market-on-open
    "Confirm": COLORS["info"],      # Blue for confirmation entries
    "CONFIRM": COLORS["info"],
}

# Gap filter status badge colors
_GAP_STATUS_COLORS = {
    "passed": COLORS["profit"],
    "filtered": COLORS["loss"],
    "pending": COLORS["warning"],
    "skipped": COLORS["neutral"],
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
        st.info("No batch scan data available. Run the nightly scanner to populate this tab.")
        return

    scan_ts = getattr(batch_data, "scan_timestamp", "")
    total_scanned = getattr(batch_data, "total_scanned", 0)
    signals_generated = getattr(batch_data, "signals_generated", 0)
    candidates_df = getattr(batch_data, "candidates_df", pd.DataFrame())
    all_scores = getattr(batch_data, "all_scores", [])

    if not scan_ts and total_scanned == 0:
        st.info("No batch scan data found. Nightly scan has not run yet.")
        _render_empty_scan_placeholder()
        return

    # -- Scan summary KPIs --------------------------------------------------
    _render_scan_summary(scan_ts, total_scanned, signals_generated, candidates_df)

    st.divider()

    # -- Candidates table ---------------------------------------------------
    st.subheader("Top Candidates")
    if candidates_df.empty:
        st.info("No candidates selected in the last scan.")
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
        f"""
        <div style="
            background-color: {COLORS['bg_card']};
            border: 1px solid {COLORS['bg_section']};
            border-radius: 8px;
            padding: 32px 24px;
            text-align: center;
        ">
            <div style="color:{COLORS['text_secondary']};font-size:1.1em;font-weight:600;margin-bottom:12px">
                Nightly Batch Scan
            </div>
            <div style="color:{COLORS['text_muted']};font-size:0.9em;line-height:1.6">
                The nightly scanner runs at 22:00 ET on weekdays.<br>
                It scans all 503 S&amp;P 500 symbols, scores each candidate,<br>
                and selects up to 12 top candidates for next-day entry.<br><br>
                Results appear here after the scan completes.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
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
        st.metric("Symbols Scanned", f"{total_scanned:,}")

    with col_signals:
        st.metric("Signals Generated", str(signals_generated))

    with col_selected:
        selected_count = len(candidates_df) if not candidates_df.empty else 0
        moo_count = 0
        confirm_count = 0
        if not candidates_df.empty and "entry_group" in candidates_df.columns:
            moo_count = int((candidates_df["entry_group"].str.upper() == "MOO").sum())
            confirm_count = selected_count - moo_count

        delta_text = f"{moo_count} MOO | {confirm_count} Confirm"
        st.metric("Candidates Selected", str(selected_count), delta=delta_text)


def _render_candidates_table(
    candidates_df: pd.DataFrame,
    held_symbols: set[str] | None = None,
) -> None:
    """Render the sortable, color-coded candidates table."""
    df = candidates_df.copy()

    # Normalize column presence
    expected_cols = [
        "rank", "symbol", "strategy", "direction", "score",
        "entry_group", "est_qty", "est_size",
        "sl_price", "tp_price", "atr", "gap_filter_status",
    ]
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

    # Rename for display
    display = df[expected_cols].rename(columns={
        "rank": "Rank",
        "symbol": "Symbol",
        "strategy": "Strategy",
        "direction": "Dir",
        "score": "Score",
        "entry_group": "Entry Group",
        "est_qty": "Est.Qty",
        "est_size": "Est.Size",
        "sl_price": "SL",
        "tp_price": "TP",
        "atr": "ATR",
        "gap_filter_status": "Gap Filter",
    })

    # Add "Status" column indicating already-held positions
    if held_symbols and "symbol" in candidates_df.columns:
        display.insert(
            2,  # After Rank and Symbol
            "Status",
            candidates_df["symbol"].map(
                lambda s: "HELD" if s in held_symbols else ""
            ).values,
        )
    else:
        display.insert(2, "Status", "")

    def _style_candidates(row: pd.Series) -> list[str]:
        styles = [""] * len(row)
        if "Entry Group" in row.index:
            idx = row.index.get_loc("Entry Group")
            group = str(row["Entry Group"]).upper()
            if group == "MOO":
                styles[idx] = f"background-color: {COLORS['profit']}22; color: {COLORS['profit']}; font-weight: bold"
            elif group in ("CONFIRM", "CONFIRMATION"):
                styles[idx] = f"background-color: {COLORS['info']}22; color: {COLORS['info']}; font-weight: bold"

        if "Gap Filter" in row.index:
            idx = row.index.get_loc("Gap Filter")
            status = str(row["Gap Filter"]).lower()
            color = _GAP_STATUS_COLORS.get(status, COLORS["neutral"])
            styles[idx] = f"color: {color}; font-weight: bold"

        if "Dir" in row.index:
            idx = row.index.get_loc("Dir")
            direction = str(row["Dir"]).lower()
            if direction in ("long", "buy"):
                styles[idx] = f"color: {COLORS['profit']}"
            elif direction in ("short", "sell"):
                styles[idx] = f"color: {COLORS['loss']}"

        if "Status" in row.index:
            idx = row.index.get_loc("Status")
            if str(row["Status"]).upper() == "HELD":
                styles[idx] = (
                    f"background-color: {COLORS['warning']}22; "
                    f"color: {COLORS['warning']}; "
                    f"font-weight: bold"
                )

        return styles

    st.dataframe(
        display.style.apply(_style_candidates, axis=1),
        use_container_width=True,
        hide_index=True,
    )

    # Legend: gap filter status (in lifecycle order)
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    gap_legend = [
        (col1, COLORS["warning"], "Pending = Gap check in progress"),
        (col2, COLORS["profit"], "Passed = Gap check OK"),
        (col3, COLORS["loss"], "Filtered = Gap too large"),
        (col4, COLORS["neutral"], "Skipped = Outside market hours"),
    ]
    for col, color, text in gap_legend:
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

    new_count = len(candidates_df)
    projected_total = current_count + new_count

    # Count longs and shorts in candidates
    new_longs = 0
    new_shorts = 0
    projected_risk = 0.0
    if "direction" in candidates_df.columns:
        new_longs = int((candidates_df["direction"].str.lower() == "long").sum())
        new_shorts = new_count - new_longs

    # Estimate risk from candidates
    if "atr" in candidates_df.columns and "strategy" in candidates_df.columns:
        for _, row in candidates_df.iterrows():
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
        heat_color = COLORS["loss"] if heat_pct > 35 else (COLORS["warning"] if heat_pct > 25 else COLORS["profit"])
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
