"""IEPCI Quote Assistant
"""

import streamlit as st
import pandas as pd
import base64
from pathlib import Path
from tempfile import TemporaryDirectory

from src.extract_rfq import HEADER_FIELDS, extract_rfq_header, extract_rfq_lines
from src.match_missing_codes import find_missing_code_candidates
from src.load_price_lists import load_catalogue
from src.generate_quotation import generate_quotation
from src.pricing import apply_list_prices, suggest_list_prices

LOGO_PATH = Path("assets/IEPCI-UK-logo.png")


@st.cache_data
def get_logo_b64() -> str:
    """Return base64-encoded IEPCI UK logo string."""
    if LOGO_PATH.exists():
        return base64.b64encode(LOGO_PATH.read_bytes()).decode("utf-8")
    return ""


# ------------------------------------------------------------ Page Configuration
st.set_page_config(
    page_title="IEPCI Quote Assistant",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------ White & Blue Theme CSS
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap');

:root {
    --primary-blue: #2563EB;
    --primary-blue-hover: #1D4ED8;
    --primary-navy: #0F2942;
    --navy-deep: #0A192F;
    --accent-blue-light: #EFF6FF;
    --accent-blue-border: #BFDBFE;
    --surface-white: #FFFFFF;
    --surface-slate: #F8FAFC;
    --border-subtle: #E2E8F0;
    --border-strong: #CBD5E1;
    --text-primary: #0F172A;
    --text-secondary: #475569;
    --text-muted: #64748B;
    --success-green: #059669;
    --success-bg: #ECFDF5;
    --warning-amber: #D97706;
    --warning-bg: #FFFBEB;
}

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    color: var(--text-primary);
}

.stApp {
    background-color: var(--surface-slate) !important;
}

/* Adjust Main Container Padding */
.main .block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 3.5rem !important;
    max-width: 1400px !important;
}

/* Sidebar Styling */
section[data-testid="stSidebar"] {
    background-color: var(--surface-white) !important;
    border-right: 1px solid var(--border-subtle) !important;
    box-shadow: 1px 0 3px rgba(15, 23, 42, 0.02) !important;
}

section[data-testid="stSidebar"] .block-container {
    padding-top: 1.25rem !important;
    padding-left: 1.25rem !important;
    padding-right: 1.25rem !important;
}

/* Sidebar Radio Navigation */
div[data-testid="stRadio"] > label {
    display: none !important;
}

div[data-testid="stRadio"] > div {
    gap: 6px !important;
}

div[data-testid="stRadio"] label {
    background: var(--surface-white) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 9px !important;
    padding: 10px 14px !important;
    font-weight: 500 !important;
    font-size: 0.92rem !important;
    color: var(--text-secondary) !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    display: flex !important;
    align-items: center !important;
    cursor: pointer !important;
    margin-bottom: 2px !important;
}

div[data-testid="stRadio"] label:hover {
    background: var(--accent-blue-light) !important;
    border-color: var(--accent-blue-border) !important;
    color: var(--primary-blue-hover) !important;
    transform: translateX(2px);
}

div[data-testid="stRadio"] label:has(input:checked) {
    background: linear-gradient(90deg, #EFF6FF 0%, #FFFFFF 100%) !important;
    border-color: var(--primary-blue) !important;
    border-left: 4px solid var(--primary-blue) !important;
    color: var(--primary-blue-hover) !important;
    font-weight: 700 !important;
    box-shadow: 0 2px 5px rgba(37, 99, 235, 0.08) !important;
}

/* Streamlit Native Metric Cards */
div[data-testid="stMetric"] {
    background: var(--surface-white) !important;
    border: 1px solid var(--border-subtle) !important;
    border-top: 3px solid var(--primary-blue) !important;
    border-radius: 12px !important;
    padding: 16px 20px !important;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04) !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
}

div[data-testid="stMetric"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 16px rgba(37, 99, 235, 0.08) !important;
}

div[data-testid="stMetricLabel"] {
    color: var(--text-muted) !important;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
}

div[data-testid="stMetricValue"] {
    color: var(--primary-navy) !important;
    font-weight: 700 !important;
    font-size: 1.85rem !important;
}

/* Primary and Secondary Buttons */
button[kind="primary"], .stButton > button[type="primary"] {
    background: linear-gradient(135deg, #1D4ED8 0%, #2563EB 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.55rem 1.35rem !important;
    font-weight: 600 !important;
    font-size: 0.92rem !important;
    letter-spacing: 0.01em !important;
    box-shadow: 0 2px 6px rgba(37, 99, 235, 0.25) !important;
    transition: all 0.2s ease !important;
}

button[kind="primary"]:hover, .stButton > button[type="primary"]:hover {
    background: linear-gradient(135deg, #1E40AF 0%, #1D4ED8 100%) !important;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35) !important;
    transform: translateY(-1px) !important;
}

button[kind="secondary"], .stButton > button:not([type="primary"]) {
    background: var(--surface-white) !important;
    color: var(--primary-navy) !important;
    border: 1px solid var(--border-strong) !important;
    border-radius: 8px !important;
    padding: 0.55rem 1.25rem !important;
    font-weight: 600 !important;
    font-size: 0.92rem !important;
    transition: all 0.2s ease !important;
}

button[kind="secondary"]:hover, .stButton > button:not([type="primary"]):hover {
    background: var(--accent-blue-light) !important;
    border-color: var(--accent-blue-border) !important;
    color: var(--primary-blue-hover) !important;
    box-shadow: 0 2px 4px rgba(37, 99, 235, 0.08) !important;
}

/* Download Button (Success Green Accent) */
.stDownloadButton > button {
    background: linear-gradient(135deg, #059669 0%, #10B981 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.65rem 1.5rem !important;
    font-weight: 700 !important;
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.25) !important;
    transition: all 0.2s ease !important;
}

.stDownloadButton > button:hover {
    box-shadow: 0 4px 16px rgba(16, 185, 129, 0.35) !important;
    transform: translateY(-1px) !important;
}

/* Dataframe and Data Editor Styling */
div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {
    background: var(--surface-white);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.03);
}

/* Input Fields and Select Boxes */
div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div {
    background-color: var(--surface-white) !important;
    border-color: var(--border-strong) !important;
    border-radius: 8px !important;
    color: var(--text-primary) !important;
}

div[data-baseweb="input"]:focus-within > div,
div[data-baseweb="select"]:focus-within > div {
    border-color: var(--primary-blue) !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15) !important;
}

