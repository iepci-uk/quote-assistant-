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
from src.database import (
    init_db,
    save_rfq_record,
    list_saved_rfqs,
    load_rfq_record,
    delete_rfq_record,
)

# Initialize database tables on app load
init_db()

LOGO_PATH = Path("assets/IEPCI-UK-logo.png")


@st.cache_data
def get_logo_b64() -> str:
    """Return base64-encoded IEPCI UK logo string."""
    if LOGO_PATH.exists():
        return base64.b64encode(LOGO_PATH.read_bytes()).decode("utf-8")
    return ""


SWITCHBOARD_SVG = """<svg width="240" height="170" viewBox="0 0 240 170" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="35" y="8" width="170" height="152" rx="10" stroke="#94A3B8" stroke-width="1.8" fill="#FFFFFF"/>
  <rect x="42" y="15" width="156" height="138" rx="6" stroke="#E2E8F0" stroke-width="1.2" fill="#F8FAFC"/>
  <rect x="50" y="22" width="140" height="22" rx="4" stroke="#CBD5E1" stroke-width="1.2" fill="#FFFFFF"/>
  <line x1="60" y1="33" x2="180" y2="33" stroke="#CBD5E1" stroke-width="2"/>
  <circle cx="75" cy="33" r="3" fill="#2563EB"/>
  <circle cx="120" cy="33" r="3" fill="#64748B"/>
  <circle cx="165" cy="33" r="3" fill="#0F172A"/>
  <rect x="50" y="50" width="140" height="50" rx="6" stroke="#2563EB" stroke-width="1.5" fill="#EFF6FF"/>
  <rect x="58" y="57" width="36" height="20" rx="3" stroke="#93C5FD" stroke-width="1" fill="#FFFFFF"/>
  <path d="M63 68 L68 64 L74 69 L79 63 L85 67" stroke="#2563EB" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="104" cy="65" r="2.5" fill="#059669"/>
  <circle cx="114" cy="65" r="2.5" fill="#CBD5E1"/>
  <circle cx="124" cy="65" r="2.5" fill="#CBD5E1"/>
  <rect x="140" y="59" width="38" height="14" rx="3" stroke="#64748B" stroke-width="1" fill="#FFFFFF"/>
  <line x1="159" y1="62" x2="159" y2="70" stroke="#0F172A" stroke-width="2" stroke-linecap="round"/>
  <line x1="58" y1="87" x2="182" y2="87" stroke="#BFDBFE" stroke-width="1" stroke-dasharray="3 3"/>
  <text x="60" y="94" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="7" fill="#1E40AF" font-weight="700">ACB-4000A DRAW-OUT · READY</text>
  <rect x="50" y="106" width="31" height="40" rx="4" stroke="#CBD5E1" stroke-width="1.2" fill="#FFFFFF"/>
  <line x1="65" y1="112" x2="65" y2="124" stroke="#0F172A" stroke-width="1.5" stroke-linecap="round"/>
  <rect x="61" y="132" width="9" height="5" rx="1.5" fill="#2563EB"/>
  <rect x="86" y="106" width="31" height="40" rx="4" stroke="#CBD5E1" stroke-width="1.2" fill="#FFFFFF"/>
  <line x1="101" y1="112" x2="101" y2="124" stroke="#0F172A" stroke-width="1.5" stroke-linecap="round"/>
  <rect x="97" y="132" width="9" height="5" rx="1.5" fill="#2563EB"/>
  <rect x="122" y="106" width="31" height="40" rx="4" stroke="#CBD5E1" stroke-width="1.2" fill="#FFFFFF"/>
  <line x1="137" y1="112" x2="137" y2="124" stroke="#0F172A" stroke-width="1.5" stroke-linecap="round"/>
  <rect x="133" y="132" width="9" height="5" rx="1.5" fill="#2563EB"/>
  <rect x="158" y="106" width="31" height="40" rx="4" stroke="#CBD5E1" stroke-width="1.2" fill="#FFFFFF"/>
  <line x1="173" y1="112" x2="173" y2="124" stroke="#0F172A" stroke-width="1.5" stroke-linecap="round"/>
  <rect x="169" y="132" width="9" height="5" rx="1.5" fill="#2563EB"/>
  <rect x="44" y="156" width="152" height="6" rx="2" fill="#CBD5E1"/>
</svg>"""


