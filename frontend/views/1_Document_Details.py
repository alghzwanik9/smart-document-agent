from datetime import datetime

import streamlit as st

from components.charts import render_charts, render_indicators
from components.extracted_data_table import render_extracted_data
from utils import strings
from utils.api_client import ApiClient, ApiError, Unreachable, shared_client


def _size(byte_count: int) -> str:
    return f"{byte_count / 1024:,.0f} KB" if byte_count < 1024 * 1024 else f"{byte_count / 1024 / 1024:,.1f} MB"


def _ltr(text: str) -> str:
    """Keeps a date or a size in reading order inside right-to-left text (it is isolated from the surrounding bidi run)."""
    return f"⁦{text}⁩"


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


def _render_export(client: ApiClient, document: dict, fields: list[dict]) -> None:
    st.subheader(strings.EXPORT_HEADER)
    file_format = document["file_type"]
    st.caption(strings.EXPORT_NOTE.format(format=file_format))
    if document["file_type"] == "PDF":
        st.caption(strings.EXPORT_PDF_NOTE)
    key = f"export_{document['id']}"

    if st.button(strings.EXPORT_PREPARE.format(format=file_format), icon=":material/description:",
                 key=f"prepare_{document['id']}"):
        try:
            st.session_state[key] = client.export(document["id"])
        except Unreachable:
            st.error(strings.ERROR_UNREACHABLE.format(url=client.base_url))
        except ApiError as error:
            st.error(strings.EXPORT_FAILED.format(reason=error.detail))

    prepared = st.session_state.get(key)
    if prepared is None:
        return
    if prepared.unplaced:
        names = {f["id"]: strings.FIELD_LABELS.get(f["field_name"], f["field_name"]) for f in fields}
        st.warning(strings.EXPORT_UNPLACED.format(
            count=len(prepared.unplaced), fields="، ".join(names.get(i, str(i)) for i in prepared.unplaced)))
    else:
        st.success(strings.EXPORT_READY)
    st.download_button(strings.EXPORT_DOWNLOAD, data=prepared.content, file_name=prepared.filename,
                       mime=prepared.media_type, icon=":material/download:", type="primary",
                       key=f"download_{document['id']}")


def render_details(client: ApiClient) -> None:
    raw_id = st.query_params.get("document_id", "")
    if not raw_id.isdigit():
        st.info(strings.DETAILS_NO_ID)
        return
    document_id = int(raw_id)

    try:
        document = client.get_document(document_id)
        fields = client.get_fields(document_id) if document["status"] == "completed" else []
    except Unreachable:
        st.error(strings.ERROR_UNREACHABLE.format(url=client.base_url))
        return
    except ApiError as error:
        st.error(strings.DETAILS_NOT_FOUND if error.status == 404 else
                 strings.ERROR_REJECTED_KEY if error.status == 401 else
                 strings.ERROR_GENERIC.format(status=error.status, reason=error.detail))
        return

    st.title(document["filename"])
    st.caption(strings.DETAILS_INFO.format(type=_ltr(document["file_type"]), size=_ltr(_size(document["file_size"])),
                                           when=_ltr(_when(document["upload_date"]))))
    if document["status"] != "completed":
        st.warning(strings.DETAILS_NOT_READY.format(status=strings.STATUS_LABELS.get(document["status"], document["status"])))
        if document.get("error_message"):
            st.caption(document["error_message"])
        return

    flash = st.session_state.pop("flash", None)
    if flash:
        st.toast(flash)
    render_indicators(fields)
    render_extracted_data(client, document_id, fields)
    render_charts(fields)
    _render_export(client, document, fields)


render_details(shared_client())