/* Custom Component Classes */
.brand-banner {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--surface-white);
    border: 1px solid var(--border-subtle);
    border-top: 3px solid var(--primary-blue);
    border-radius: 14px;
    padding: 16px 24px;
    margin-bottom: 24px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}

.brand-left {
    display: flex;
    align-items: center;
    gap: 16px;
}

.brand-icon-box {
    background: linear-gradient(135deg, #1E3A8A 0%, #2563EB 100%);
    color: #FFFFFF;
    width: 44px;
    height: 44px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.4rem;
    box-shadow: 0 2px 6px rgba(37, 99, 235, 0.25);
}

.brand-title-wrap {
    display: flex;
    flex-direction: column;
}

.brand-title {
    font-size: 1.28rem;
    font-weight: 800;
    color: var(--primary-navy);
    letter-spacing: -0.02em;
    display: flex;
    align-items: center;
    gap: 8px;
}

.brand-badge {
    background: var(--accent-blue-light);
    color: var(--primary-blue-hover);
    border: 1px solid var(--accent-blue-border);
    font-size: 0.65rem;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 6px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

.brand-subtitle {
    font-size: 0.85rem;
    color: var(--text-muted);
    font-weight: 500;
}

.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 0.82rem;
    font-weight: 600;
}

.status-pill-active {
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    color: #1D4ED8;
}

.status-pill-idle {
    background: #F1F5F9;
    border: 1px solid #E2E8F0;
    color: #64748B;
}

.ui-card {
    background: var(--surface-white);
    border: 1px solid var(--border-subtle);
    border-radius: 14px;
    padding: 22px 24px;
    margin-bottom: 20px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.03);
}

.ui-card-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--primary-navy);
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    gap: 8px;
}

.ui-card-subtitle {
    font-size: 0.83rem;
    color: var(--text-muted);
    margin-bottom: 16px;
}

.section-eyebrow {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--primary-blue);
    margin-bottom: 2px;
}

.section-heading {
    font-size: 1.55rem;
    font-weight: 800;
    color: var(--primary-navy);
    letter-spacing: -0.02em;
    margin-bottom: 4px;
}

.section-description {
    font-size: 0.9rem;
    color: var(--text-secondary);
    margin-bottom: 20px;
}

/* Modern Workflow Stepper */
.workflow-stepper {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: 24px;
}

.stepper-card {
    background: var(--surface-white);
    border: 1px solid var(--border-subtle);
    border-radius: 11px;
    padding: 12px 14px;
    display: flex;
    align-items: center;
    gap: 12px;
    transition: all 0.2s ease;
}

.stepper-card.done {
    border-color: #BFDBFE;
    background: linear-gradient(135deg, #F0F7FF 0%, #FFFFFF 100%);
}

.stepper-card.active {
    border-color: var(--primary-blue);
    background: #FFFFFF;
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
}

.stepper-num {
    width: 30px;
    height: 30px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;
    font-weight: 700;
    flex-shrink: 0;
}

.stepper-card.done .stepper-num {
    background: #2563EB;
    color: #FFFFFF;
}

.stepper-card.active .stepper-num {
    background: #EFF6FF;
    border: 2px solid #2563EB;
    color: #2563EB;
}

.stepper-card.idle .stepper-num {
    background: #F1F5F9;
    color: #94A3B8;
}

.stepper-text {
    display: flex;
    flex-direction: column;
}

.stepper-title {
    font-size: 0.82rem;
    font-weight: 700;
    color: var(--primary-navy);
}

.stepper-status {
    font-size: 0.72rem;
    color: var(--text-muted);
}

/* Callout Alert Boxes */
.callout-blue {
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-left: 4px solid var(--primary-blue);
    border-radius: 9px;
    padding: 14px 18px;
    margin: 14px 0 20px 0;
    display: flex;
    align-items: flex-start;
    gap: 12px;
    color: #1E3A8A;
    font-size: 0.88rem;
    line-height: 1.45;
}

.callout-amber {
    background: #FFFBEB;
    border: 1px solid #FDE68A;
    border-left: 4px solid var(--warning-amber);
    border-radius: 9px;
    padding: 14px 18px;
    margin: 14px 0 20px 0;
    display: flex;
    align-items: flex-start;
    gap: 12px;
    color: #92400E;
    font-size: 0.88rem;
    line-height: 1.45;
}

/* Commercial Financial Banner */
.commercial-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin-bottom: 22px;
}

.commercial-card {
    background: var(--surface-white);
    border: 1px solid var(--border-subtle);
    border-radius: 12px;
    padding: 16px 18px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.03);
    position: relative;
    overflow: hidden;
}

.commercial-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: #CBD5E1;
}

.commercial-card.highlight::before {
    background: var(--primary-blue);
}

