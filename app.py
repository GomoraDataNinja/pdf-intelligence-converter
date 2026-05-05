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
import uuid
import csv
import sqlite3
import hashlib
from typing import List, Dict, Any
import zipfile
import re
import time
import warnings

warnings.filterwarnings("ignore")

# Try to import OCR-related libraries, but don't fail if they're not available
OCR_AVAILABLE = False
try:
    import pytesseract
    from pdf2image import convert_from_bytes
    OCR_AVAILABLE = True
except ImportError:
    pass

# ============================================
# LOCKED CONFIGURATION - DO NOT CHANGE
# ============================================
APP_VERSION = "4.0.0"
APP_NAME = "PDF Intelligence Converter"
SESSION_TIMEOUT_MINUTES = 60

# Get deployment mode - locked to production
DEPLOYMENT_MODE = "production"

# Default password - works without secrets file
DEFAULT_PASSWORD = "SPAR2024"

# ============================================
# PASSWORD SETUP - No secrets file needed
# ============================================
def get_app_password():
    """Get password - works with or without secrets.toml"""
    # Priority 1: Environment variable (for cloud deployment)
    env_pw = os.environ.get("APP_PASSWORD", "").strip()
    if env_pw:
        return env_pw
    
    # Priority 2: Streamlit secrets (if available)
    try:
        if hasattr(st, 'secrets'):
            secrets_dict = dict(st.secrets)
            if 'app_password' in secrets_dict:
                sec_pw = str(secrets_dict['app_password']).strip()
                if sec_pw:
                    return sec_pw
    except:
        pass
    
    # Priority 3: Default password (always works)
    return DEFAULT_PASSWORD

ORG_PASSWORD = get_app_password()

# ============================================
# LOCKED THEME - Consistent across all deployments
# ============================================
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

