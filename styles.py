"""Professional enterprise styling and theme for IEPCI Quote Assistant.

Calm, clean aesthetic matching IEPCI brand:
- Palette: Royal Blue, Pure White, Midnight Black, and Metallic Silver
- Frosted glassmorphism panels with micro-borders
- Bento grid dashboard layout with live time-saved counter
- Switchboard line illustration empty states
- Satisfying quotation approval stamp animation
- Stepped quotation progress pipeline
- Zero emojis
"""

import streamlit as st

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    /* Brand Palette: Blue, White, Black, Silver */
    --c-black: #0B0F19;
    --c-navy-dark: #0F172A;
    --c-navy: #1E293B;
    --c-blue-primary: #2563EB;
    --c-blue-deep: #1E40AF;
    --c-blue-hover: #1D4ED8;
    --c-blue-tint: #EFF6FF;
    --c-blue-border: #BFDBFE;
    
    --c-white: #FFFFFF;
    --c-silver-light: #F8FAFC;
    --c-silver: #E2E8F0;
    --c-silver-medium: #CBD5E1;
    --c-silver-dark: #94A3B8;
    --c-silver-text: #64748B;
    
    --c-emerald: #059669;
    --c-emerald-tint: #ECFDF5;
    --c-emerald-border: #A7F3D0;
    --c-amber: #D97706;
    --c-amber-tint: #FFFBEB;
    --c-amber-border: #FDE68A;
    
    /* Rounded Borders */
    --r-xs: 5px;
    --r-sm: 8px;
    --r-md: 10px;
    --r-lg: 14px;
    --r-xl: 18px;
    --r-pill: 9999px;
    
    /* Frosted Glass Shadows & Borders */
    --glass-bg: rgba(255, 255, 255, 0.94);
    --glass-border: rgba(226, 232, 240, 0.9);
    --card-shadow: 0 1px 3px rgba(15, 23, 42, 0.04), 0 4px 14px -2px rgba(15, 23, 42, 0.02);
}

/* Global Typography */
html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    color: var(--c-navy-dark);
}

.stApp {
    background-color: var(--c-silver-light) !important;
}

/* ---------------- Layout & Compact Spacing (Zero Header Void) ---------------- */
header[data-testid="stHeader"] {
    height: 0px !important;
    min-height: 0px !important;
    padding: 0 !important;
    margin: 0 !important;
    background: transparent !important;
    z-index: 10 !important;
}

div[data-testid="stSidebarHeader"] {
    padding-top: 0.25rem !important;
    padding-bottom: 0 !important;
    min-height: auto !important;
    height: auto !important;
}

div[data-testid="stSidebarCollapseButton"] {
    margin: 0 !important;
}

div[data-testid="stSidebarCollapsedControl"] {
    top: 0.35rem !important;
    left: 0.35rem !important;
    z-index: 99 !important;
}

.main .block-container {
    padding-top: 0.25rem !important;
    padding-bottom: 1.5rem !important;
    padding-left: 1.25rem !important;
    padding-right: 1.25rem !important;
    max-width: 1540px !important;
}

div[data-testid="stVerticalBlock"] {
    gap: 0.65rem !important;
}

div[data-testid="stHorizontalBlock"] {
    gap: 0.75rem !important;
}

/* ---------------- Sidebar Navigation (Clean SaaS Menu) ---------------- */
section[data-testid="stSidebar"] {
    background-color: var(--c-white) !important;
    border-right: 1px solid var(--c-silver) !important;
    box-shadow: none !important;
}

section[data-testid="stSidebar"] .block-container {
    padding-top: 0 !important;
    padding-left: 0.85rem !important;
    padding-right: 0.85rem !important;
}

/* Sidebar Header: Seamless Minimalist Workspace (Linear / Vercel style) */
.sidebar-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0px 2px 10px 2px;
    margin-top: 0 !important;
    margin-bottom: 10px;
    border-bottom: 1px solid var(--c-silver);
}

.sidebar-header-logo {
    width: 44px;
    height: 44px;
    border-radius: var(--r-sm);
    border: 1px solid var(--c-silver);
    padding: 2px;
    object-fit: contain;
    background: #FFFFFF;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
    flex-shrink: 0;
}

