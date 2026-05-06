"""
PDF Intelligence Converter - Premium Batsirai Design
Production Version 4.0.0 - Deployment Locked
Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import tempfile
import os
from pathlib import Path
import pdfplumber
import fitz  # PyMuPDF
from docx import Document
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from PIL import Image
import io
from datetime import datetime, timezone
import json
import csv
import sqlite3
import hashlib
from typing import List, Dict, Any
import zipfile
import re
import time
import warnings
import logging

warnings.filterwarnings("ignore")
logging.getLogger('streamlit').setLevel(logging.ERROR)

OCR_AVAILABLE = False
try:
    import pytesseract
    from pdf2image import convert_from_bytes
    OCR_AVAILABLE = True
except ImportError:
    pass

APP_VERSION = "4.0.0"
APP_NAME = "PDF Intelligence Converter"
DEPLOYMENT_MODE = os.environ.get("DEPLOYMENT_MODE", "production")
SESSION_TIMEOUT_MINUTES = 60

st.set_page_config(
    page_title=f"{APP_NAME}",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

THEME = {
    "bg": "#ffffff",
    "panel": "#ffffff",
    "panel2": "#f7f7f7",
    "text": "#111111",
    "muted": "#5b5b5b",
    "border": "rgba(0,0,0,0.10)",
    "border2": "rgba(0,0,0,0.14)",
    "accent": "#d71e28",
    "accent2": "#b5161f",
    "good": "#168a45",
    "bad": "#d11a2a",
    "neutral": "#6b7280",
}

def safe_rerun():
    try:
        if hasattr(st, "rerun"):
            st.rerun()
        elif hasattr(st, "experimental_rerun"):
            st.experimental_rerun()
    except:
        pass

def get_org_password():
    env_pw = os.environ.get("APP_PASSWORD", "").strip()
    if env_pw:
        return env_pw
    try:
        if hasattr(st, 'secrets') and st.secrets:
            sec_pw = str(st.secrets.get("app_password", "")).strip()
            if sec_pw:
                return sec_pw
    except:
        pass
    return "SPAR2024"

ORG_PASSWORD = get_org_password()

def apply_style():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

    * {
        font-family: 'Inter', sans-serif !important;
    }

    html, body, [data-testid="stAppViewContainer"], .stApp {
        background: #ffffff !important;
        color: #111111 !important;
    }

    /* Hide Streamlit default chrome */
    [data-testid="stHeader"], 
    [data-testid="stToolbar"], 
    #MainMenu, 
    footer {
        display: none !important;
    }

    /* ✅ FIXED: Responsive container (no min-width) */
    .block-container {
        max-width: 1200px !important;
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        margin: 0 auto !important;
    }

    /* ✅ FIXED: Sidebar (no forced width) */
    section[data-testid="stSidebar"] {
        background: #ffffff !important;
        border-right: 1px solid rgba(0,0,0,0.10) !important;
    }

    /* Cards */
    .card {
        background: #ffffff;
        border: 1px solid rgba(0,0,0,0.10);
        border-radius: 18px;
        padding: 18px;
        margin-bottom: 16px;
    }

    .card-soft {
        background: #f7f7f7;
        border: 1px solid rgba(0,0,0,0.10);
        border-radius: 18px;
        padding: 18px;
        margin-bottom: 16px;
    }

    /* Hero */
    .hero {
        border: 1px solid rgba(0,0,0,0.10);
        border-radius: 22px;
        padding: 24px;
        margin-bottom: 20px;
        background: radial-gradient(900px 260px at 50% -10%, rgba(215,30,40,0.10), transparent 60%);
    }

    .title {
        font-size: 28px;
        font-weight: 800;
    }

    .subtitle {
        margin-top: 6px;
        color: #5b5b5b;
        font-size: 14px;
    }

    /* Chips */
    .chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 10px;
        border-radius: 999px;
        border: 1px solid rgba(0,0,0,0.10);
        font-size: 12px;
        color: #5b5b5b;
        background: #ffffff;
    }

    .chip-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #d71e28;
    }

    .chip-container {
        display: flex;
        gap: 8px;
        flex-wrap: wrap; /* ✅ FIXED: allows wrapping instead of shrinking */
    }

    /* Buttons */
    div.stButton > button {
        background: #d71e28;
        color: white;
        border-radius: 12px;
        border: none;
        padding: 0.6rem 1rem;
        font-weight: 700;
    }

    div.stButton > button:hover {
        background: #b5161f;
    }

    /* Inputs */
    div[data-baseweb="input"], 
    div[data-baseweb="select"] {
        border-radius: 12px !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab"] {
        border-radius: 12px;
        padding: 10px 14px;
        font-weight: 700;
    }

    .stTabs [aria-selected="true"] {
        background: rgba(215,30,40,0.10) !important;
        border: 1px solid rgba(215,30,40,0.3) !important;
    }

    /* Tables */
    [data-testid="stDataFrame"] {
        border-radius: 12px;
        border: 1px solid rgba(0,0,0,0.10);
    }

    /* ✅ Mobile responsiveness */
    @media (max-width: 768px) {
        .title {
            font-size: 22px;
        }

        .block-container {
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
    }

    </style>
    """, unsafe_allow_html=True)
