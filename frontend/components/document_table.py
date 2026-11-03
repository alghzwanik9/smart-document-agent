from datetime import datetime

import streamlit as st

from utils import strings
from utils.api_client import ApiClient, ApiError, Unreachable

PAGE_SIZE = 10
REFRESH_SECONDS = 4
WIDTHS = [4, 1.2, 2, 2.4, 1.4]


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


def _delete(client: ApiClient, document: dict) -> None:
    try:
        client.delete_document(document["id"])
        st.toast(strings.DELETE_DONE.format(name=document["filename"]))
        st.rerun(scope="fragment")
    except ApiError as error:
        st.error(strings.DELETE_FAILED.format(name=document["filename"], reason=error.detail))


@st.fragment(run_every=REFRESH_SECONDS)
def render_document_table(client: ApiClient) -> None:
    """The list of documents. It refreshes itself while documents are being processed."""
    st.subheader(strings.LIST_HEADER)
    page = st.session_state.setdefault("document_page", 1)
    try:
        data = client.list_documents(page=page, page_size=PAGE_SIZE)
    except Unreachable:
        st.error(strings.ERROR_UNREACHABLE.format(url=client.base_url))
        return
    except ApiError as error:
        st.error(strings.ERROR_REJECTED_KEY if error.status == 401 else
                 strings.ERROR_GENERIC.format(status=error.status, reason=error.detail))
        return

    pages = max(1, -(-data["total"] // PAGE_SIZE))
    if page > pages:                        # the last document of the page was deleted
        st.session_state["document_page"] = pages
        st.rerun(scope="fragment")
    if not data["items"]:
        st.info(strings.LIST_EMPTY)
        return

    header = st.columns(WIDTHS, vertical_alignment="center")
    for cell, label in zip(header, (strings.COLUMN_FILE, strings.COLUMN_TYPE, strings.COLUMN_STATUS,
                                    strings.COLUMN_UPLOADED, strings.COLUMN_ACTIONS)):
        cell.caption(label)

    for document in data["items"]:
        with st.container(border=True):
            name, kind, status, uploaded, actions = st.columns(WIDTHS, vertical_alignment="center")
            name.markdown(f"`{document['filename']}`")
            kind.write(document["file_type"])
            state = document["status"]
            status.badge(strings.STATUS_LABELS.get(state, state), color=strings.STATUS_COLORS.get(state, "gray"))
            uploaded.write(_when(document["upload_date"]))
            if state == "completed":
                actions.page_link("views/1_Document_Details.py", label=strings.DETAILS_BUTTON,
                                  icon=":material/table_view:", query_params={"document_id": document["id"]})
            with actions.popover(strings.DELETE, icon=":material/delete:"):
                st.write(strings.DELETE_NOTE)
                if st.button(strings.DELETE_CONFIRM, key=f"delete_{document['id']}", type="primary"):
                    _delete(client, document)
            if state == "failed" and document.get("error_message"):
                st.caption(document["error_message"])

    previous, middle, following = st.columns([1, 2, 1], vertical_alignment="center")
    if previous.button(strings.PAGE_PREVIOUS, disabled=page <= 1, icon=":material/chevron_right:"):
        st.session_state["document_page"] = page - 1
        st.rerun(scope="fragment")
    middle.caption(f"{strings.PAGE_OF.format(page=page, pages=pages)} - {strings.TOTAL.format(total=data['total'])}")
    if following.button(strings.PAGE_NEXT, disabled=page >= pages, icon=":material/chevron_left:"):
        st.session_state["document_page"] = page + 1
        st.rerun(scope="fragment")