.sidebar-header-title {
    font-size: 1.05rem;
    font-weight: 800;
    color: var(--c-navy-dark);
    letter-spacing: -0.015em;
    display: flex;
    align-items: center;
    gap: 6px;
    line-height: 1.2;
}

.sidebar-header-badge {
    font-size: 0.65rem;
    font-weight: 700;
    color: var(--c-blue-deep);
    background: var(--c-blue-tint);
    border: 1px solid var(--c-blue-border);
    padding: 1px 6px;
    border-radius: var(--r-pill);
    letter-spacing: 0.02em;
}

.sidebar-header-sub {
    font-size: 0.74rem;
    color: var(--c-silver-text);
    font-weight: 500;
    margin-top: 2px;
}

.sidebar-brand-card {
    background: var(--c-white);
    border: 1px solid var(--c-silver);
    border-left: 3px solid var(--c-blue-primary);
    border-radius: var(--r-md);
    padding: 10px 12px;
    margin-bottom: 12px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}

.sidebar-brand-title {
    font-size: 1.02rem;
    font-weight: 800;
    letter-spacing: -0.01em;
    color: var(--c-navy-dark);
}

.sidebar-brand-sub {
    font-size: 0.72rem;
    color: var(--c-silver-text);
    font-weight: 500;
    margin-top: 1px;
}

/* Hide default clunky radio circles; transform into modern menu items */
div[data-testid="stRadio"] > label {
    display: none !important;
}

div[data-testid="stRadio"] div[role="radiogroup"] {
    gap: 3px !important;
}

div[data-testid="stRadio"] div[role="radiogroup"] > label > div:first-child {
    display: none !important;
}

div[data-testid="stRadio"] label {
    background: transparent !important;
    border: none !important;
    border-radius: var(--r-sm) !important;
    padding: 8px 12px !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    color: #475569 !important;
    transition: all 0.15s ease !important;
    display: flex !important;
    align-items: center !important;
    cursor: pointer !important;
    box-shadow: none !important;
}

div[data-testid="stRadio"] label:hover {
    background: #F1F5F9 !important;
    color: var(--c-navy-dark) !important;
}

div[data-testid="stRadio"] label:has(input:checked) {
    background: var(--c-blue-tint) !important;
    color: var(--c-blue-deep) !important;
    font-weight: 700 !important;
    border-left: 3px solid var(--c-blue-primary) !important;
}

/* Sidebar Info Card */
.sidebar-info-card {
    background: var(--c-white);
    border: 1px solid var(--c-silver);
    border-radius: var(--r-md);
    padding: 9px 12px;
    margin-top: 6px;
    font-size: 0.8rem;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.02);
}

.sidebar-info-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
    border-bottom: 1px solid #F1F5F9;
}

.sidebar-info-row:last-child {
    border-bottom: none;
}

/* ---------------- Top Application Header Banner ---------------- */
.brand-banner {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--c-white);
    border: 1px solid var(--c-silver);
    border-radius: var(--r-lg);
    padding: 10px 18px;
    margin-top: 0 !important;
    margin-bottom: 8px;
    box-shadow: var(--card-shadow);
}

.brand-left {
    display: flex;
    align-items: center;
    gap: 16px;
}

.brand-logo {
    width: 72px;
    height: 72px;
    border-radius: var(--r-md);
    border: 1px solid var(--c-silver);
    padding: 3px;
    object-fit: contain;
    background: #FFFFFF;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
    flex-shrink: 0;
}

.brand-icon-box {
    background: var(--c-black);
    color: #FFFFFF;
    padding: 12px 18px;
    border-radius: var(--r-md);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.1rem;
    font-weight: 800;
    letter-spacing: 0.05em;
}

.brand-title-wrap {
    display: flex;
    flex-direction: column;
}

.brand-title {
    font-size: 1.35rem;
    font-weight: 800;
    color: var(--c-navy-dark);
    letter-spacing: -0.015em;
    display: flex;
    align-items: center;
    gap: 8px;
}

.brand-badge {
    background: var(--c-blue-tint);
    color: var(--c-blue-primary);
    border: 1px solid var(--c-blue-border);
    font-size: 0.68rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: var(--r-pill);
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

.brand-subtitle {
    font-size: 0.8rem;
    color: var(--c-silver-text);
    font-weight: 500;
    margin-top: 1px;
}

/* Status Pill with Pulsing Live Dot */
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 5px 12px;
    border-radius: var(--r-pill);
    font-size: 0.8rem;
    font-weight: 600;
}