.commercial-card.total::before {
    background: linear-gradient(90deg, #1D4ED8 0%, #3B82F6 100%);
}

.commercial-label {
    font-size: 0.74rem;
    font-weight: 700;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
}

.commercial-val {
    font-size: 1.45rem;
    font-weight: 800;
    color: var(--primary-navy);
    line-height: 1.2;
}

.commercial-sub {
    font-size: 0.74rem;
    color: var(--text-muted);
    margin-top: 4px;
}

.sidebar-brand-card {
    background: linear-gradient(135deg, #0F2942 0%, #1E3A8A 100%);
    border-radius: 12px;
    padding: 16px;
    color: #FFFFFF;
    margin-bottom: 16px;
    box-shadow: 0 4px 12px rgba(15, 41, 66, 0.2);
}

.sidebar-brand-title {
    font-size: 1.05rem;
    font-weight: 800;
    letter-spacing: 0.02em;
    display: flex;
    align-items: center;
    gap: 8px;
}

.sidebar-brand-sub {
    font-size: 0.74rem;
    color: #BFDBFE;
    font-weight: 500;
    margin-top: 2px;
}

.sidebar-info-card {
    background: var(--surface-white);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 14px;
    margin-top: 14px;
    font-size: 0.82rem;
}

.sidebar-info-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 5px 0;
    border-bottom: 1px solid #F1F5F9;
}

.sidebar-info-row:last-child {
    border-bottom: none;
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ------------------------------------------------------------ Data & State Helpers
@st.cache_data
def get_catalogue():
    """Load cached supplier catalogue from processed price lists."""
    return load_catalogue()


def get_rfq():
    """Retrieve current RFQ line items from session state."""
    return st.session_state.get("rfq_lines")


def prepare_rfq(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure RFQ dataframe has required pricing columns."""
    df = df.copy()
    if "unit_rate" not in df.columns:
        df["unit_rate"] = None
    if "price_approved" not in df.columns:
        df["price_approved"] = False
    return df


def load_rfq_bytes(file_bytes: bytes, filename: str) -> bool:
    """Extract RFQ lines and header from file bytes into session state."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / filename
        temp_path.write_bytes(file_bytes)

        extracted = extract_rfq_lines(str(temp_path))
        extracted = pd.DataFrame(extracted)

        if extracted.empty:
            return False

        st.session_state["rfq_lines"] = prepare_rfq(extracted)
        st.session_state["rfq_filename"] = filename
        st.session_state["match_candidates"] = None

        try:
            header = extract_rfq_header(str(temp_path))
        except Exception:
            header = {key: "" for key, _ in HEADER_FIELDS}

        st.session_state["rfq_header"] = header
        for key, _ in HEADER_FIELDS:
            st.session_state.pop(f"hdr_{key}", None)
        st.session_state.pop("rfq_editor", None)
        st.session_state.pop("pricing_editor", None)
        st.session_state.pop("quotation_bytes", None)
        return True


# Initialize session state keys
if "rfq_lines" not in st.session_state:
    st.session_state["rfq_lines"] = None

if "match_candidates" not in st.session_state:
    st.session_state["match_candidates"] = None

if "rfq_header" not in st.session_state:
    st.session_state["rfq_header"] = {}

if "rfq_filename" not in st.session_state:
    st.session_state["rfq_filename"] = None

if "quotation_bytes" not in st.session_state:
    st.session_state["quotation_bytes"] = None


# ------------------------------------------------------------ Sidebar Layout
with st.sidebar:
    logo_b64 = get_logo_b64()
    logo_img_sidebar = (
        f'<img src="data:image/png;base64,{logo_b64}" style="width:44px; height:44px; border-radius:50%; box-shadow:0 2px 8px rgba(0,0,0,0.2); object-fit:contain; background:#ffffff;" alt="IEPCI UK" />'
        if logo_b64
        else '<span style="font-size:1.6rem;">⚡</span>'
    )

    st.markdown(
        f"""
        <div class="sidebar-brand-card">
            <div style="display: flex; align-items: center; gap: 12px;">
                {logo_img_sidebar}
                <div>
                    <div class="sidebar-brand-title">IEPCI UK</div>
                    <div class="sidebar-brand-sub">Smart Quotation Assistant v2.4</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    nav_options = [
        "📊 Dashboard",
        "📑 RFQ Analysis",
        "🔍 Product Matching",
        "📚 Supplier Catalogue",
        "💰 Pricing & Quotation",
    ]

    selected_nav = st.radio(
        "Navigation",
        nav_options,
        index=0,
        label_visibility="collapsed",
    )
    current_page = selected_nav.split(" ", 1)[1]

    # Sidebar Document Status Card
    rfq_current = get_rfq()
    st.markdown("<hr style='margin: 16px 0; border: none; border-top: 1px solid #E2E8F0;' />", unsafe_allow_html=True)
    
    st.markdown("<div style='font-size:0.75rem; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:8px;'>Current RFQ State</div>", unsafe_allow_html=True)

    if rfq_current is None:
        st.markdown(
            """
            <div class="sidebar-info-card">
                <div style="color: #64748B; font-size: 0.82rem; margin-bottom: 8px;">No active RFQ document.</div>
                <div style="font-size: 0.78rem; color: #94A3B8;">Upload a file or load the demo RFQ to begin.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        sample_pdf = Path("data/raw/RFQ_KBS-0147.pdf")
        if sample_pdf.exists():
            if st.button("⚡ Load Demo RFQ (KBS-0147)", use_container_width=True):
                with st.spinner("Extracting demo RFQ..."):
                    if load_rfq_bytes(sample_pdf.read_bytes(), sample_pdf.name):
                        st.success("Loaded demo RFQ!")
                        st.rerun()
    else:
        filename = st.session_state.get("rfq_filename", "RFQ Document")
        total_lines = len(rfq_current)
        approved_count = 0
        if "price_approved" in rfq_current.columns:
            approved_count = int(rfq_current["price_approved"].fillna(False).astype(bool).sum())
        
        missing_count = 0
        if "part_code" in rfq_current.columns:
            missing_count = int(
                rfq_current["part_code"].fillna("").astype(str).str.strip().eq("").sum()
            )

        progress_pct = int((approved_count / total_lines * 100)) if total_lines > 0 else 0

        st.markdown(
            f"""
            <div class="sidebar-info-card">
                <div style="font-weight:700; color:#0F2942; font-size:0.85rem; word-break:break-all; margin-bottom:6px;">
                    📄 {filename}
                </div>
                <div class="sidebar-info-row">
                    <span style="color:#64748B;">Total Items:</span>
                    <span style="font-weight:700; color:#0F172A;">{total_lines}</span>
                </div>
                <div class="sidebar-info-row">
                    <span style="color:#64748B;">Missing Codes:</span>
                    <span style="font-weight:700; color:{'#D97706' if missing_count > 0 else '#059669'};">{missing_count}</span>
                </div>
                <div class="sidebar-info-row">
                    <span style="color:#64748B;">Approved Rates:</span>
                    <span style="font-weight:700; color:#2563EB;">{approved_count} / {total_lines} ({progress_pct}%)</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_rst, col_load = st.columns(2)
        with col_rst:
            if st.button("Clear", use_container_width=True):
                st.session_state["rfq_lines"] = None
                st.session_state["rfq_filename"] = None
                st.session_state["match_candidates"] = None
                st.session_state["rfq_header"] = {}
                st.session_state["quotation_bytes"] = None
                st.rerun()
        with col_load:
            sample_pdf = Path("data/raw/RFQ_KBS-0147.pdf")
            if sample_pdf.exists():
                if st.button("Reload Demo", use_container_width=True):
                    with st.spinner("Reloading..."):
                        load_rfq_bytes(sample_pdf.read_bytes(), sample_pdf.name)
                        st.rerun()

    st.markdown("<hr style='margin: 16px 0; border: none; border-top: 1px solid #E2E8F0;' />", unsafe_allow_html=True)
    st.markdown(
        """
        <div style="font-size: 0.72rem; color: #94A3B8; text-align: center; line-height: 1.4;">
            Master Price Lists Active<br>
            <strong>ABB (Feb 2026) · Schneider (Apr 2026)</strong><br>
            All amounts in INR (₹)
        </div>
        """,
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------ Brand Top Banner
rfq = get_rfq()
if rfq is not None:
    fn = st.session_state.get("rfq_filename", "Customer RFQ")
    status_html = f"""
    <div class="status-pill status-pill-active">
        <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#2563EB;"></span>
        Active: {fn} ({len(rfq)} items)
    </div>
    """
else:
    status_html = """
    <div class="status-pill status-pill-idle">
        <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#94A3B8;"></span>
        No RFQ Loaded
    </div>
    """

logo_img_banner = (
    f'<img src="data:image/png;base64,{logo_b64}" style="width:70px; height:70px; border-radius:50%; box-shadow:0 2px 10px rgba(37,99,235,0.25); object-fit:contain; background:#ffffff; border:2px solid #EFF6FF;" alt="IEPCI UK Logo" />'
    if logo_b64
    else '<div class="brand-icon-box">⚡</div>'
)

st.markdown(
    f"""
    <div class="brand-banner">
        <div class="brand-left">
            {logo_img_banner}
            <div class="brand-title-wrap">
                <div class="brand-title">
                    IEPCI UK
                    <span class="brand-badge">Quote Assistant</span>
                </div>
                <div class="brand-subtitle">
                    Automated RFQ Extraction · Intelligent Switchgear Matching · INR Commercial Pricing
                </div>
            </div>
        </div>
        <div class="brand-right">
            {status_html}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# PAGE 1: DASHBOARD
# ============================================================
if current_page == "Dashboard":
    st.markdown(
        """
        <div>
            <div class="section-eyebrow">OVERVIEW & PIPELINE</div>
            <div class="section-heading">Quotation Command Center</div>
            <div class="section-description">
                Monitor RFQ lifecycle progress from raw customer document intake to finalized Excel quotation.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Compute key KPI metrics
    total_items = len(rfq) if rfq is not None else 0
    missing_codes = 0
    unapproved_prices = 0

    if rfq is not None:
        if "part_code" in rfq.columns:
            missing_codes = int(
                rfq["part_code"].fillna("").astype(str).str.strip().eq("").sum()
            )
        if "price_approved" in rfq.columns:
            unapproved_prices = int(
                (~rfq["price_approved"].fillna(False).astype(bool)).sum()
            )

    try:
        catalogue_len = len(get_catalogue())
    except Exception:
        catalogue_len = 6366

    # 4 Native KPI cards
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("RFQ Items", total_items, help="Total line items extracted from the RFQ document")
    col2.metric(
        "Missing Codes",
        missing_codes,
        delta=f"-{missing_codes} need review" if missing_codes > 0 else "All present",
        delta_color="inverse" if missing_codes > 0 else "normal",
        help="Items without a specific manufacturer part number",
    )
    col3.metric(
        "Pending Approvals",
        unapproved_prices,
        delta=f"{total_items - unapproved_prices} approved" if total_items > 0 else None,
        help="Line items that require rate confirmation before export",
    )
    col4.metric(
        "Catalogue Master",
        f"{catalogue_len:,}",
        delta="ABB & Schneider",
        help="Total indexed switchgear products available for matching",
    )

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # Workflow Stepper Graphic
    s1_class = "done" if rfq is not None else "active"
    s1_num = "✓" if rfq is not None else "1"
    s1_desc = f"{total_items} items extracted" if rfq is not None else "Upload file"

    s2_class = "done" if (rfq is not None and missing_codes == 0) else ("active" if (rfq is not None and missing_codes > 0) else "idle")
    s2_num = "✓" if (rfq is not None and missing_codes == 0) else "2"
    s2_desc = f"{missing_codes} require lookup" if (rfq is not None and missing_codes > 0) else ("Matched" if rfq is not None else "Pending intake")

    approved_count = total_items - unapproved_prices
    s3_class = "done" if (rfq is not None and unapproved_prices == 0 and total_items > 0) else ("active" if (rfq is not None) else "idle")
    s3_num = "✓" if (rfq is not None and unapproved_prices == 0 and total_items > 0) else "3"
    s3_desc = f"{approved_count}/{total_items} confirmed" if rfq is not None else "Pending matching"

    quote_ready = st.session_state.get("quotation_bytes") is not None
    s4_class = "done" if quote_ready else "idle"
    s4_num = "✓" if quote_ready else "4"
    s4_desc = "Excel Draft Ready" if quote_ready else "Pending pricing"

    st.markdown(
        f"""
        <div class="workflow-stepper">
            <div class="stepper-card {s1_class}">
                <div class="stepper-num">{s1_num}</div>
                <div class="stepper-text">
                    <span class="stepper-title">1. RFQ Intake</span>
                    <span class="stepper-status">{s1_desc}</span>
                </div>
            </div>
            <div class="stepper-card {s2_class}">
                <div class="stepper-num">{s2_num}</div>
                <div class="stepper-text">
                    <span class="stepper-title">2. Part Matching</span>
                    <span class="stepper-status">{s2_desc}</span>
                </div>
            </div>
            <div class="stepper-card {s3_class}">
                <div class="stepper-num">{s3_num}</div>
                <div class="stepper-text">
                    <span class="stepper-title">3. Pricing Approval</span>
                    <span class="stepper-status">{s3_desc}</span>
                </div>
            </div>
            <div class="stepper-card {s4_class}">
                <div class="stepper-num">{s4_num}</div>
                <div class="stepper-text">
                    <span class="stepper-title">4. Quotation Export</span>
                    <span class="stepper-status">{s4_desc}</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Empty State vs Populated Dashboard
    if rfq is None:
        logo_empty = (
            f'<img src="data:image/png;base64,{logo_b64}" style="width:72px; height:72px; border-radius:50%; box-shadow:0 4px 14px rgba(37,99,235,0.18); margin-bottom:14px; object-fit:contain; background:#ffffff; border:2px solid #EFF6FF;" alt="IEPCI UK Logo" />'
            if logo_b64
            else '<div style="font-size: 2.8rem; margin-bottom: 12px;">📑</div>'
        )
        st.markdown(
            f"""
            <div class="ui-card" style="text-align: center; padding: 40px 20px;">
                {logo_empty}
                <div style="font-size: 1.25rem; font-weight: 800; color: #0F2942; margin-bottom: 8px;">
                    No Active RFQ Loaded
                </div>
                <div style="max-width: 540px; margin: 0 auto 24px auto; color: #64748B; font-size: 0.92rem; line-height: 1.5;">
                    Get started by uploading a customer RFQ file (PDF, Excel, or Word) in 
                    <strong>RFQ Analysis</strong>, or click below to load the bundled test RFQ to explore the app.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_c1, col_c2, col_c3 = st.columns([1, 1.5, 1])
        with col_c2:
            sample_pdf = Path("data/raw/RFQ_KBS-0147.pdf")
            if sample_pdf.exists():
                if st.button("⚡ Load Demo RFQ (KBS-0147.pdf)", type="primary", use_container_width=True):
                    with st.spinner("Loading demo RFQ..."):
                        load_rfq_bytes(sample_pdf.read_bytes(), sample_pdf.name)
                        st.rerun()

    else:
        # Loaded RFQ Summary Card
        hdr = st.session_state.get("rfq_header", {})
        customer = hdr.get("customer_name") or "Unspecified Customer"
        rfq_no = hdr.get("rfq_number") or "N/A"
        due = hdr.get("due_date") or "N/A"
        project = hdr.get("project") or "Standard Supply"

        st.markdown(
            f"""
            <div class="ui-card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <div class="ui-card-title">📋 Active RFQ Profile</div>
                    <span class="status-pill status-pill-active">Document: {st.session_state.get('rfq_filename')}</span>
                </div>
                <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:16px; background:#F8FAFC; border:1px solid #E2E8F0; border-radius:10px; padding:14px 18px;">
                    <div>
                        <div style="font-size:0.75rem; color:#64748B; font-weight:600; text-transform:uppercase;">Customer</div>
                        <div style="font-size:0.95rem; font-weight:700; color:#0F2942;">{customer}</div>
                    </div>
                    <div>
                        <div style="font-size:0.75rem; color:#64748B; font-weight:600; text-transform:uppercase;">RFQ Reference</div>
                        <div style="font-size:0.95rem; font-weight:700; color:#0F2942;">{rfq_no}</div>
                    </div>
                    <div>
                        <div style="font-size:0.75rem; color:#64748B; font-weight:600; text-transform:uppercase;">Due Date</div>
                        <div style="font-size:0.95rem; font-weight:700; color:#0F2942;">{due}</div>
                    </div>
                    <div>
                        <div style="font-size:0.75rem; color:#64748B; font-weight:600; text-transform:uppercase;">Project</div>
                        <div style="font-size:0.95rem; font-weight:700; color:#0F2942;">{project}</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <div style="font-size:1.05rem; font-weight:700; color:#0F2942;">Extracted Items Summary</div>
                <span style="font-size:0.8rem; color:#64748B;">Use the tabs in the left sidebar to edit items, match codes, or approve rates.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Clean preview table
        display_rfq = rfq.copy()
        st.dataframe(
            display_rfq,
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# PAGE 2: RFQ ANALYSIS
# ============================================================
elif current_page == "RFQ Analysis":
    st.markdown(
        """
        <div>
            <div class="section-eyebrow">STEP 1 · DOCUMENT INTAKE</div>
            <div class="section-heading">Upload & Review RFQ</div>
            <div class="section-description">
                Extract tabular line items and header metadata from PDF, Excel, or Word documents.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Upload Container Card
    st.markdown(
        """
        <div class="ui-card">
            <div class="ui-card-title">📤 Select RFQ Document</div>
            <div class="ui-card-subtitle">Supported formats: PDF (.pdf), Excel (.xlsx, .xls), Word (.docx)</div>
        """,
        unsafe_allow_html=True,
    )

    uploaded_file = st.file_uploader(
        "Upload customer RFQ file",
        type=["pdf", "xlsx", "xls", "docx"],
        label_visibility="collapsed",
    )

    col_up1, col_up2 = st.columns([1, 1])
    with col_up1:
        if uploaded_file and st.button("🚀 Extract RFQ Items from Upload", type="primary", use_container_width=True):
            with st.spinner("Extracting line items and document headers..."):
                try:
                    success = load_rfq_bytes(uploaded_file.getvalue(), uploaded_file.name)
                    if success:
                        st.success(f"Successfully extracted {len(st.session_state['rfq_lines'])} items from {uploaded_file.name}!")
                        st.rerun()
                    else:
                        st.warning("No line items were found in the uploaded file.")
                except Exception as error:
                    st.error(f"Extraction failed: {error}")

    with col_up2:
        sample_pdf = Path("data/raw/RFQ_KBS-0147.pdf")
        if sample_pdf.exists():
            if st.button("⚡ Or Load Test Sample RFQ (RFQ_KBS-0147.pdf)", use_container_width=True):
                with st.spinner("Extracting sample RFQ..."):
                    load_rfq_bytes(sample_pdf.read_bytes(), sample_pdf.name)
                    st.success("Sample RFQ extracted successfully!")
                    st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    rfq = get_rfq()

    if rfq is not None:
        st.markdown(
            f"""
            <div class="ui-card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <div>
                        <div class="ui-card-title">📝 Extracted Line Items ({len(rfq)} lines)</div>
                        <div class="ui-card-subtitle">Review extracted text and correct any errors directly in the table below.</div>
                    </div>
                </div>
            """,
            unsafe_allow_html=True,
        )

        edited = st.data_editor(
            rfq,
            key="rfq_editor",
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
        )

        col_save, _ = st.columns([1, 3])
        with col_save:
            if st.button("💾 Save Line Item Corrections", type="primary", use_container_width=True):
                st.session_state["rfq_lines"] = prepare_rfq(edited)
                st.session_state.pop("match_candidates", None)
                st.session_state.pop("quotation_bytes", None)
                st.success("RFQ lines updated successfully.")

        st.markdown("</div>", unsafe_allow_html=True)

        # Header / Customer Details Card
        st.markdown(
            """
            <div class="ui-card">
                <div class="ui-card-title">🏢 Customer & Tender Details</div>
                <div class="ui-card-subtitle">
                    These parameters are automatically embedded into the final quotation header.
                </div>
            """,
            unsafe_allow_html=True,
        )

        header = st.session_state.get("rfq_header", {})
        left, right = st.columns(2)

        # Customer Profile group
        with left:
            st.markdown("<div style='font-weight:700; color:#1E3A8A; font-size:0.9rem; margin-bottom:12px;'>👤 Customer Contact Profile</div>", unsafe_allow_html=True)
            for key, label in HEADER_FIELDS[:5]:
                header[key] = st.text_input(
                    label,
                    value=header.get(key, ""),
                    key=f"hdr_{key}",
                )

        # Tender Reference group
        with right:
            st.markdown("<div style='font-weight:700; color:#1E3A8A; font-size:0.9rem; margin-bottom:12px;'>📋 Tender & Commercial References</div>", unsafe_allow_html=True)
            for key, label in HEADER_FIELDS[5:]:
                header[key] = st.text_input(
                    label,
                    value=header.get(key, ""),
                    key=f"hdr_{key}",
                )

        st.session_state["rfq_header"] = header
        st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# PAGE 3: PRODUCT MATCHING
# ============================================================
elif current_page == "Product Matching":
    st.markdown(
        """
        <div>
            <div class="section-eyebrow">STEP 2 · IDENTIFICATION</div>
            <div class="section-heading">Product & Part-Code Matching</div>
            <div class="section-description">
                Identify manufacturer catalogue numbers for RFQ items with missing or incomplete part specifications.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    rfq = get_rfq()

    if rfq is None:
        st.markdown(
            """
            <div class="callout-blue">
                <span style="font-size: 1.3rem;">ℹ️</span>
                <div>
                    <strong>No RFQ items available.</strong><br>
                    Please upload an RFQ in <strong>RFQ Analysis</strong> first.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        missing_df = pd.DataFrame()
        if "part_code" in rfq.columns:
            missing_df = rfq[rfq["part_code"].fillna("").astype(str).str.strip().eq("")]

        col_m1, col_m2 = st.columns([1, 2])
        with col_m1:
            st.metric(
                "Missing Part Codes",
                len(missing_df),
                delta="Needs Match" if len(missing_df) > 0 else "All Provided",
                delta_color="inverse" if len(missing_df) > 0 else "normal",
            )

        with col_m2:
            st.markdown(
                """
                <div class="callout-blue" style="margin-top:0;">
                    <div>
                        <strong>Air Circuit Breaker (ACB) Matching Engine</strong><br>
                        The matching algorithm compares rated current (A), poles, breaking capacity, and release type 
                        against the 6,366 master catalogue records.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if not missing_df.empty:
            st.markdown("<div style='font-weight:700; color:#0F2942; margin: 12px 0 8px 0;'>Items Requiring Verification:</div>", unsafe_allow_html=True)
            cols_to_show = [c for c in ["line_no", "make", "description", "qty", "unit"] if c in missing_df.columns]
            st.dataframe(missing_df[cols_to_show], use_container_width=True, hide_index=True)

        if st.button("🔍 Search Supplier Catalogues for Candidates", type="primary"):
            try:
                with st.spinner("Analyzing ratings, poles, breaking capacity and frame sizes..."):
                    candidates = find_missing_code_candidates(rfq)
                st.session_state["match_candidates"] = candidates
                st.success(f"Matched {len(candidates)} candidate options across missing lines.")
            except Exception as error:
                st.error(f"Matching failed: {error}")

        candidates = st.session_state.get("match_candidates")

        if candidates is not None:
            results = pd.DataFrame(candidates)

            if results.empty:
                st.warning("No candidate records found. Supplier technical inquiry recommended.")
            else:
                st.markdown(
                    """
                    <div class="callout-amber">
                        <span style="font-size: 1.3rem;">⚠️</span>
                        <div>
                            <strong>Engineering Verification Required:</strong><br>
                            Candidate records are algorithmic suggestions. Confirm exact accessory configurations, 
                            release types, and dimensions prior to formal quotation.
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                for line_no, group in results.groupby("line_no", sort=False):
                    desc = group.iloc[0].get("rfq_description", "RFQ Item") if "rfq_description" in group.columns else ""
                    st.markdown(
                        f"""
                        <div class="ui-card" style="margin-bottom: 16px;">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                                <div style="font-weight:800; font-size:1.05rem; color:#1E3A8A;">
                                    RFQ Line #{line_no}
                                </div>
                                <span class="brand-badge">ACB Specification Match</span>
                            </div>
                            <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:10px 14px; font-size:0.85rem; color:#334155; margin-bottom:14px;">
                                <strong>RFQ Requirement:</strong> {desc}
                            </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    columns = [
                        "rank",
                        "score",
                        "part_code",
                        "candidate_description",
                        "price",
                        "supporting_details",
                        "checks_needed",
                        "decision",
                    ]

                    st.dataframe(
                        group[[c for c in columns if c in group.columns]],
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# PAGE 4: SUPPLIER CATALOGUE
# ============================================================
elif current_page == "Supplier Catalogue":
    st.markdown(
        """
        <div>
            <div class="section-eyebrow">REFERENCE DATABASE</div>
            <div class="section-heading">Master Supplier Catalogue</div>
            <div class="section-description">
                Search and explore 6,366+ pre-indexed switchgear items from ABB (Feb 2026) and Schneider Electric (Apr 2026).
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        catalogue = get_catalogue()

        # Catalogue KPIs
        abb_count = (catalogue["supplier"].str.upper() == "ABB").sum() if "supplier" in catalogue.columns else 0
        sch_count = (catalogue["supplier"].str.upper().str.contains("SCHNEIDER")).sum() if "supplier" in catalogue.columns else 0
        priced_count = catalogue["price_inr"].notna().sum() if "price_inr" in catalogue.columns else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Catalogue Items", f"{len(catalogue):,}")
        c2.metric("ABB Products", f"{abb_count:,}")
        c3.metric("Schneider Products", f"{sch_count:,}")
        c4.metric("Priced Records", f"{priced_count:,}")

        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

        # Filter & Search Card
        st.markdown(
            """
            <div class="ui-card">
                <div class="ui-card-title">🔍 Filter & Search Master Records</div>
            """,
            unsafe_allow_html=True,
        )

        col_f1, col_f2, col_f3 = st.columns([1, 1, 2])

        suppliers = ["All Suppliers"]
        if "supplier" in catalogue.columns:
            suppliers += sorted(catalogue["supplier"].dropna().astype(str).unique().tolist())

        with col_f1:
            selected_supplier = st.selectbox("Manufacturer", suppliers)

        with col_f2:
            price_filter = st.selectbox("Price Status", ["All Items", "Priced Only (INR)", "Price on Inquiry"])

        with col_f3:
            search = st.text_input(
                "Search part code or description",
                placeholder="e.g. AF26-30-00, NSX400, 400A...",
            )

        st.markdown("</div>", unsafe_allow_html=True)

        # Apply Filters
        filtered = catalogue.copy()
        if selected_supplier != "All Suppliers":
            filtered = filtered[filtered["supplier"].astype(str) == selected_supplier]

        if price_filter == "Priced Only (INR)":
            filtered = filtered[filtered["price_inr"].notna()]
        elif price_filter == "Price on Inquiry":
            filtered = filtered[filtered["price_inr"].isna()]

        if search.strip():
            searchable = filtered.fillna("").astype(str)
            mask = searchable.apply(
                lambda col: col.str.contains(search.strip(), case=False, regex=False)
            ).any(axis=1)
            filtered = filtered[mask]

        st.markdown(
            f"""
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size:0.88rem; font-weight:700; color:#1E3A8A;">
                    Showing {len(filtered):,} matching records
                </span>
                <span style="font-size:0.78rem; color:#64748B;">
                    (Display limited to top 500 for optimal performance)
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        display_columns = [
            "supplier",
            "part_code",
            "description",
            "price_inr",
            "price_status",
            "rating_a",
            "poles",
            "breaking_capacity",
        ]
        display_columns = [c for c in display_columns if c in filtered.columns]

        st.dataframe(
            filtered[display_columns].head(500),
            use_container_width=True,
            hide_index=True,
            column_config={
                "price_inr": st.column_config.NumberColumn(
                    "List Price (INR ₹)",
                    format="₹ %.2f",
                ),
                "part_code": st.column_config.TextColumn("Part Code"),
                "supplier": st.column_config.TextColumn("Manufacturer"),
            },
        )

    except Exception as error:
        st.error(f"Could not load supplier catalogue: {error}")


# ============================================================
# PAGE 5: PRICING & QUOTATION
# ============================================================
elif current_page == "Pricing & Quotation":
    st.markdown(
        """
        <div>
            <div class="section-eyebrow">STEP 3 · COMMERCIAL PRICING & EXPORT</div>
            <div class="section-heading">Pricing Review & Excel Quotation</div>
            <div class="section-description">
                Apply supplier list prices (INR MRP), review individual rates, and export the official Excel quotation draft.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    rfq = get_rfq()

    if rfq is None:
        st.markdown(
            """
            <div class="callout-blue">
                <span style="font-size: 1.3rem;">ℹ️</span>
                <div>
                    <strong>No RFQ items available for pricing.</strong><br>
                    Please upload an RFQ in <strong>RFQ Analysis</strong> first.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # Load Catalogue and Suggestions
        helper_columns = ["list_price_inr", "price_note"]
        base = prepare_rfq(rfq).drop(columns=helper_columns, errors="ignore")
        catalogue = get_catalogue()
        suggestions = suggest_list_prices(base, catalogue)

        table = base.copy()
        table["list_price_inr"] = suggestions["list_price_inr"].to_numpy()
        table["price_note"] = suggestions["price_note"].to_numpy()

        preferred = [
            "line_no", "description", "make", "part_code", "qty", "unit",
            "list_price_inr", "price_note", "unit_rate", "price_approved",
        ]
        table = table[
            [c for c in preferred if c in table.columns]
            + [c for c in table.columns if c not in preferred]
        ]

        # Calculate live commercial totals for approved items
        approved_mask = table["price_approved"].fillna(False).astype(bool)
        approved_count = int(approved_mask.sum())
        total_items = len(table)
        approved_pct = int(approved_count / total_items * 100) if total_items > 0 else 0

        qty_series = pd.to_numeric(table["qty"], errors="coerce").fillna(1)
        rate_series = pd.to_numeric(table["unit_rate"], errors="coerce").fillna(0)
        line_totals = qty_series * rate_series
        approved_subtotal = float(line_totals[approved_mask].sum())
        gst_amount = approved_subtotal * 0.18
        total_with_tax = approved_subtotal + gst_amount

        # Commercial Live Financial Banner
        st.markdown(
            f"""
            <div class="commercial-grid">
                <div class="commercial-card">
                    <div class="commercial-label">Approval Coverage</div>
                    <div class="commercial-val">{approved_count} / {total_items}</div>
                    <div class="commercial-sub">{approved_pct}% of lines approved</div>
                </div>
                <div class="commercial-card highlight">
                    <div class="commercial-label">Net Subtotal (INR)</div>
                    <div class="commercial-val">₹ {approved_subtotal:,.2f}</div>
                    <div class="commercial-sub">Approved line rates</div>
                </div>
                <div class="commercial-card">
                    <div class="commercial-label">Estimated GST (18%)</div>
                    <div class="commercial-val">₹ {gst_amount:,.2f}</div>
                    <div class="commercial-sub">Standard tax liability</div>
                </div>
                <div class="commercial-card total">
                    <div class="commercial-label">Total Quotation Value</div>
                    <div class="commercial-val" style="color:#1D4ED8;">₹ {total_with_tax:,.2f}</div>
                    <div class="commercial-sub">Gross (Net + GST)</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Quick Action Box
        st.markdown(
            """
            <div class="ui-card" style="padding:16px 20px; margin-bottom:16px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div style="font-weight:700; color:#0F2942; font-size:0.95rem;">
                            ⚡ Auto-Populate Supplier List Prices
                        </div>
                        <div style="font-size:0.8rem; color:#64748B;">
                            Fills the approved rate for all exact part-code matches from the master price list.
                            Manually entered rates are preserved.
                        </div>
                    </div>
            """,
            unsafe_allow_html=True,
        )

        col_btn, _ = st.columns([1.5, 3])
        with col_btn:
            if st.button("Apply Supplier List Prices as Rates", type="primary", use_container_width=True):
                st.session_state["rfq_lines"] = apply_list_prices(base, catalogue)
                st.session_state.pop("pricing_editor", None)
                st.session_state.pop("quotation_bytes", None)
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

        # Pricing Review Data Editor
        st.markdown(
            """
            <div class="ui-card">
                <div class="ui-card-title">📝 Line Item Pricing & Approval Review</div>
                <div class="ui-card-subtitle">
                    Rates are only included in the final quotation when marked <strong>Rate approved</strong>.
                </div>
            """,
            unsafe_allow_html=True,
        )

        edited = st.data_editor(
            table,
            key="pricing_editor",
            use_container_width=True,
            hide_index=True,
            disabled=helper_columns,
            column_config={
                "line_no": st.column_config.TextColumn("Line", width="small"),
                "list_price_inr": st.column_config.NumberColumn(
                    "Supplier List Price (INR)",
                    format="₹ %.2f",
                ),
                "price_note": st.column_config.TextColumn("Price Source & Notes"),
                "unit_rate": st.column_config.NumberColumn(
                    "Approved Unit Rate (INR)",
                    min_value=0.0,
                    format="₹ %.2f",
                ),
                "price_approved": st.column_config.CheckboxColumn(
                    "Rate Approved"
                ),
            },
        )
        edited = edited.drop(columns=helper_columns, errors="ignore")

        col_s1, _ = st.columns([1, 3])
        with col_s1:
            if st.button("💾 Save Rate Changes", use_container_width=True):
                st.session_state["rfq_lines"] = prepare_rfq(edited)
                st.session_state.pop("quotation_bytes", None)
                st.success("Pricing review saved.")

        st.markdown("</div>", unsafe_allow_html=True)

        # Generate Quotation Card
        st.markdown(
            """
            <div class="ui-card">
                <div class="ui-card-title">📊 Official Quotation Generation</div>
                <div class="ui-card-subtitle">
                    Populates the official IEPCI Quotation template (.xlsx) with approved line items, commercial values, and customer header.
                </div>
            """,
            unsafe_allow_html=True,
        )

        col_g1, col_g2 = st.columns([1, 2])
        with col_g1:
            if st.button("⚡ Generate Official Excel Draft", type="primary", use_container_width=True):
                try:
                    with st.spinner("Generating quotation from IEPCI template..."):
                        reviewed = prepare_rfq(edited)

                        with TemporaryDirectory() as temp_dir:
                            output_path = Path(temp_dir) / "IEPCI_Quotation_DRAFT.xlsx"

                            generate_quotation(
                                output_path=output_path,
                                rfq_df=reviewed,
                                header=st.session_state.get("rfq_header"),
                            )

                            st.session_state["quotation_bytes"] = output_path.read_bytes()

                        st.success("Excel draft quotation generated successfully!")

                except Exception as error:
                    st.error(f"Quotation generation failed: {error}")

        quotation_bytes = st.session_state.get("quotation_bytes")

        if quotation_bytes:
            st.markdown(
                f"""
                <div style="background:#ECFDF5; border:1px solid #A7F3D0; border-radius:10px; padding:16px 20px; margin-top:16px; display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div style="font-weight:800; color:#065F46; font-size:1rem;">
                            ✅ IEPCI_Quotation_DRAFT.xlsx Ready for Download
                        </div>
                        <div style="font-size:0.8rem; color:#047857; margin-top:2px;">
                            Official format with formulas, GST calculation, and header references ({len(quotation_bytes):,} bytes).
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.download_button(
                "📥 Download Final Excel Quotation",
                data=quotation_bytes,
                file_name="IEPCI_Quotation_DRAFT.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)
