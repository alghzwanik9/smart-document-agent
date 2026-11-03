from datetime import datetime

import pandas as pd
import streamlit as st

from components.charts import render_summary_charts, render_summary_indicators
from utils import strings
from utils.api_client import ApiClient, ApiError, Unreachable, shared_client

RECENT_CORRECTIONS = 10


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


def _corrections_frame(items: list[dict]) -> pd.DataFrame:
    return pd.DataFrame({
        strings.COLUMN_FIELD: [strings.FIELD_LABELS.get(i["field_name"], i["field_name"]) for i in items],
        strings.COLUMN_BEFORE: [i["original_value"] or "" for i in items],
        strings.COLUMN_AFTER: [i["corrected_value"] for i in items],
        strings.COLUMN_DATE: [f"⁦{_when(i['correction_date'])}⁩" for i in items],
    })


def render_analytics(client: ApiClient) -> None:
    st.title(strings.ANALYTICS_TITLE)
    st.caption(strings.ANALYTICS_CAPTION)
    try:
        summary = client.analytics_summary()
        corrections = client.list_corrections(page_size=RECENT_CORRECTIONS)
    except Unreachable:
        st.error(strings.ERROR_UNREACHABLE.format(url=client.base_url))
        return
    except ApiError as error:
        st.error(strings.ERROR_REJECTED_KEY if error.status == 401 else
                 strings.ERROR_GENERIC.format(status=error.status, reason=error.detail))
        return

    if summary["documents_total"] == 0:
        st.info(strings.ANALYTICS_EMPTY)
        return
    render_summary_indicators(summary)
    render_summary_charts(summary)

    st.subheader(strings.CORRECTIONS_HEADER)
    st.caption(strings.CORRECTIONS_HELP)
    if not corrections["items"]:
        st.info(strings.CORRECTIONS_EMPTY)
        return
    st.dataframe(_corrections_frame(corrections["items"]), hide_index=True, width="stretch")


render_analytics(shared_client())