apply_style()

# Session management
def touch():
    st.session_state.last_activity = datetime.now()

def is_timed_out():
    last = st.session_state.get("last_activity")
    if not last:
        return False
    return (datetime.now() - last).total_seconds() > SESSION_TIMEOUT_MINUTES * 60

def logout():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    safe_rerun()

# Initialize session state
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "session_id" not in st.session_state:
    st.session_state.session_id = hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]
if "last_activity" not in st.session_state:
    st.session_state.last_activity = datetime.now()
if "username" not in st.session_state:
    st.session_state.username = None
if "page" not in st.session_state:
    st.session_state.page = "📄 Convert PDF"

# Database setup
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password_hash TEXT, role TEXT DEFAULT 'user')''')
    c.execute('''CREATE TABLE IF NOT EXISTS conversion_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  username TEXT,
                  filename TEXT,
                  output_format TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  file_size INTEGER)''')
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        admin_hash = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                 ('admin', admin_hash, 'admin'))
    conn.commit()
    conn.close()

init_db()

def verify_user(username, password):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    c.execute("SELECT * FROM users WHERE username=? AND password_hash=?", 
             (username, password_hash))
    user = c.fetchone()
    conn.close()
    return user is not None

def register_user(username, password, role='user'):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    try:
        c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                 (username, password_hash, role))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def save_conversion_history(username, filename, output_format, file_size):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT INTO conversion_history (username, filename, output_format, file_size) VALUES (?, ?, ?, ?)",
             (username, filename, output_format, file_size))
    conn.commit()
    conn.close()

def get_user_history(username):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM conversion_history WHERE username=? ORDER BY timestamp DESC LIMIT 50",
             (username,))
    history = c.fetchall()
    conn.close()
    return history

def sign_in(username, password):
    if verify_user(username, password):
        st.session_state.authenticated = True
        st.session_state.username = username
        touch()
        return True
    return False

# PDF Processing functions
def extract_pdf_intelligent(pdf_path, mode, extract_tables_flag):
    content = {"text": [], "tables": [], "pages": 0, "metadata": {}}
    
    try:
        doc = fitz.open(pdf_path)
        content["metadata"] = {
            "title": doc.metadata.get("title", "Unknown"),
            "author": doc.metadata.get("author", "Unknown"),
            "subject": doc.metadata.get("subject", "Unknown"),
            "creator": doc.metadata.get("creator", "Unknown"),
            "producer": doc.metadata.get("producer", "Unknown"),
            "page_count": len(doc)
        }
        doc.close()
    except:
        content["metadata"] = {"title": "Unknown", "author": "Unknown", "page_count": 0}
    
    with pdfplumber.open(pdf_path) as pdf:
        content["pages"] = len(pdf.pages)
        
        for page_num, page in enumerate(pdf.pages, 1):
            if mode in ["Smart (Text + Tables)", "Text Only"]:
                text = page.extract_text() or ""
                content["text"].append({
                    "page": page_num, 
                    "content": text,
                    "word_count": len(text.split()),
                    "char_count": len(text)
                })
            
            if extract_tables_flag and mode in ["Smart (Text + Tables)", "Tables Only"]:
                tables = page.extract_tables()
                for table_idx, table in enumerate(tables, 1):
                    if table and len(table) > 1:
                        cleaned_table = []
                        for row in table:
                            cleaned_row = [str(cell).strip() if cell else "" for cell in row]
                            if any(cleaned_row):
                                cleaned_table.append(cleaned_row)
                        
                        if cleaned_table:
                            content["tables"].append({
                                "page": page_num,
                                "table_id": table_idx,
                                "rows": len(cleaned_table),
                                "columns": len(cleaned_table[0]) if cleaned_table else 0,
                                "table": cleaned_table
                            })
    return content

def convert_to_excel(content, output_buffer, metadata_include=True):
    wb = Workbook()
    ws_summary = wb.active
    ws_summary.title = "Summary"
    
    row = 1
    ws_summary.cell(row=row, column=1, value="PDF Intelligence Report")
    ws_summary.cell(row=row, column=1).font = Font(bold=True, size=14, color="D71E28")
    row += 2
    
    if metadata_include and content["metadata"]:
        ws_summary.cell(row=row, column=1, value="Document Information")
        ws_summary.cell(row=row, column=1).font = Font(bold=True, size=12)
        row += 1
        for key, value in content["metadata"].items():
            ws_summary.cell(row=row, column=1, value=key.replace('_', ' ').title())
            ws_summary.cell(row=row, column=2, value=str(value))
            row += 1
        row += 1
    
    ws_summary.cell(row=row, column=1, value="Statistics")
    ws_summary.cell(row=row, column=1).font = Font(bold=True, size=12)
    row += 1
    ws_summary.cell(row=row, column=1, value="Total Pages")
    ws_summary.cell(row=row, column=2, value=content['pages'])
    row += 1
    ws_summary.cell(row=row, column=1, value="Total Tables")
    ws_summary.cell(row=row, column=2, value=len(content['tables']))
    
    if content["text"]:
        ws_content = wb.create_sheet("Content")
        row = 1
        for page_data in content["text"]:
            ws_content.cell(row=row, column=1, value=f"--- PAGE {page_data['page']} ---")
            ws_content.cell(row=row, column=1).font = Font(bold=True, color="D71E28")
            row += 1
            for line in page_data["content"].split('\n'):
                if line.strip():
                    ws_content.cell(row=row, column=1, value=line)
                    row += 1
            row += 1
    
    if content["tables"]:
        for table_data in content["tables"]:
            sheet_name = f"Table_{table_data['table_id']}_P{table_data['page']}"[:31]
            ws_table = wb.create_sheet(sheet_name)
            table = table_data["table"]
            for r, row_data in enumerate(table, 1):
                for c, cell in enumerate(row_data, 1):
                    ws_table.cell(row=r, column=c, value=cell)
    
    wb.save(output_buffer)
    output_buffer.seek(0)
    return output_buffer

def convert_to_word(content, output_buffer):
    doc = Document()
    doc.add_heading('PDF Intelligence Report', 0)
    doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if content["text"]:
        for page_data in content["text"]:
            doc.add_heading(f'Page {page_data["page"]}', level=1)
            doc.add_paragraph(page_data["content"])
    
    if content["tables"]:
        doc.add_heading('Extracted Tables', level=1)
        for table_data in content["tables"]:
            if table_data["table"]:
                doc.add_heading(f'Table {table_data["table_id"]} (Page {table_data["page"]})', level=2)
                table = doc.add_table(rows=len(table_data["table"]), cols=len(table_data["table"][0]))
                table.style = 'Light List Accent 1'
                for i, row in enumerate(table_data["table"]):
                    for j, cell in enumerate(row):
                        table.cell(i, j).text = cell
    
    doc.save(output_buffer)
    output_buffer.seek(0)
    return output_buffer

def convert_to_markdown(content):
    md = []
    md.append("# PDF Intelligence Report\n\n")
    md.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    
    for page_data in content["text"]:
        md.append(f"## Page {page_data['page']}\n\n")
        md.append(f"{page_data['content']}\n\n---\n\n")
    
    if content["tables"]:
        md.append("\n## Tables\n\n")
        for table_data in content["tables"]:
            md.append(f"### Table {table_data['table_id']}\n\n")
            if table_data["table"]:
                for i, row in enumerate(table_data["table"]):
                    md.append("| " + " | ".join(row) + " |\n")
                    if i == 0:
                        md.append("|" + "|".join(["---" for _ in row]) + "|\n")
            md.append("\n\n")
    
    return "".join(md)

def convert_to_html(content):
    html = []
    html.append(f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>PDF Intelligence Report</title>
<style>
body{{font-family:sans-serif;margin:40px}}
h1{{color:#d71e28}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ddd;padding:8px}}
th{{background-color:#FDE8E8}}
</style></head>
<body>
<h1>PDF Intelligence Report</h1>
<p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>""")
    
    for page_data in content["text"]:
        html.append(f'<h2>Page {page_data["page"]}</h2>')
        html.append(f'<pre>{page_data["content"]}</pre>')
    
    if content["tables"]:
        html.append("<h2>Tables</h2>")
        for table_data in content["tables"]:
            html.append(f'<h3>Table {table_data["table_id"]} (Page {table_data["page"]})</h3>')
            html.append('<table>')
            if table_data["table"]:
                for i, row in enumerate(table_data["table"]):
                    html.append('<tr>')
                    tag = 'th' if i == 0 else 'td'
                    for cell in row:
                        html.append(f'<{tag}>{cell}</{tag}>')
                    html.append('</tr>')
            html.append('</table><br>')
    
    html.append("</body></html>")
    return "\n".join(html)

def merge_pdfs(pdf_files):
    merged = fitz.open()
    for pdf_file in pdf_files:
        pdf_content = pdf_file.read()
        with fitz.open(stream=pdf_content, filetype="pdf") as pdf:
            merged.insert_pdf(pdf)
    output = io.BytesIO()
    merged.save(output)
    merged.close()
    output.seek(0)
    return output

def split_pdf(pdf_bytes, pages_per_split):
    pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    splits = []
    for i in range(0, len(pdf_doc), pages_per_split):
        new_pdf = fitz.open()
        end = min(i + pages_per_split, len(pdf_doc))
        new_pdf.insert_pdf(pdf_doc, from_page=i, to_page=end-1)
        output = io.BytesIO()
        new_pdf.save(output)
        new_pdf.close()
        output.seek(0)
        splits.append(output)
    pdf_doc.close()
    return splits

def rotate_pdf(pdf_bytes, rotation):
    pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in pdf_doc:
        page.set_rotation(rotation)
    output = io.BytesIO()
    pdf_doc.save(output)
    pdf_doc.close()
    output.seek(0)
    return output

# ============================================
# SIGN IN PAGE - Smaller heading to fit box
# ============================================

if not st.session_state.authenticated:
    st.markdown('<div style="height: 1.8rem;"></div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.25, 1])
    with c2:
        st.markdown(f"""
        <div class="card" style="margin-top: 10vh;">
            <div class="login-title" style="text-align:center;">⚡ {APP_NAME}</div>
            <div class="subtitle" style="text-align:center;">Sign in to continue.</div>
            <div style="height: 14px;"></div>
            <div style="display:flex; justify-content:center;">
                <div class="chip"><span class="chip-dot"></span> Version {APP_VERSION} • Production</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        tab1, tab2 = st.tabs(["Sign In", "Register"])
        
        with tab1:
            with st.form("login_form", clear_on_submit=True):
                username = st.text_input("Username", placeholder="Enter username")
                password = st.text_input("Password", type="password", placeholder="Enter password")
                col1, col2 = st.columns(2)
                with col1:
                    ok = st.form_submit_button("Sign in", use_container_width=True)
                with col2:
                    demo = st.form_submit_button("Demo", use_container_width=True)

            if ok:
                if username and password:
                    if sign_in(username, password):
                        st.success("Sign in successful!")
                        safe_rerun()
                    else:
                        st.error("Invalid credentials")
                else:
                    st.warning("Please fill in all fields")
            
            if demo:
                st.info("Demo: admin / admin123")
        
        with tab2:
            with st.form("register_form", clear_on_submit=True):
                new_username = st.text_input("New Username", placeholder="Choose username")
                new_password = st.text_input("New Password", type="password", placeholder="Min 6 characters")
                confirm_password = st.text_input("Confirm Password", type="password", placeholder="Confirm password")
                reg = st.form_submit_button("Register", use_container_width=True)

            if reg:
                if new_username and new_password and confirm_password:
                    if new_password == confirm_password:
                        if len(new_password) >= 6:
                            if register_user(new_username, new_password):
                                st.success("Registration successful! Please sign in.")
                            else:
                                st.error("Username already exists")
                        else:
                            st.warning("Password must be at least 6 characters")
                    else:
                        st.error("Passwords don't match")
                else:
                    st.warning("Please fill in all fields")

    st.stop()

# Session timeout check
if st.session_state.authenticated and is_timed_out():
    st.session_state.authenticated = False
    st.warning("Session timed out. Sign in again.")
    safe_rerun()

touch()

# ============================================
# MAIN DASHBOARD
# ============================================

with st.sidebar:
    st.markdown(f"### ⚡ {st.session_state.username}")
    st.markdown("---")
    page = st.radio("Navigation", ["📄 Convert PDF", "🔧 PDF Tools", "📊 History", "⚙️ Settings"], label_visibility="collapsed")
    st.session_state.page = page
    st.markdown("---")
    
    history = get_user_history(st.session_state.username)
    if history:
        st.markdown("**Recent Activity**")
        for h in history[:5]:
            st.markdown(f"📄 {str(h[2])[:30]} → {h[3]}")
    
    st.markdown("---")
    if st.button("🚪 Sign Out", use_container_width=True):
        logout()

st.markdown(f"""
<div class="hero" style="text-align:center;">
    <div class="title">⚡ {APP_NAME}</div>
    <div class="subtitle">Upload your PDF document. Extract content, convert formats, and manage your documents intelligently.</div>
    <div style="height: 12px;"></div>
    <div class="chip-container">
        <div class="chip"><span class="chip-dot"></span> Secure session</div>
        <div class="chip">Session {st.session_state.session_id}</div>
        <div class="chip">Production</div>
        <div class="chip">Version {APP_VERSION}</div>
        <div class="chip">User {st.session_state.username}</div>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("")

if page == "📄 Convert PDF":
    st.markdown("""<div class="card"><div style="font-size:16px; font-weight:800;">Document Conversion</div><div class="subtitle">Upload your PDF for intelligent extraction and multi-format conversion.</div></div>""", unsafe_allow_html=True)
    st.markdown("")
    
    col_input, col_settings = st.columns([2, 1])
    
    with col_input:
        uploaded_file = st.file_uploader("Choose a PDF file", type=['pdf'], key="convert_upload")
        if uploaded_file:
            st.markdown(f"""<div class="card-soft"><strong>📄 Document:</strong> {uploaded_file.name}<br><strong>📏 Size:</strong> {len(uploaded_file.getvalue())/1024:.2f} KB</div>""", unsafe_allow_html=True)
    
    with col_settings:
        output_format = st.selectbox("Convert to", ["Excel (XLSX)", "Word (DOCX)", "Text (TXT)", "CSV", "JSON", "Markdown", "HTML"])
        extraction_modes = ["Smart (Text + Tables)", "Text Only", "Tables Only"]
        if OCR_AVAILABLE:
            extraction_modes.append("OCR (Scanned PDFs)")
        extraction_mode = st.selectbox("Extraction mode", extraction_modes)
        extract_tables = st.checkbox("Extract tables", value=True)
    
    with st.expander("🔧 Advanced Options"):
        include_metadata = st.checkbox("Include metadata", value=True)
    
    b1, b2 = st.columns([1, 5])
    with b1:
        convert_button = st.button("🔄 Convert", use_container_width=True)
    with b2:
        if st.button("Clear", use_container_width=True):
            st.rerun()
    
    if uploaded_file and convert_button:
        with st.spinner("Processing..."):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_path = tmp_file.name
                
                content = extract_pdf_intelligent(tmp_path, extraction_mode, extract_tables)
                result_buffer = None
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                base_name = Path(uploaded_file.name).stem
                
                if output_format == "Excel (XLSX)":
                    result_buffer = io.BytesIO()
                    convert_to_excel(content, result_buffer, include_metadata)
                    filename = f"{base_name}_{timestamp}.xlsx"
                    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                elif output_format == "Word (DOCX)":
                    result_buffer = io.BytesIO()
                    convert_to_word(content, result_buffer)
                    filename = f"{base_name}_{timestamp}.docx"
                    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                elif output_format == "Text (TXT)":
                    text_content = "\n\n".join([p["content"] for p in content["text"]])
                    result_buffer = io.BytesIO(text_content.encode('utf-8'))
                    filename = f"{base_name}_{timestamp}.txt"
                    mime = "text/plain"
                elif output_format == "CSV":
                    result_buffer = io.BytesIO()
                    text_stream = io.TextIOWrapper(result_buffer, 'utf-8', newline='')
                    writer = csv.writer(text_stream)
                    writer.writerow(["Page", "Content"])
                    for page in content["text"]:
                        writer.writerow([page["page"], page["content"]])
                    text_stream.flush()
                    result_buffer.seek(0)
                    filename = f"{base_name}_{timestamp}.csv"
                    mime = "text/csv"
                elif output_format == "JSON":
                    json_content = {"metadata": content["metadata"], "pages": content["pages"], "text": [{"page": p["page"], "content": p["content"]} for p in content["text"]], "tables": [{"page": t["page"], "table": t["table"]} for t in content["tables"]]}
                    result_buffer = io.BytesIO(json.dumps(json_content, indent=2, ensure_ascii=False).encode('utf-8'))
                    filename = f"{base_name}_{timestamp}.json"
                    mime = "application/json"
                elif output_format == "Markdown":
                    md = convert_to_markdown(content)
                    result_buffer = io.BytesIO(md.encode('utf-8'))
                    filename = f"{base_name}_{timestamp}.md"
                    mime = "text/markdown"
                elif output_format == "HTML":
                    html_content = convert_to_html(content)
                    result_buffer = io.BytesIO(html_content.encode('utf-8'))
                    filename = f"{base_name}_{timestamp}.html"
                    mime = "text/html"
                
                os.unlink(tmp_path)
                
                save_conversion_history(st.session_state.username, uploaded_file.name, output_format, len(uploaded_file.getvalue()))
                
                st.markdown("")
                m1, m2, m3 = st.columns(3)
                with m1:
                    st.markdown(f"<div class='metric'><div class='metric-k'>Pages</div><div class='metric-v'>{content['pages']}</div></div>", unsafe_allow_html=True)
                with m2:
                    st.markdown(f"<div class='metric'><div class='metric-k'>Tables</div><div class='metric-v'>{len(content['tables'])}</div></div>", unsafe_allow_html=True)
                with m3:
                    total_words = sum(t.get("word_count", 0) for t in content["text"])
                    st.markdown(f"<div class='metric'><div class='metric-k'>Words</div><div class='metric-v'>{total_words}</div></div>", unsafe_allow_html=True)
                
                st.success(f"Conversion complete! ({output_format})")
                
                if result_buffer:
                    result_buffer.seek(0)
                    st.download_button(label=f"💾 Download {filename}", data=result_buffer.getvalue(), file_name=filename, mime=mime, use_container_width=True)
                
                st.balloons()
                
            except Exception as e:
                st.error(f"Error: {str(e)}")

elif page == "🔧 PDF Tools":
    st.markdown("""<div class="card"><div style="font-size:16px; font-weight:800;">PDF Tools</div><div class="subtitle">Merge, split, or rotate PDF documents.</div></div>""", unsafe_allow_html=True)
    st.markdown("")
    
    tool_tab1, tool_tab2, tool_tab3 = st.tabs(["Merge PDFs", "Split PDF", "Rotate PDF"])
    
    with tool_tab1:
        uploaded_files = st.file_uploader("Upload PDFs to merge (2 or more)", type=['pdf'], accept_multiple_files=True, key="merge_upload")
        if uploaded_files and len(uploaded_files) > 1:
            if st.button("🔄 Merge PDFs", use_container_width=True):
                with st.spinner("Merging..."):
                    merged_pdf = merge_pdfs(uploaded_files)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    st.success(f"Merged {len(uploaded_files)} PDFs!")
                    st.download_button(label="💾 Download Merged PDF", data=merged_pdf.getvalue(), file_name=f"merged_{timestamp}.pdf", mime="application/pdf", use_container_width=True)
    
    with tool_tab2:
        split_file = st.file_uploader("Upload PDF to split", type=['pdf'], key="split_upload")
        if split_file:
            try:
                with fitz.open(stream=split_file.getvalue(), filetype="pdf") as doc:
                    total_pages = len(doc)
                st.markdown(f"**Total pages: {total_pages}**")
            except:
                total_pages = 1
            
            pages_per_file = st.number_input("Pages per split", min_value=1, value=1)
            if st.button("🔄 Split PDF", use_container_width=True):
                with st.spinner("Splitting..."):
                    splits = split_pdf(split_file.getvalue(), pages_per_file)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    if len(splits) == 1:
                        st.download_button(label="💾 Download Split PDF", data=splits[0].getvalue(), file_name=f"split_{timestamp}.pdf", mime="application/pdf", use_container_width=True)
                    else:
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                            for i, split in enumerate(splits, 1):
                                zip_file.writestr(f"split_part_{i:03d}.pdf", split.getvalue())
                        zip_buffer.seek(0)
                        st.download_button(label=f"💾 Download {len(splits)} PDFs (ZIP)", data=zip_buffer.getvalue(), file_name=f"splits_{timestamp}.zip", mime="application/zip", use_container_width=True)
                    st.success(f"Split into {len(splits)} file(s)!")
    
    with tool_tab3:
        rotate_file = st.file_uploader("Upload PDF to rotate", type=['pdf'], key="rotate_upload")
        rotation = st.selectbox("Rotation", [90, 180, 270], format_func=lambda x: f"{x}° clockwise")
        if rotate_file and st.button("🔄 Rotate PDF", use_container_width=True):
            with st.spinner("Rotating..."):
                rotated_pdf = rotate_pdf(rotate_file.getvalue(), rotation)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.success(f"Rotated by {rotation}°!")
                st.download_button(label="💾 Download Rotated PDF", data=rotated_pdf.getvalue(), file_name=f"rotated_{timestamp}.pdf", mime="application/pdf", use_container_width=True)

elif page == "📊 History":
    st.markdown("""<div class="card"><div style="font-size:16px; font-weight:800;">Conversion History</div><div class="subtitle">View your recent document conversions.</div></div>""", unsafe_allow_html=True)
    st.markdown("")
    
    history = get_user_history(st.session_state.username)
    if history:
        df_history = pd.DataFrame(history, columns=['ID', 'Username', 'Filename', 'Output Format', 'Timestamp', 'File Size'])
        df_history['File Size'] = df_history['File Size'].apply(lambda x: f"{x/1024:.2f} KB")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"<div class='metric'><div class='metric-k'>Conversions</div><div class='metric-v'>{len(df_history)}</div></div>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<div class='metric'><div class='metric-k'>Formats</div><div class='metric-v'>{len(df_history['Output Format'].unique())}</div></div>", unsafe_allow_html=True)
        with col3:
            st.markdown(f"<div class='metric'><div class='metric-k'>Files</div><div class='metric-v'>{len(df_history['Filename'].unique())}</div></div>", unsafe_allow_html=True)
        
        st.dataframe(df_history[['Filename', 'Output Format', 'Timestamp', 'File Size']], use_container_width=True)
        
        csv_buffer = io.StringIO()
        df_history.to_csv(csv_buffer, index=False)
        st.download_button(label="📥 Download History (CSV)", data=csv_buffer.getvalue(), file_name=f"history_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv", use_container_width=True)
    else:
        st.info("No conversion history yet.")

elif page == "⚙️ Settings":
    st.markdown("""<div class="card"><div style="font-size:16px; font-weight:800;">Settings</div><div class="subtitle">Configure your preferences.</div></div>""", unsafe_allow_html=True)
    st.markdown("")
    st.markdown("### Account Information")
    st.markdown(f"**Username:** {st.session_state.username}")
    st.markdown(f"**Session:** {st.session_state.session_id}")
    st.markdown(f"**Version:** {APP_VERSION}")

st.markdown("")
st.markdown(f"""<div class="card-soft" style="text-align:center;"><div style="font-weight:800;">⚡ {APP_NAME} v{APP_VERSION}</div><div class="subtitle">Secure session • {datetime.now().strftime("%Y-%m-%d %H:%M")} • User: {st.session_state.username}</div></div>""", unsafe_allow_html=True)

st.markdown("")
logout_c1, logout_c2, logout_c3 = st.columns([1, 1, 1])
with logout_c2:
    if st.button("Logout", use_container_width=True):
        logout()