.status-pill-active {
    background: var(--c-emerald-tint);
    border: 1px solid var(--c-emerald-border);
    color: var(--c-emerald);
}

.status-pill-idle {
    background: var(--c-silver-light);
    border: 1px solid var(--c-silver);
    color: var(--c-silver-text);
}

.status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    display: inline-block;
}

.status-dot-active {
    background: var(--c-emerald);
    box-shadow: 0 0 0 2px rgba(5, 150, 105, 0.2);
    animation: pulseDot 2s infinite ease-in-out;
}

.status-dot-idle {
    background: var(--c-silver-dark);
}

@keyframes pulseDot {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.3); opacity: 0.7; }
}

/* ---------------- Bento Grid Dashboard Layout ---------------- */
.bento-grid {
    display: grid;
    grid-template-columns: 1.6fr 1.2fr 1fr 1fr;
    gap: 10px;
    margin-bottom: 20px;
}

@media (max-width: 1100px) {
    .bento-grid {
        grid-template-columns: 1fr 1fr;
    }
}

@media (max-width: 640px) {
    .bento-grid {
        grid-template-columns: 1fr;
    }
}

.bento-card {
    background: var(--c-white);
    border: 1px solid var(--c-silver);
    border-radius: var(--r-lg);
    padding: 12px 16px;
    box-shadow: var(--card-shadow);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    transition: all 0.15s ease;
}

.bento-card:hover {
    border-color: var(--c-silver-medium);
    box-shadow: 0 4px 12px -2px rgba(15, 23, 42, 0.06);
}

.bento-card.hero {
    background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 60%, var(--c-blue-tint) 100%);
    border-left: 3px solid var(--c-blue-primary);
}

.bento-badge-live {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    color: var(--c-blue-deep);
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 2px 7px;
    border-radius: var(--r-pill);
    margin-bottom: 4px;
    width: fit-content;
}

.bento-label {
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--c-silver-text);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 2px;
}

.bento-val {
    font-size: 1.55rem;
    font-weight: 800;
    color: var(--c-navy-dark);
    line-height: 1.15;
    letter-spacing: -0.01em;
}

.bento-sub {
    font-size: 0.74rem;
    color: var(--c-silver-text);
    font-weight: 500;
    margin-top: 3px;
}

.bento-tag {
    display: inline-block;
    font-size: 0.68rem;
    font-weight: 600;
    color: var(--c-navy);
    background: var(--c-silver-light);
    border: 1px solid var(--c-silver);
    padding: 2px 6px;
    border-radius: var(--r-xs);
    margin-top: 6px;
    width: fit-content;
}

.bento-progress-track {
    width: 100%;
    height: 6px;
    background: var(--c-silver);
    border-radius: var(--r-pill);
    margin-top: 8px;
    overflow: hidden;
}

.bento-progress-fill {
    height: 100%;
    background: var(--c-blue-primary);
    border-radius: var(--r-pill);
    transition: width 0.3s ease;
}

/* ---------------- Workflow Pipeline Stepper ---------------- */
.workflow-stepper {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin-bottom: 20px;
}

.stepper-card {
    background: var(--c-white);
    border: 1px solid var(--c-silver);
    border-radius: var(--r-md);
    padding: 7px 11px;
    display: flex;
    align-items: center;
    gap: 9px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.02);
    transition: all 0.15s ease;
}

.stepper-card.done {
    border-color: var(--c-blue-border);
    background: var(--c-silver-light);
    border-left: 3px solid var(--c-blue-primary);
}

.stepper-card.active {
    border-color: #93C5FD;
    background: #FFFFFF;
    border-left: 3px solid var(--c-blue-primary);
    box-shadow: 0 2px 6px rgba(37, 99, 235, 0.08);
}

.stepper-num {
    width: 22px;
    height: 22px;
    border-radius: var(--r-xs);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.72rem;
    font-weight: 700;
    flex-shrink: 0;
}

.stepper-card.done .stepper-num {
    background: var(--c-blue-primary);
    color: #FFFFFF;
}

