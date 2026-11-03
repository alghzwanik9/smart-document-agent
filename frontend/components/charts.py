import pandas as pd
import streamlit as st

from components.extracted_data_table import effective_value, group_records, needs_review, record_label
from utils import strings

MAX_CHART_RECORDS = 40
BAR_BASE_HEIGHT = 70
BAR_ROW_HEIGHT = 40
SERIES_COLORS = ["#4A90E2", "#7ED321", "#D0021B"]   # primary, accent, danger from blueprint section 12
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


def to_number(text: str) -> float | None:
    try:
        return float(text.translate(_ARABIC_DIGITS).replace(",", "").strip())
    except ValueError:
        return None


def summary(fields: list[dict]) -> dict:
    """The figures of the key-indicator row."""
    records = group_records(fields)
    nets = [to_number(effective_value(r["net_salary"])) for r in records.values() if "net_salary" in r]
    confidences = [f["confidence"] for f in fields if f["confidence"] is not None]
    return {
        "records": len(records),
        "total_net": sum(n for n in nets if n is not None),
        "confidence": sum(confidences) / len(confidences) if confidences else None,
        "review": sum(1 for f in fields if needs_review(f)),
    }


def components_frame(fields: list[dict]) -> pd.DataFrame:
    """Basic salary, allowances and deductions of each employee, indexed by a unique label."""
    rows, seen = {}, {}
    for position, (index, record) in enumerate(group_records(fields).items()):
        label = record_label(index, record, position)
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            label = f"{label} ({seen[label]})"
        values = {strings.CHART_SERIES[name]: to_number(effective_value(record[name])) if name in record else None
                  for name in strings.CHART_SERIES}
        if any(v is not None for v in values.values()):
            rows[label] = values
    return pd.DataFrame.from_dict(rows, orient="index", columns=list(strings.CHART_SERIES.values()))


def render_indicators(fields: list[dict]) -> None:
    figures = summary(fields)
    first, second, third, fourth = st.columns(4)
    first.metric(strings.KPI_RECORDS, figures["records"])
    total = figures["total_net"]
    second.metric(strings.KPI_TOTAL_NET, f"{total:,.0f}" if float(total).is_integer() else f"{total:,.2f}")
    third.metric(strings.KPI_CONFIDENCE, "-" if figures["confidence"] is None else f"{figures['confidence']:.0%}")
    fourth.metric(strings.KPI_REVIEW, figures["review"])


def render_charts(fields: list[dict]) -> None:
    st.subheader(strings.CHARTS_HEADER)
    frame = components_frame(fields)
    if frame.empty:
        st.info(strings.CHART_EMPTY)
        return
    st.caption(strings.CHART_COMPONENTS)
    if len(frame) > MAX_CHART_RECORDS:
        st.caption(strings.CHART_LIMIT.format(count=MAX_CHART_RECORDS, total=len(frame)))
    st.bar_chart(frame.head(MAX_CHART_RECORDS).fillna(0), color=SERIES_COLORS, stack=False)


# ---------------------------------------------------------------------- analytics page
def counts_frame(counts: dict[str, int], labels: dict[str, str] | None = None) -> pd.DataFrame:
    """One bar per key, named with its interface label, in the order the backend gave."""
    names = [(labels or {}).get(key, key) for key in counts]
    return pd.DataFrame({strings.KPI_DOCUMENTS: list(counts.values())}, index=names)


def render_summary_indicators(summary: dict) -> None:
    completed = summary["documents_by_status"].get("completed", 0)
    confidence = summary["average_confidence"]
    columns = st.columns(5)
    columns[0].metric(strings.KPI_DOCUMENTS, summary["documents_total"])
    columns[1].metric(strings.KPI_COMPLETED, completed)
    columns[2].metric(strings.KPI_FIELDS, summary["fields_total"])
    columns[3].metric(strings.KPI_CONFIDENCE, strings.KPI_NO_CONFIDENCE if confidence is None else f"{confidence:.0%}")
    columns[4].metric(strings.KPI_CORRECTIONS, summary["corrections_total"])


def _bars(frame: pd.DataFrame, color: str) -> None:
    """Horizontal bars, as tall as they have rows: a lone bar must not fill the page."""
    st.bar_chart(frame, color=color, horizontal=True, height=BAR_BASE_HEIGHT + BAR_ROW_HEIGHT * len(frame))


def render_summary_charts(summary: dict) -> None:
    left, right = st.columns(2)
    with left:
        st.caption(strings.CHART_BY_TYPE)
        _bars(counts_frame(summary["documents_by_type"]), SERIES_COLORS[0])
    with right:
        st.caption(strings.CHART_BY_STATUS)
        _bars(counts_frame(summary["documents_by_status"], strings.STATUS_LABELS), SERIES_COLORS[0])
    if summary["corrected_by_field"]:
        st.caption(strings.CHART_BY_FIELD)
        frame = counts_frame(summary["corrected_by_field"], strings.FIELD_LABELS)
        _bars(frame.rename(columns={strings.KPI_DOCUMENTS: strings.KPI_CORRECTIONS}), SERIES_COLORS[1])