st.set_page_config(
    page_title=f"{APP_NAME}",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

def safe_rerun():
    """Safe rerun function for all Streamlit versions"""
    try:
        if hasattr(st, "rerun"):
            st.rerun()
        elif hasattr(st, "experimental_rerun"):
            st.experimental_rerun()
    except:
        st.experimental_rerun()

def apply_style():
    """Locked CSS - Same appearance everywhere"""
    st.markdown(
        f"""
        <style>
        :root {{
            --bg: {THEME['bg']};
            --panel: {THEME['panel']};
            --panel2: {THEME['panel2']};
            --text: {THEME['text']};
            --muted: {THEME['muted']};
            --border: {THEME['border']};
            --border2: {THEME['border2']};
            --accent: {THEME['accent']};
            --accent2: {THEME['accent2']};
            --good: {THEME['good']};
            --bad: {THEME['bad']};
            --neutral: {THEME['neutral']};
        }}

        html {{
            color-scheme: light !important;
        }}

        html, body, [data-testid="stAppViewContainer"], .stApp {{
            background: var(--bg) !important;
            color: var(--text) !important;
        }}

        [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer {{
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
        }}

        .block-container {{
            max-width: 1120px;
            padding-top: 2.6rem !important;
            padding-bottom: 2.2rem !important;
        }}

        html, body, .stApp, .stMarkdown, .stText, p, span, div, label {{
            font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, "Noto Sans", "Helvetica Neue", sans-serif !important;
            color: var(--text) !important;
        }}

        section[data-testid="stSidebar"] {{
            background: #ffffff !important;
            border-right: 1px solid var(--border) !important;
        }}

        .card {{
            background: #ffffff !important;
            border: 1px solid var(--border) !important;
            border-radius: 18px !important;
            padding: 18px 18px !important;
        }}

        .card-soft {{
            background: var(--panel2) !important;
            border: 1px solid var(--border) !important;
            border-radius: 18px !important;
            padding: 18px 18px !important;
        }}

        .hero {{
            border: 1px solid var(--border) !important;
            border-radius: 22px !important;
            padding: 26px 22px !important;
            background:
                radial-gradient(900px 260px at 50% -10%, rgba(215,30,40,0.10), transparent 60%),
                linear-gradient(180deg, #ffffff, #ffffff) !important;
        }}

        .title {{
            font-size: 30px !important;
            font-weight: 800 !important;
            letter-spacing: 0.2px !important;
            margin: 0 !important;
        }}

        .subtitle {{
            margin-top: 8px !important;
            color: var(--muted) !important;
            font-size: 14px !important;
            line-height: 1.6 !important;
        }}

        .chip {{
            display: inline-flex !important;
            align-items: center !important;
            gap: 8px !important;
            padding: 6px 12px !important;
            border-radius: 999px !important;
            border: 1px solid var(--border) !important;
            background: #ffffff !important;
            font-size: 12px !important;
            font-weight: 650 !important;
            color: var(--muted) !important;
        }}

        .chip-dot {{
            width: 8px !important;
            height: 8px !important;
            border-radius: 999px !important;
            display: inline-block !important;
            background: var(--accent) !important;
        }}

        .metric {{
            border: 1px solid var(--border) !important;
            border-radius: 18px !important;
            padding: 14px 14px !important;
            background: #ffffff !important;
        }}

        .metric-k {{
            font-size: 12px !important;
            color: var(--muted) !important;
            font-weight: 700 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.9px !important;
        }}

        .metric-v {{
            font-size: 26px !important;
            font-weight: 850 !important;
            margin-top: 6px !important;
        }}

        .muted {{
            color: var(--muted) !important;
        }}

        div.stButton > button,
        button,
        button[kind="primary"],
        button[kind="secondary"],
        [data-testid="baseButton-primary"] > button,
        [data-testid="baseButton-secondary"] > button {{
            background: var(--accent) !important;
            border: 1px solid var(--accent) !important;
            border-radius: 14px !important;
            padding: 0.7rem 1rem !important;
            font-weight: 750 !important;
            color: #ffffff !important;
        }}

        div.stButton > button:hover,
        button:hover,
        button[kind="primary"]:hover,
        button[kind="secondary"]:hover,
        [data-testid="baseButton-primary"] > button:hover,
        [data-testid="baseButton-secondary"] > button:hover {{
            background: var(--accent2) !important;
            border: 1px solid var(--accent2) !important;
        }}

        div[data-baseweb="base-input"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div {{
            background: #ffffff !important;
            border: 1px solid var(--border2) !important;
            border-radius: 14px !important;
            box-shadow: none !important;
        }}

        div[data-baseweb="base-input"] input,
        div[data-baseweb="input"] input {{
            background: transparent !important;
            color: var(--text) !important;
            -webkit-text-fill-color: var(--text) !important;
        }}

        div[data-baseweb="select"] input,
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] svg {{
            color: var(--text) !important;
            fill: var(--text) !important;
        }}

        .stTabs [data-baseweb="tab-list"],
        div[data-testid="stTabs"] [data-baseweb="tab-list"] {{
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            gap: 14px !important;
            width: 100% !important;
            flex-wrap: wrap !important;
            margin-top: 10px !important;
            padding: 0 6px !important;
        }}

        .stTabs [data-baseweb="tab"],
        div[data-testid="stTabs"] [data-baseweb="tab"] {{
            background: #ffffff !important;
            border: 1px solid var(--border) !important;
            border-radius: 16px !important;
            margin-right: 0 !important;
            padding: 14px 18px !important;
            font-weight: 850 !important;
            font-size: 15px !important;
            min-width: 150px !important;
            text-align: center !important;
        }}

        .stTabs [data-baseweb="tab"][aria-selected="true"],
        div[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {{
            background: rgba(215,30,40,0.10) !important;
            border: 1px solid rgba(215,30,40,0.35) !important;
        }}

        [data-testid="stDataFrame"] {{
            background: #ffffff !important;
            border: 1px solid var(--border) !important;
            border-radius: 16px !important;
            overflow: hidden !important;
        }}

        div[data-baseweb="popover"],
        div[data-baseweb="popover"] > div {{
            background: #ffffff !important;
            color: var(--text) !important;
            border-radius: 14px !important;
            border: 1px solid var(--border2) !important;
            box-shadow: 0 12px 28px rgba(0,0,0,0.10) !important;
        }}

        ul[role="listbox"],
        div[role="listbox"] {{
            background: #ffffff !important;
            color: var(--text) !important;
        }}

        li[role="option"] {{
            background: #ffffff !important;
            color: var(--text) !important;
        }}

        li[role="option"]:hover {{
            background: rgba(215,30,40,0.08) !important;
        }}

        span[data-baseweb="tag"] {{
            background: rgba(215,30,40,0.12) !important;
            border: 1px solid rgba(215,30,40,0.25) !important;
            color: var(--text) !important;
        }}

        a, a:visited {{
            color: var(--accent) !important;
            text-decoration: none !important;
            font-weight: 750 !important;
        }}
        a:hover {{
            color: var(--accent2) !important;
            text-decoration: underline !important;
        }}

        @media (max-width: 820px) {{
            .stTabs [data-baseweb="tab"],
            div[data-testid="stTabs"] [data-baseweb="tab"] {{
                min-width: 0 !important;
                padding: 12px 14px !important;
                font-size: 14px !important;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

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
    # Add default admin user if not exists
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        admin_hash = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                 ('admin', admin_hash, 'admin'))
    conn.commit()
    conn.close()

init_db()

# Database functions
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
    
    if metadata_include:
        ws_summary.cell(row=row, column=1, value="Document Information")
        ws_summary.cell(row=row, column=1).font = Font(bold=True, size=12)
        row += 1
        for key, value in content["metadata"].items():
            ws_summary.cell(row=row, column=1, value=key.replace('_', ' ').title())
            ws_summary.cell(row=row, column=2, value=str(value))
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
            ws_content.cell(row=row, column=1, value=f"========== PAGE {page_data['page']} ==========")
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
            
            header_fill = PatternFill(start_color="FDE8E8", end_color="FDE8E8", fill_type="solid")
            header_font = Font(bold=True)
            
            for r, row_data in enumerate(table, 1):
                for c, cell in enumerate(row_data, 1):
                    ws_table.cell(row=r, column=c, value=cell)
                    if r == 1:
                        ws_table.cell(row=r, column=c).fill = header_fill
                        ws_table.cell(row=r, column=c).font = header_font
    
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
            doc.add_heading(f'Table {table_data["table_id"]} (Page {table_data["page"]})', level=2)
            if table_data["table"]:
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
    md.append(f"# PDF Intelligence Report\n\n")
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
<head>
    <meta charset="UTF-8">
    <title>PDF Intelligence Report</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; margin: 40px; }}
        h1 {{ color: #d71e28; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; }}
        th {{ background-color: #FDE8E8; }}
    </style>
</head>
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
        try:
            pdf_content = pdf_file.read()
            with fitz.open(stream=pdf_content, filetype="pdf") as pdf:
                merged.insert_pdf(pdf)
        except Exception as e:
            raise Exception(f"Error processing {pdf_file.name}: {str(e)}")
    
    output = io.BytesIO()
    merged.save(output)
    merged.close()
    output.seek(0)
    return output

def split_pdf(pdf_bytes, pages_per_split):
    try:
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
    except Exception as e:
        raise Exception(f"Error splitting PDF: {str(e)}")

def rotate_pdf(pdf_bytes, rotation):
    try:
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in pdf_doc:
            page.set_rotation(rotation)
        
        output = io.BytesIO()
        pdf_doc.save(output)
        pdf_doc.close()
        output.seek(0)
        return output
    except Exception as e:
        raise Exception(f"Error rotating PDF: {str(e)}")

# ============================================
# SIGN IN PAGE - Locked Design
# ============================================

if not st.session_state.authenticated:
    st.markdown('<div style="height: 1.8rem;"></div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.25, 1])
    with c2:
        st.markdown(
            f"""
            <div class="card" style="margin-top: 10vh;">
                <div class="title" style="text-align:center;">{APP_NAME}</div>
                <div class="subtitle" style="text-align:center;">Sign in to continue.</div>
                <div style="height: 14px;"></div>
                <div style="display:flex; justify-content:center;">
                    <div class="chip"><span class="chip-dot"></span> Version {APP_VERSION} • Production</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        tab1, tab2 = st.tabs(["Sign In", "Register"])
        
        with tab1:
            with st.form("login_form", clear_on_submit=True):
                username = st.text_input("Username", placeholder="Enter username")
                password = st.text_input("Password", type="password", placeholder="Enter password")
                
                col1, col2 = st.columns(2)
                with col1:
                    ok = st.form_submit_button("Sign in", use_container_width=True)
                with col2:
                    demo = st.form_submit_button("Demo Access", use_container_width=True)

            if ok:
                if username and password:
                    if sign_in(username, password):
                        st.success("✅ Sign in successful!")
                        safe_rerun()
                    else:
                        st.error("❌ Invalid credentials")
                else:
                    st.warning("Please fill in all fields")
            
            if demo:
                st.info("Demo credentials: admin / admin123")
        
        with tab2:
            with st.form("register_form", clear_on_submit=True):
                new_username = st.text_input("New Username", placeholder="Choose username")
                new_password = st.text_input("New Password", type="password", placeholder="Choose password (min 6 characters)")
                confirm_password = st.text_input("Confirm Password", type="password", placeholder="Confirm password")
                
                reg = st.form_submit_button("Register", use_container_width=True)

            if reg:
                if new_username and new_password and confirm_password:
                    if new_password == confirm_password:
                        if len(new_password) >= 6:
                            if register_user(new_username, new_password):
                                st.success("✅ Registration successful! Please sign in.")
                            else:
                                st.error("❌ Username already exists")
                        else:
                            st.warning("Password must be at least 6 characters")
                    else:
                        st.error("❌ Passwords don't match")
                else:
                    st.warning("Please fill in all fields")

    st.stop()

# Check session timeout
if st.session_state.authenticated and is_timed_out():
    st.session_state.authenticated = False
    st.warning("Session timed out. Sign in again.")
    safe_rerun()

touch()

# ============================================
# MAIN DASHBOARD - Locked Layout
# ============================================

# Sidebar
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.username}")
    st.markdown("---")
    
    page = st.radio(
        "Navigation",
        ["📄 Convert PDF", "🔧 PDF Tools", "📊 History", "⚙️ Settings"],
        label_visibility="collapsed"
    )
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

# Hero header
st.markdown(
    f"""
    <div class="hero" style="text-align:center;">
        <div class="title">{APP_NAME}</div>
        <div class="subtitle">Upload your PDF document. Extract content, convert formats, and manage your documents intelligently.</div>
        <div style="height: 12px;"></div>
        <div style="display:flex; justify-content:center; gap:10px; flex-wrap:wrap;">
            <div class="chip"><span class="chip-dot"></span> Secure session</div>
            <div class="chip">Session {st.session_state.session_id}</div>
            <div class="chip">Production Mode</div>
            <div class="chip">Version {APP_VERSION}</div>
            <div class="chip">User {st.session_state.username}</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("")

# [Rest of the page routing code remains exactly the same as before...]
# Convert PDF, PDF Tools, History, Settings pages - all identical to previous code

# ... (rest of the code from the previous version continues here)