.stepper-card.active .stepper-num {
    background: var(--c-blue-tint);
    border: 1px solid var(--c-blue-primary);
    color: var(--c-blue-primary);
}

.stepper-card.idle .stepper-num {
    background: var(--c-silver);
    color: var(--c-silver-dark);
}

.stepper-text {
    display: flex;
    flex-direction: column;
}

.stepper-title {
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--c-navy-dark);
}

.stepper-status {
    font-size: 0.68rem;
    color: var(--c-silver-text);
}

/* ---------------- Switchboard Empty State ---------------- */
.empty-state-card {
    background: var(--c-white);
    border: 1px solid var(--c-silver);
    border-radius: var(--r-lg);
    padding: 24px 20px 20px 20px;
    text-align: center;
    box-shadow: var(--card-shadow);
    display: flex;
    flex-direction: column;
    align-items: center;
    margin-bottom: 10px;
}

.empty-state-title {
    font-size: 1.2rem;
    font-weight: 800;
    color: var(--c-navy-dark);
    margin-top: 12px;
    margin-bottom: 6px;
    letter-spacing: -0.01em;
}

.empty-state-desc {
    max-width: 520px;
    color: var(--c-silver-text);
    font-size: 0.86rem;
    line-height: 1.45;
    margin: 0 auto 16px auto;
}

/* ---------------- Satisfying Approved Stamp Animation ---------------- */
@keyframes stampIn {
    0% {
        opacity: 0;
        transform: scale(2.4) rotate(-24deg);
    }
    60% {
        opacity: 0.95;
        transform: scale(0.96) rotate(-5deg);
    }
    100% {
        opacity: 0.92;
        transform: scale(1) rotate(-8deg);
    }
}

.stamp-wrap {
    display: flex;
    justify-content: flex-end;
    margin-bottom: -10px;
    position: relative;
    z-index: 5;
}

.stamp-badge {
    display: inline-block;
    padding: 5px 14px;
    border: 2.5px dashed var(--c-emerald);
    border-radius: var(--r-sm);
    color: var(--c-emerald);
    background: rgba(236, 253, 245, 0.92);
    backdrop-filter: blur(4px);
    box-shadow: 0 0 0 1px rgba(5, 150, 105, 0.15);
    animation: stampIn 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;
    transform: rotate(-8deg);
    user-select: none;
}

.stamp-badge-title {
    font-size: 1.05rem;
    font-weight: 900;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    line-height: 1.1;
    text-align: center;
}

.stamp-badge-sub {
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    text-align: center;
    opacity: 0.85;
}

/* ---------------- UI Cards & Containers ---------------- */
.ui-card {
    background: var(--c-white);
    border: 1px solid var(--c-silver);
    border-radius: var(--r-lg);
    padding: 12px 16px;
    margin-bottom: 10px;
    box-shadow: var(--card-shadow);
}

.ui-card-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--c-navy-dark);
    margin-bottom: 2px;
}

.ui-card-subtitle {
    font-size: 0.78rem;
    color: var(--c-silver-text);
    margin-bottom: 8px;
}

.section-eyebrow {
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--c-blue-primary);
    margin-bottom: 2px;
}

.section-heading {
    font-size: 1.25rem;
    font-weight: 800;
    color: var(--c-navy-dark);
    letter-spacing: -0.01em;
    margin-bottom: 2px;
}

.section-description {
    font-size: 0.82rem;
    color: var(--c-silver-text);
    margin-bottom: 10px;
}

/* ---------------- Buttons & Inputs (Accessible Enterprise Theme) ---------------- */
button, .stButton > button, .stDownloadButton > button {
    border-radius: var(--r-sm) !important;
    font-weight: 600 !important;
    font-size: 0.86rem !important;
    padding: 0.4rem 1rem !important;
    min-height: 36px !important;
    transition: all 0.15s ease-in-out !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08) !important;
    cursor: pointer !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    letter-spacing: 0.01em !important;
}

/* Primary Action Buttons: Dark Midnight Navy (WCAG AAA 14:1) */
button[kind="primary"],
button[data-testid="stBaseButton-primary"],
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {
    background: #0F2942 !important;
    color: #FFFFFF !important;
    border: 1px solid #0A192F !important;
    box-shadow: 0 2px 4px rgba(15, 41, 66, 0.35), 0 1px 2px rgba(0, 0, 0, 0.15) !important;
}