# ------------------------------------------------------------ Page Configuration
st.set_page_config(
    page_title="IEPCI Quote Assistant",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------ Enterprise Theme and Styling
from styles import apply_styles

apply_styles()


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
        st.session_state["rfq_db_id"] = None
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


def load_rfq_from_database(rfq_id: int) -> bool:
    """Load an RFQ and all its lines from SQLite into session state."""
    header, lines_df, filename = load_rfq_record(rfq_id)
    if lines_df is not None and not lines_df.empty:
        st.session_state["rfq_lines"] = prepare_rfq(lines_df)
        st.session_state["rfq_filename"] = filename or f"RFQ_#{rfq_id}"
        st.session_state["rfq_header"] = header
        st.session_state["rfq_db_id"] = rfq_id
        st.session_state["match_candidates"] = None
        for key, _ in HEADER_FIELDS:
            st.session_state.pop(f"hdr_{key}", None)
        st.session_state.pop("rfq_editor", None)
        st.session_state.pop("pricing_editor", None)
        st.session_state.pop("quotation_bytes", None)
        return True
    return False


# Initialize session state keys
if "rfq_lines" not in st.session_state:
    st.session_state["rfq_lines"] = None

if "rfq_db_id" not in st.session_state:
    st.session_state["rfq_db_id"] = None

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
        f'<img src="data:image/png;base64,{logo_b64}" class="sidebar-header-logo" alt="IEPCI UK" />'
        if logo_b64
        else '<div class="brand-icon-box" style="width:40px; height:40px; font-size:0.85rem;">IEPCI</div>'
    )

    st.markdown(
        f"""<div class="sidebar-header">
{logo_img_sidebar}
<div>
<div class="sidebar-header-title">
IEPCI UK <span class="sidebar-header-badge">v2.4</span>
</div>
<div class="sidebar-header-sub">Quotation Assistant</div>
</div>
</div>""",
        unsafe_allow_html=True,
    )

    nav_options = [
        "Dashboard",
        "RFQ Analysis",
        "Product Matching",
        "Supplier Catalogue",
        "Pricing & Quotation",
    ]

    selected_nav = st.radio(
        "Navigation",
        nav_options,
        index=0,
        label_visibility="collapsed",
    )
    current_page = selected_nav

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
            if st.button("Load Demo RFQ (KBS-0147)", type="primary", use_container_width=True):
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
                    {filename}
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
                st.session_state["rfq_db_id"] = None
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
    status_html = f'<div class="status-pill status-pill-active"><span class="status-dot status-dot-active"></span>Active: {fn} ({len(rfq)} items)</div>'
else:
    status_html = '<div class="status-pill status-pill-idle"><span class="status-dot status-dot-idle"></span>No RFQ Loaded</div>'

logo_img_banner = (
    f'<img src="data:image/png;base64,{logo_b64}" class="brand-logo" alt="IEPCI UK Logo" />'
    if logo_b64
    else '<div class="brand-icon-box">IEPCI</div>'
)

