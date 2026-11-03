"""The one place that makes the interface right-to-left and sets the fonts."""
import streamlit as st

# System fonts only: nothing is fetched from the internet. Cairo and Noto Sans Arabic are used when installed.
FONT_STACK = "'Cairo', 'Noto Sans Arabic', 'Segoe UI', Tahoma, Arial, sans-serif"

RTL_CSS = f"""
<style>
/* text elements only: icons are spans in their own icon font, and a wider selector would turn them into words */
body, .stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp label, .stApp li, .stApp input,
.stApp textarea, .stApp button {{ font-family: {FONT_STACK}; }}
.stApp, [data-testid="stSidebar"] {{ direction: rtl; }}
.stApp [data-testid="stMarkdownContainer"], .stApp label, .stApp [data-testid="stCaptionContainer"] {{ text-align: right; }}
.stApp [data-testid="stFileUploaderDropzone"] {{ direction: rtl; }}
/* numbers, file names and emails keep their own direction inside right-to-left text */
.stApp code, .stApp [data-testid="stDataFrame"] {{ direction: ltr; unicode-bidi: plaintext; }}
/* the chart engine lays out its axis and legend left to right; the labels are still Arabic text */
.stApp [data-testid="stVegaLiteChart"] {{ direction: ltr; }}
/* a key figure must fit its column at any width: shrink rather than cut it with an ellipsis */
.stApp [data-testid="stMetricValue"] {{ font-size: clamp(1.25rem, 2.2vw, 2.25rem); }}
.stApp [data-testid="stMetricValue"] > div {{ overflow: visible; text-overflow: clip; }}
</style>
"""


def inject_rtl() -> None:
    st.markdown(RTL_CSS, unsafe_allow_html=True)