button[kind="primary"] *,
button[data-testid="stBaseButton-primary"] *,
.stButton > button[kind="primary"] *,
.stButton > button[data-testid="stBaseButton-primary"] * {
    color: #FFFFFF !important;
}

button[kind="primary"]:hover,
button[data-testid="stBaseButton-primary"]:hover,
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="stBaseButton-primary"]:hover {
    background: #1E40AF !important;
    border-color: #1E3A8A !important;
    color: #FFFFFF !important;
    box-shadow: 0 4px 10px rgba(30, 64, 175, 0.45) !important;
    transform: translateY(-1px) !important;
}

button[kind="primary"]:active,
button[data-testid="stBaseButton-primary"]:active,
.stButton > button[kind="primary"]:active,
.stButton > button[data-testid="stBaseButton-primary"]:active {
    background: #0A192F !important;
    color: #FFFFFF !important;
    transform: translateY(0) !important;
}

button[kind="primary"]:focus-visible,
button[data-testid="stBaseButton-primary"]:focus-visible,
.stButton > button[kind="primary"]:focus-visible,
.stButton > button[data-testid="stBaseButton-primary"]:focus-visible {
    outline: 2px solid #2563EB !important;
    outline-offset: 2px !important;
}

/* Secondary / Default Buttons: Dark Slate (Solid Darker Shade, WCAG AAA 9:1) */
button[kind="secondary"],
button[data-testid="stBaseButton-secondary"],
.stButton > button[kind="secondary"],
.stButton > button[data-testid="stBaseButton-secondary"],
.stButton > button:not([kind="primary"]):not([data-testid="stBaseButton-primary"]) {
    background: #334155 !important;
    color: #FFFFFF !important;
    border: 1px solid #1E293B !important;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.25) !important;
}

button[kind="secondary"] *,
button[data-testid="stBaseButton-secondary"] *,
.stButton > button[kind="secondary"] *,
.stButton > button[data-testid="stBaseButton-secondary"] *,
.stButton > button:not([kind="primary"]):not([data-testid="stBaseButton-primary"]) * {
    color: #FFFFFF !important;
}

button[kind="secondary"]:hover,
button[data-testid="stBaseButton-secondary"]:hover,
.stButton > button[kind="secondary"]:hover,
.stButton > button[data-testid="stBaseButton-secondary"]:hover,
.stButton > button:not([kind="primary"]):not([data-testid="stBaseButton-primary"]):hover {
    background: #1E293B !important;
    border-color: #0F172A !important;
    color: #FFFFFF !important;
    box-shadow: 0 3px 8px rgba(15, 23, 42, 0.35) !important;
    transform: translateY(-0.5px) !important;
}

button[kind="secondary"]:active,
button[data-testid="stBaseButton-secondary"]:active,
.stButton > button[kind="secondary"]:active,
.stButton > button[data-testid="stBaseButton-secondary"]:active,
.stButton > button:not([kind="primary"]):not([data-testid="stBaseButton-primary"]):active {
    background: #0F172A !important;
    color: #FFFFFF !important;
    transform: translateY(0) !important;
}

button[kind="secondary"]:focus-visible,
button[data-testid="stBaseButton-secondary"]:focus-visible,
.stButton > button[kind="secondary"]:focus-visible,
.stButton > button[data-testid="stBaseButton-secondary"]:focus-visible,
.stButton > button:not([kind="primary"]):not([data-testid="stBaseButton-primary"]):focus-visible {
    outline: 2px solid #64748B !important;
    outline-offset: 2px !important;
}

/* Download / Export Buttons: Dark Forest Emerald Green (WCAG AAA) */
.stDownloadButton > button {
    background: #065F46 !important;
    color: #FFFFFF !important;
    border: 1px solid #022C22 !important;
    box-shadow: 0 2px 4px rgba(6, 95, 70, 0.35) !important;
}

.stDownloadButton > button * {
    color: #FFFFFF !important;
}

.stDownloadButton > button:hover {
    background: #047857 !important;
    border-color: #064E3B !important;
    color: #FFFFFF !important;
    box-shadow: 0 4px 10px rgba(4, 120, 87, 0.45) !important;
    transform: translateY(-1px) !important;
}