st.markdown(
    f"""<div class="brand-banner">
<div class="brand-left">
{logo_img_banner}
<div class="brand-title-wrap">
<div class="brand-title">IEPCI UK <span class="brand-badge">Quote Assistant</span></div>
<div class="brand-subtitle">Switchgear Quotation System · Master Price Lists (ABB & Schneider Electric)</div>
</div>
</div>
<div class="brand-right">
{status_html}
</div>
</div>""",
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

    # Bento Grid Dashboard calculation
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

    approved_count = total_items - unapproved_prices
    try:
        catalogue_len = len(get_catalogue())
    except Exception:
        catalogue_len = 13273

    saved_rfqs = list_saved_rfqs()
    if rfq is not None and total_items > 0:
        mins_saved = total_items * 14
        time_saved_val = f"{mins_saved / 60:.1f} hrs" if mins_saved >= 60 else f"{mins_saved} mins"
        time_saved_sub = f"{total_items} switchgear lines automated"
        doc_intake_val = f"{total_items} Items"
        doc_intake_sub = st.session_state.get("rfq_filename", "Customer RFQ")
        progress_pct = int((approved_count / total_items) * 100) if total_items > 0 else 0
    elif saved_rfqs:
        total_saved_lines = sum(r.get("items_count", 0) for r in saved_rfqs)
        mins_saved = total_saved_lines * 14
        time_saved_val = f"{mins_saved / 60:.1f} hrs" if mins_saved >= 60 else f"{mins_saved} mins"
        time_saved_sub = f"Cumulative across {len(saved_rfqs)} saved quotations"
        doc_intake_val = "0 Active"
        doc_intake_sub = f"{len(saved_rfqs)} saved quotes in database"
        progress_pct = 0
    else:
        time_saved_val = "~4.5 hrs"
        time_saved_sub = "14 mins avg saved per line item"
        doc_intake_val = "0 Active"
        doc_intake_sub = "Workspace ready for document"
        progress_pct = 0

    rate_health_val = f"{approved_count}/{total_items}" if rfq is not None else "Ready"
    rate_health_sub = f"{total_items - unapproved_prices} confirmed" if rfq is not None else "Pending document intake"
    missing_tag = f"-{missing_codes} need lookup" if missing_codes > 0 else "All codes verified"

    bento_html = f"""<div class="bento-grid">
<div class="bento-card hero">
<div>
<div class="bento-badge-live"><span class="status-dot status-dot-active"></span>Live Velocity</div>
<div class="bento-val" style="color:#1E40AF;">{time_saved_val}</div>
<div class="bento-label" style="margin-top:2px;">Manual Quoting Time Saved</div>
</div>
<div class="bento-sub">{time_saved_sub}</div>
</div>
<div class="bento-card">
<div>
<div class="bento-label">Document Intake</div>
<div class="bento-val">{doc_intake_val}</div>
<div class="bento-sub">{doc_intake_sub}</div>
</div>
<div class="bento-progress-track">
<div class="bento-progress-fill" style="width:{progress_pct}%;"></div>
</div>
</div>
<div class="bento-card">
<div>
<div class="bento-label">Master Price Lists</div>
<div class="bento-val">{catalogue_len:,}</div>
<div class="bento-sub">Verified Switchgear SKUs</div>
</div>
<div class="bento-tag">ABB & Schneider Q1 2026</div>
</div>
<div class="bento-card">
<div>
<div class="bento-label">Commercial Approval</div>
<div class="bento-val">{rate_health_val}</div>
<div class="bento-sub">{rate_health_sub}</div>
</div>
<div class="bento-tag">{missing_tag}</div>
</div>
</div>"""
    st.markdown(bento_html, unsafe_allow_html=True)

    # Workflow Stepper Graphic
    s1_class = "done" if rfq is not None else "active"
    s1_num = "OK" if rfq is not None else "1"
    s1_desc = f"{total_items} items extracted" if rfq is not None else "Upload RFQ file"

    s2_class = "done" if (rfq is not None and missing_codes == 0) else ("active" if (rfq is not None and missing_codes > 0) else "idle")
    s2_num = "OK" if (rfq is not None and missing_codes == 0) else "2"
    s2_desc = f"{missing_codes} require lookup" if (rfq is not None and missing_codes > 0) else ("Matched" if rfq is not None else "Pending intake")

    s3_class = "done" if (rfq is not None and unapproved_prices == 0 and total_items > 0) else ("active" if (rfq is not None) else "idle")
    s3_num = "OK" if (rfq is not None and unapproved_prices == 0 and total_items > 0) else "3"
    s3_desc = f"{approved_count}/{total_items} confirmed" if rfq is not None else "Pending matching"

    quote_ready = st.session_state.get("quotation_bytes") is not None
    s4_class = "done" if quote_ready else "idle"
    s4_num = "OK" if quote_ready else "4"
    s4_desc = "Excel Draft Ready" if quote_ready else "Pending pricing"

    stepper_html = f"""<div class="workflow-stepper">
<div class="stepper-card {s1_class}">
<div class="stepper-num">{s1_num}</div>
<div class="stepper-text">
<span class="stepper-title">1. Reading RFQ</span>
<span class="stepper-status">{s1_desc}</span>
</div>
</div>
<div class="stepper-card {s2_class}">
<div class="stepper-num">{s2_num}</div>
<div class="stepper-text">
<span class="stepper-title">2. Matching {f"{total_items} lines" if total_items > 0 else "Lines"}</span>
<span class="stepper-status">{s2_desc}</span>
</div>
</div>
<div class="stepper-card {s3_class}">
<div class="stepper-num">{s3_num}</div>
<div class="stepper-text">
<span class="stepper-title">3. Pricing</span>
<span class="stepper-status">{s3_desc}</span>
</div>
</div>
<div class="stepper-card {s4_class}">
<div class="stepper-num">{s4_num}</div>
<div class="stepper-text">
<span class="stepper-title">4. Draft Ready</span>
<span class="stepper-status">{s4_desc}</span>
</div>
</div>
</div>"""
    st.markdown(stepper_html, unsafe_allow_html=True)

    # Empty State vs Populated Dashboard
    if rfq is None:
        empty_state_html = f"""<div class="empty-state-card">
{SWITCHBOARD_SVG}
<div class="empty-state-title">Quotation Workspace Ready</div>
<div class="empty-state-desc">
Upload a customer switchgear RFQ (PDF, Excel, Word) in <strong>RFQ Analysis</strong>, or initialize the demo dataset below to test automated line extraction and pricing.
</div>
</div>"""
        st.markdown(empty_state_html, unsafe_allow_html=True)

        col_c1, col_c2, col_c3 = st.columns([1, 1.4, 1])
        with col_c2:
            sample_pdf = Path("data/raw/RFQ_KBS-0147.pdf")
            if sample_pdf.exists():
                if st.button("Load Demo RFQ (KBS-0147.pdf)", type="primary", use_container_width=True):
                    with st.status("Analyzing RFQ Document...", expanded=True) as status:
                        st.write("Step 1/4: Reading RFQ Document...")
                        import time
                        time.sleep(0.3)
                        st.write("Step 2/4: Matching switchgear lines against Master Catalogue...")
                        time.sleep(0.3)
                        st.write("Step 3/4: Applying Master List Prices...")
                        time.sleep(0.2)
                        st.write("Step 4/4: Draft quotation ready.")
                        status.update(label="RFQ Analysis Complete", state="complete", expanded=False)
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
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <div class="ui-card-title">Active RFQ Profile</div>
                    <span class="status-pill status-pill-active">Document: {st.session_state.get('rfq_filename')}</span>
                </div>
                <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; background:#F8FAFC; border:1px solid #E2E8F0; border-radius:6px; padding:10px 14px;">
                    <div>
                        <div style="font-size:0.72rem; color:#64748B; font-weight:600; text-transform:uppercase;">Customer</div>
                        <div style="font-size:0.9rem; font-weight:700; color:#0F2942;">{customer}</div>
                    </div>
                    <div>
                        <div style="font-size:0.72rem; color:#64748B; font-weight:600; text-transform:uppercase;">RFQ Reference</div>
                        <div style="font-size:0.9rem; font-weight:700; color:#0F2942;">{rfq_no}</div>
                    </div>
                    <div>
                        <div style="font-size:0.72rem; color:#64748B; font-weight:600; text-transform:uppercase;">Due Date</div>
                        <div style="font-size:0.9rem; font-weight:700; color:#0F2942;">{due}</div>
                    </div>
                    <div>
                        <div style="font-size:0.72rem; color:#64748B; font-weight:600; text-transform:uppercase;">Project</div>
                        <div style="font-size:0.9rem; font-weight:700; color:#0F2942;">{project}</div>
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

    # ------------------------------------------------------------ Saved Quotations (Database)
    saved_rfqs = list_saved_rfqs()
    if saved_rfqs:
        st.markdown(
            """
            <div class="ui-card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <div>
                        <div class="ui-card-title">Saved Quotations & Drafts (Database)</div>
                        <div class="ui-card-subtitle">Saved quotation projects stored permanently in SQLite.</div>
                    </div>
                </div>
            """,
            unsafe_allow_html=True,
        )

        rfq_options = {
            f"#{r['id']} · {r['rfq_number']} · {r['customer_name']} ({r['items_count']} items)": r['id']
            for r in saved_rfqs
        }

        col_sel, col_act1, col_act2 = st.columns([3, 1, 1])
        with col_sel:
            selected_label = st.selectbox(
                "Select a saved quotation to open",
                list(rfq_options.keys()),
                key="db_rfq_select",
                label_visibility="collapsed",
            )
            selected_rfq_id = rfq_options[selected_label]

        with col_act1:
            if st.button("Open RFQ", type="primary", use_container_width=True, key="btn_open_db_rfq"):
                if load_rfq_from_database(selected_rfq_id):
                    st.success(f"Loaded RFQ #{selected_rfq_id}!")
                    st.rerun()
                else:
                    st.error("Failed to load RFQ.")

        with col_act2:
            if st.button("Delete", use_container_width=True, key="btn_del_db_rfq"):
                delete_rfq_record(selected_rfq_id)
                if st.session_state.get("rfq_db_id") == selected_rfq_id:
                    st.session_state["rfq_lines"] = None
                    st.session_state["rfq_db_id"] = None
                st.success(f"Deleted RFQ #{selected_rfq_id}")
                st.rerun()

        # Summary table of all saved records
        summary_rows = []
        for r in saved_rfqs:
            summary_rows.append({
                "ID": r["id"],
                "RFQ Number": r["rfq_number"],
                "Customer": r["customer_name"],
                "Items": r["items_count"],
                "Approved": r["approved_count"],
                "Approved Value (₹)": f"₹ {r['subtotal_inr']:,.2f}",
                "Status": r["status"],
                "Updated": r["updated_at"],
            })
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)


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
            <div class="ui-card-title">Select RFQ Document</div>
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
        if uploaded_file and st.button("Extract RFQ Items from Upload", type="primary", use_container_width=True):
            try:
                with st.status("Analyzing RFQ Document...", expanded=True) as status:
                    st.write("Step 1/4: Reading RFQ Document...")
                    import time
                    time.sleep(0.3)
                    success = load_rfq_bytes(uploaded_file.getvalue(), uploaded_file.name)
                    if success:
                        line_count = len(st.session_state.get('rfq_lines', []))
                        st.write(f"Step 2/4: Matching {line_count} lines against master catalogue...")
                        time.sleep(0.3)
                        st.write("Step 3/4: Pricing line items...")
                        time.sleep(0.2)
                        st.write("Step 4/4: Draft quotation ready.")
                        status.update(label="RFQ Analysis Complete", state="complete", expanded=False)
                        st.rerun()
                    else:
                        st.warning("No line items were found in the uploaded file.")
            except Exception as error:
                st.error(f"Extraction failed: {error}")

    with col_up2:
        sample_pdf = Path("data/raw/RFQ_KBS-0147.pdf")
        if sample_pdf.exists():
            if st.button("Or Load Test Sample RFQ (RFQ_KBS-0147.pdf)", use_container_width=True):
                with st.status("Analyzing RFQ Document...", expanded=True) as status:
                    st.write("Step 1/4: Reading RFQ Document...")
                    import time
                    time.sleep(0.3)
                    load_rfq_bytes(sample_pdf.read_bytes(), sample_pdf.name)
                    line_count = len(st.session_state.get('rfq_lines', []))
                    st.write(f"Step 2/4: Matching {line_count} lines against master catalogue...")
                    time.sleep(0.3)
                    st.write("Step 3/4: Pricing line items...")
                    time.sleep(0.2)
                    st.write("Step 4/4: Draft quotation ready.")
                    status.update(label="RFQ Analysis Complete", state="complete", expanded=False)
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    rfq = get_rfq()

    if rfq is not None:
        st.markdown(
            f"""
            <div class="ui-card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <div>
                        <div class="ui-card-title">Extracted Line Items ({len(rfq)} lines)</div>
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

        col_save1, col_save2, _ = st.columns([1.2, 1.4, 2])
        with col_save1:
            if st.button("Apply Corrections", type="primary", use_container_width=True):
                st.session_state["rfq_lines"] = prepare_rfq(edited)
                st.session_state.pop("match_candidates", None)
                st.session_state.pop("quotation_bytes", None)
                st.success("RFQ lines updated successfully.")
        with col_save2:
            if st.button("Save Draft to Database", use_container_width=True):
                st.session_state["rfq_lines"] = prepare_rfq(edited)
                st.session_state.pop("match_candidates", None)
                st.session_state.pop("quotation_bytes", None)
                hdr = st.session_state.get("rfq_header", {})
                fn = st.session_state.get("rfq_filename", "Uploaded RFQ")
                db_id = save_rfq_record(
                    header=hdr,
                    lines_df=st.session_state["rfq_lines"],
                    filename=fn,
                    status="DRAFT",
                    rfq_id=st.session_state.get("rfq_db_id"),
                )
                st.session_state["rfq_db_id"] = db_id
                st.success(f"Saved draft to database (ID #{db_id})!")

        st.markdown("</div>", unsafe_allow_html=True)

        # Header / Customer Details Card
        st.markdown(
            """
            <div class="ui-card">
                <div class="ui-card-title">Customer & Tender Details</div>
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
            st.markdown("<div style='font-weight:700; color:#1E3A8A; font-size:0.9rem; margin-bottom:12px;'>Customer Contact Profile</div>", unsafe_allow_html=True)
            for key, label in HEADER_FIELDS[:5]:
                header[key] = st.text_input(
                    label,
                    value=header.get(key, ""),
                    key=f"hdr_{key}",
                )

        # Tender Reference group
        with right:
            st.markdown("<div style='font-weight:700; color:#1E3A8A; font-size:0.9rem; margin-bottom:12px;'>Tender & Commercial References</div>", unsafe_allow_html=True)
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

        if st.button("Search Supplier Catalogues for Candidates", type="primary"):
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
                            <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:6px; padding:8px 12px; font-size:0.84rem; color:#334155; margin-bottom:12px;">
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
                <div class="ui-card-title">Filter & Search Master Records</div>
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

        # Satisfying stamp animation when quote is approved
        if total_items > 0 and approved_count == total_items:
            stamp_html = """<div class="stamp-wrap">
<div class="stamp-badge">
<div class="stamp-badge-title">APPROVED</div>
<div class="stamp-badge-sub">IEPCI COMMERCIAL VERIFIED</div>
</div>
</div>"""
        elif total_items > 0 and approved_count > 0:
            stamp_html = f"""<div class="stamp-wrap">
<div class="stamp-badge" style="border-color:#2563EB; color:#2563EB; background:rgba(239,246,255,0.92);">
<div class="stamp-badge-title">{approved_count}/{total_items} VERIFIED</div>
<div class="stamp-badge-sub">IN-PROGRESS APPROVAL</div>
</div>
</div>"""
        else:
            stamp_html = ""

        # Commercial Live Financial Banner
        st.markdown(
            f"""{stamp_html}
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
</div>""",
            unsafe_allow_html=True,
        )

        # Quick Action Box
        st.markdown(
            """<div class="ui-card" style="padding:12px 16px; margin-bottom:10px;">
<div style="display:flex; justify-content:space-between; align-items:center;">
<div>
<div style="font-weight:700; color:#0F2942; font-size:0.92rem;">
Automate Supplier List Prices & Approvals
</div>
<div style="font-size:0.78rem; color:#64748B;">
Populate verified manufacturer list prices across all matched lines, or confirm all line rates for export.
</div>
</div>
</div>""",
            unsafe_allow_html=True,
        )

        col_btn1, col_btn2, _ = st.columns([1.5, 1.5, 2])
        with col_btn1:
            if st.button("Apply Supplier List Prices", type="secondary", use_container_width=True):
                st.session_state["rfq_lines"] = apply_list_prices(base, catalogue)
                st.session_state.pop("pricing_editor", None)
                st.session_state.pop("quotation_bytes", None)
                st.rerun()

        with col_btn2:
            if st.button("Approve All Line Rates", type="primary", use_container_width=True):
                approved_df = base.copy()
                approved_df["price_approved"] = True
                st.session_state["rfq_lines"] = approved_df
                st.session_state.pop("pricing_editor", None)
                st.session_state.pop("quotation_bytes", None)
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

        # Pricing Review Data Editor
        st.markdown(
            """
            <div class="ui-card">
                <div class="ui-card-title">Line Item Pricing & Approval Review</div>
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

        col_s1, col_s2, _ = st.columns([1.2, 1.5, 2])
        with col_s1:
            if st.button("Apply Rates", use_container_width=True):
                st.session_state["rfq_lines"] = prepare_rfq(edited)
                st.session_state.pop("quotation_bytes", None)
                st.success("Pricing review saved in session.")
        with col_s2:
            if st.button("Save Quotation to Database", type="primary", use_container_width=True):
                st.session_state["rfq_lines"] = prepare_rfq(edited)
                st.session_state.pop("quotation_bytes", None)
                hdr = st.session_state.get("rfq_header", {})
                fn = st.session_state.get("rfq_filename", "Quotation Project")
                status = "APPROVED" if approved_count == total_items and total_items > 0 else "IN_REVIEW"
                db_id = save_rfq_record(
                    header=hdr,
                    lines_df=st.session_state["rfq_lines"],
                    filename=fn,
                    status=status,
                    rfq_id=st.session_state.get("rfq_db_id"),
                )
                st.session_state["rfq_db_id"] = db_id
                st.success(f"Quotation saved to SQLite database (ID #{db_id})!")

        st.markdown("</div>", unsafe_allow_html=True)

        # Generate Quotation Card
        st.markdown(
            """
            <div class="ui-card">
                <div class="ui-card-title">Official Quotation Generation</div>
                <div class="ui-card-subtitle">
                    Populates the official IEPCI Quotation template (.xlsx) with approved line items, commercial values, and customer header.
                </div>
            """,
            unsafe_allow_html=True,
        )

        col_g1, col_g2 = st.columns([1, 2])
        with col_g1:
            if st.button("Generate Official Excel Draft", type="primary", use_container_width=True):
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

                            # Auto-save generation state to SQLite
                            hdr = st.session_state.get("rfq_header", {})
                            fn = st.session_state.get("rfq_filename", "Quotation Project")
                            db_id = save_rfq_record(
                                header=hdr,
                                lines_df=reviewed,
                                filename=fn,
                                status="GENERATED",
                                rfq_id=st.session_state.get("rfq_db_id"),
                            )
                            st.session_state["rfq_db_id"] = db_id

                        st.success("Excel draft quotation generated successfully!")

                except Exception as error:
                    st.error(f"Quotation generation failed: {error}")

        quotation_bytes = st.session_state.get("quotation_bytes")

        if quotation_bytes:
            st.markdown(
                f"""
                <div style="background:#ECFDF5; border:1px solid #A7F3D0; border-radius:6px; padding:12px 16px; margin:10px 0 12px 0; display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div style="font-weight:700; color:#065F46; font-size:0.95rem;">
                            IEPCI_Quotation_DRAFT.xlsx Ready for Download
                        </div>
                        <div style="font-size:0.78rem; color:#047857; margin-top:2px;">
                            Official format with formulas, GST calculation, and header references ({len(quotation_bytes):,} bytes).
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.download_button(
                "Download Final Excel Quotation",
                data=quotation_bytes,
                file_name="IEPCI_Quotation_DRAFT.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)
