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
}


def render_scan_results(batch_data) -> None:
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
        _render_candidates_table(candidates_df)

    st.divider()

    # -- Score distribution histogram ---------------------------------------
    if all_scores:
        _render_score_distribution(all_scores, candidates_df)
    else:
        st.caption("Score distribution data not available.")


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


def _render_candidates_table(candidates_df: pd.DataFrame) -> None:
    """Render the sortable, color-coded candidates table."""
    df = candidates_df.copy()

    # Normalize column presence
    expected_cols = [
        "rank", "symbol", "strategy", "direction", "score",
        "entry_group", "sl_price", "tp_price", "atr", "gap_filter_status",
    ]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = "--"

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
        "sl_price": "SL",
        "tp_price": "TP",
        "atr": "ATR",
        "gap_filter_status": "Gap Filter",
    })

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

        return styles

    st.dataframe(
        display.style.apply(_style_candidates, axis=1),
        use_container_width=True,
        hide_index=True,
    )

    # Entry group legend
    col_leg1, col_leg2, col_leg3, _ = st.columns([1, 1, 1, 3])
    with col_leg1:
        st.markdown(
            f'<span style="color:{COLORS["profit"]};font-size:0.85em">MOO = Market-On-Open order</span>',
            unsafe_allow_html=True,
        )
    with col_leg2:
        st.markdown(
            f'<span style="color:{COLORS["info"]};font-size:0.85em">Confirm = Wait for confirmation</span>',
            unsafe_allow_html=True,
        )
    with col_leg3:
        st.markdown(
            f'<span style="color:{COLORS["warning"]};font-size:0.85em">Pending = Gap check in progress</span>',
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


def _format_scan_timestamp(scan_ts: str) -> str:
    """Format scan timestamp for compact display."""
    if not scan_ts:
        return "Never"
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(scan_ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%m/%d %H:%M ET")
    except (ValueError, TypeError):
        return scan_ts[:16] if len(scan_ts) > 16 else scan_ts