/* Destructive / Delete Button: Dark Crimson Red */
div.st-key-btn_del_db_rfq button,
div[class*="st-key-btn_del_db_rfq"] button,
div[data-testid*="btn_del_db_rfq"] button {
    background: #B91C1C !important;
    color: #FFFFFF !important;
    border: 1px solid #991B1B !important;
    box-shadow: 0 1px 3px rgba(185, 28, 28, 0.35) !important;
}

div.st-key-btn_del_db_rfq button *,
div[class*="st-key-btn_del_db_rfq"] button *,
div[data-testid*="btn_del_db_rfq"] button * {
    color: #FFFFFF !important;
}

div.st-key-btn_del_db_rfq button:hover,
div[class*="st-key-btn_del_db_rfq"] button:hover,
div[data-testid*="btn_del_db_rfq"] button:hover {
    background: #991B1B !important;
    color: #FFFFFF !important;
    border-color: #7F1D1D !important;
    box-shadow: 0 3px 8px rgba(153, 27, 27, 0.5) !important;
    transform: translateY(-1px) !important;
}

/* Disabled Button State */
button:disabled,
.stButton > button:disabled,
.stDownloadButton > button:disabled {
    background: #94A3B8 !important;
    color: #E2E8F0 !important;
    border: 1px solid #64748B !important;
    cursor: not-allowed !important;
    opacity: 0.65 !important;
    box-shadow: none !important;
    transform: none !important;
}

div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div {
    background-color: var(--c-white) !important;
    border: 1px solid var(--c-silver-medium) !important;
    border-radius: var(--r-sm) !important;
    color: var(--c-navy-dark) !important;
    min-height: 34px !important;
    font-size: 0.85rem !important;
}

div[data-baseweb="input"]:focus-within > div,
div[data-baseweb="select"]:focus-within > div {
    border-color: var(--c-blue-primary) !important;
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12) !important;
}

.stTextInput label, .stSelectbox label, .stFileUploader label {
    font-size: 0.74rem !important;
    font-weight: 600 !important;
    color: #334155 !important;
    margin-bottom: 2px !important;
}

/* ---------------- Tables & DataFrames ---------------- */
div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {
    background: var(--c-white) !important;
    border: 1px solid var(--c-silver) !important;
    border-radius: var(--r-md) !important;
    overflow: hidden !important;
    box-shadow: var(--card-shadow) !important;
}

/* ---------------- Commercial Summary Cards ---------------- */
.commercial-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin-bottom: 8px;
}

.commercial-card {
    background: var(--c-white);
    border: 1px solid var(--c-silver);
    border-radius: var(--r-md);
    padding: 10px 12px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
    border-top: 3px solid var(--c-silver-medium);
}

.commercial-card.highlight {
    border-top-color: var(--c-blue-primary);
}

.commercial-card.total {
    border-top-color: var(--c-emerald);
}

.commercial-label {
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--c-silver-text);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 2px;
}

.commercial-val {
    font-size: 1.25rem;
    font-weight: 800;
    color: var(--c-navy-dark);
    line-height: 1.2;
}

.commercial-sub {
    font-size: 0.72rem;
    color: var(--c-silver-text);
    margin-top: 2px;
}

/* ---------------- Callout Notices ---------------- */
.callout-blue {
    background: var(--c-blue-tint);
    border: 1px solid var(--c-blue-border);
    border-left: 3px solid var(--c-blue-primary);
    border-radius: var(--r-sm);
    padding: 8px 12px;
    margin: 6px 0 8px 0;
    color: #1E3A8A;
    font-size: 0.84rem;
    line-height: 1.45;
}

.callout-amber {
    background: var(--c-amber-tint);
    border: 1px solid var(--c-amber-border);
    border-left: 3px solid var(--c-amber);
    border-radius: var(--r-sm);
    padding: 8px 12px;
    margin: 6px 0 8px 0;
    color: #92400E;
    font-size: 0.84rem;
    line-height: 1.45;
}

/* Responsive */
@media (max-width: 768px) {
    .main .block-container {
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
    }
    .workflow-stepper {
        grid-template-columns: 1fr 1fr;
    }
    .commercial-grid {
        grid-template-columns: 1fr 1fr;
    }
}
</style>
"""


def apply_styles():
    """Inject custom CSS into the Streamlit session."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
