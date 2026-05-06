"""
PDF Intelligence Converter - Premium Batsirai Design
Production Version 4.1.0 - Enhanced with Batch Processing, OCR Language Detection, Mobile Responsiveness, Notifications & DB Migrations
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
import gc
from collections import deque
from functools import wraps

warnings.filterwarnings("ignore")
logging.getLogger('streamlit').setLevel(logging.ERROR)

OCR_AVAILABLE = False
try:
    import pytesseract
    from pdf2image import convert_from_bytes
    from langdetect import detect, DetectorFactory
    DetectorFactory.seed = 0
    OCR_AVAILABLE = True
except ImportError:
    pass

APP_VERSION = "4.1.0"
APP_NAME = "PDF Intelligence Converter"
DEPLOYMENT_MODE = os.environ.get("DEPLOYMENT_MODE", "production")
SESSION_TIMEOUT_MINUTES = 60
MAX_BATCH_SIZE = 20
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# ============================================
# NOTIFICATION SYSTEM
# ============================================
class NotificationSystem:
    """Enhanced notification system with persistence and categories"""
    
    def __init__(self):
        if "notifications" not in st.session_state:
            st.session_state.notifications = deque(maxlen=50)
        if "unread_count" not in st.session_state:
            st.session_state.unread_count = 0
    
    def add(self, message: str, type: str = "info", duration: int = 5, action_url: str = None):
        notification = {
            "id": hashlib.md5(f"{message}{datetime.now()}".encode()).hexdigest()[:8],
            "message": message,
            "type": type,
            "timestamp": datetime.now(),
            "read": False,
            "duration": duration,
            "action_url": action_url
        }
        st.session_state.notifications.appendleft(notification)
        st.session_state.unread_count += 1
        
        if type == "success":
            st.success(message)
        elif type == "error":
            st.error(message)
        elif type == "warning":
            st.warning(message)
        else:
            st.info(message)
        
        return notification["id"]
    
    def mark_as_read(self, notification_id: str):
        for notif in st.session_state.notifications:
            if notif["id"] == notification_id:
                if not notif["read"]:
                    notif["read"] = True
                    st.session_state.unread_count = max(0, st.session_state.unread_count - 1)
                break
    
    def mark_all_read(self):
        for notif in st.session_state.notifications:
            notif["read"] = True
        st.session_state.unread_count = 0
    
    def clear_all(self):
        st.session_state.notifications.clear()
        st.session_state.unread_count = 0
    
    def get_unread_count(self) -> int:
        return st.session_state.unread_count
    
    def render_notification_center(self):
        if not st.session_state.notifications:
            st.info("📭 No notifications")
            return
        
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.markdown(f"**📬 Notifications** ({len([n for n in st.session_state.notifications if not n['read']])} unread)")
        with col2:
            if st.button("✓ Mark all read", key="mark_all_read", use_container_width=True):
                self.mark_all_read()
                st.rerun()
        with col3:
            if st.button("🗑 Clear all", key="clear_all_notif", use_container_width=True):
                self.clear_all()
                st.rerun()
        
        st.markdown("---")
        
        for notif in st.session_state.notifications:
            opacity = "0.7" if notif["read"] else "1"
            with st.container():
                st.markdown(f"""
                <div style="
                    padding: 12px;
                    border-radius: 8px;
                    margin-bottom: 8px;
                    opacity: {opacity};
                    background: {'#f0f0f0' if st.session_state.theme == 'light' else '#2d2d2d'};
                ">
                    <strong>{notif['type'].upper()}</strong><br>
                    {notif['message']}
                    <div style="font-size: 11px; margin-top: 4px;">
                        {notif['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                if not notif["read"]:
                    if st.button(f"Mark read", key=f"read_{notif['id']}", use_container_width=True):
                        self.mark_as_read(notif["id"])
                        st.rerun()

# ============================================
# DATABASE MIGRATIONS
# ============================================
class DatabaseManager:
    def __init__(self, db_path='users.db'):
        self.db_path = db_path
        self.current_version = 2
    
    def get_db_version(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute("SELECT version FROM db_version ORDER BY version DESC LIMIT 1")
            version = c.fetchone()
            if version:
                return version[0]
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()
        return 0
    
    def set_db_version(self, version):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS db_version (version INTEGER, applied_at TIMESTAMP)")
        c.execute("INSERT INTO db_version (version, applied_at) VALUES (?, ?)", 
                 (version, datetime.now()))
        conn.commit()
        conn.close()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (username TEXT PRIMARY KEY, 
                      password_hash TEXT, 
                      role TEXT DEFAULT 'user',
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      last_login TIMESTAMP)''')
        
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
            c.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                     ('admin', admin_hash, 'admin', datetime.now()))
        
        conn.commit()
        conn.close()
        self.set_db_version(1)
    
    def migrate_v1_to_v2(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            c.execute("PRAGMA table_info(conversion_history)")
            columns = [col[1] for col in c.fetchall()]
            
            new_columns = {
                "processing_time": "REAL",
                "error_message": "TEXT",
                "file_pages": "INTEGER",
                "batch_id": "TEXT",
                "conversion_status": "TEXT DEFAULT 'completed'"
            }
            
            for col_name, col_type in new_columns.items():
                if col_name not in columns:
                    c.execute(f"ALTER TABLE conversion_history ADD COLUMN {col_name} {col_type}")
            
            c.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON conversion_history(timestamp)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_username_timestamp ON conversion_history(username, timestamp)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_batch_id ON conversion_history(batch_id)")
            
            c.execute("""
                CREATE TABLE IF NOT EXISTS batch_jobs (
                    batch_id TEXT PRIMARY KEY,
                    username TEXT,
                    created_at TIMESTAMP,
                    total_files INTEGER,
                    completed_files INTEGER DEFAULT 0,
                    failed_files INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'processing'
                )
            """)
            
            c.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    username TEXT PRIMARY KEY,
                    default_output_format TEXT DEFAULT 'Excel (XLSX)',
                    default_extraction_mode TEXT DEFAULT 'Smart (Text + Tables)',
                    auto_convert BOOLEAN DEFAULT 0,
                    notify_on_completion BOOLEAN DEFAULT 1,
                    theme TEXT DEFAULT 'light'
                )
            """)
            
            c.execute("""
                CREATE TABLE IF NOT EXISTS user_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    action TEXT,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip_address TEXT
                )
            """)
            
            conn.commit()
            self.set_db_version(2)
            return True
        except Exception as e:
            print(f"Migration error: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def run_migrations(self):
        current_version = self.get_db_version()
        
        if current_version < 1:
            self.init_database()
        
        if current_version < 2:
            self.migrate_v1_to_v2()

# ============================================
# BATCH PROCESSING SYSTEM
# ============================================
class BatchProcessor:
    def __init__(self):
        if "batch_jobs" not in st.session_state:
            st.session_state.batch_jobs = {}
        if "active_batch" not in st.session_state:
            st.session_state.active_batch = None
    
    def create_batch_job(self, files: List, output_format: str, extraction_mode: str, 
                        extraction_options: Dict) -> str:
        batch_id = hashlib.md5(f"{st.session_state.username}{datetime.now()}".encode()).hexdigest()[:12]
        
        job = {
            "batch_id": batch_id,
            "username": st.session_state.username,
            "files": [{"name": f.name, "bytes": f.getvalue(), "size": len(f.getvalue())} for f in files],
            "total_files": len(files),
            "completed_files": 0,
            "failed_files": 0,
            "status": "pending",
            "output_format": output_format,
            "extraction_mode": extraction_mode,
            "extraction_options": extraction_options,
            "created_at": datetime.now(),
            "results": [],
            "progress": 0
        }
        
        st.session_state.batch_jobs[batch_id] = job
        st.session_state.active_batch = batch_id
        return batch_id
    
    def process_batch(self, batch_id: str, progress_callback=None):
        if batch_id not in st.session_state.batch_jobs:
            return False
        
        job = st.session_state.batch_jobs[batch_id]
        job["status"] = "processing"
        
        for idx, file_data in enumerate(job["files"]):
            try:
                start_time = time.time()
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(file_data["bytes"])
                    tmp_path = tmp_file.name
                
                content = extract_pdf_intelligent(
                    tmp_path, 
                    job["extraction_mode"], 
                    job["extraction_options"].get("extract_tables", True)
                )
                
                output_buffer = self._convert_content(content, job["output_format"], job["extraction_options"])
                processing_time = time.time() - start_time
                
                result = {
                    "filename": file_data["name"],
                    "success": True,
                    "output": output_buffer,
                    "processing_time": processing_time,
                    "pages": content["pages"],
                    "tables": len(content["tables"])
                }
                
                job["completed_files"] += 1
                job["results"].append(result)
                
                os.unlink(tmp_path)
                
            except Exception as e:
                job["failed_files"] += 1
                job["results"].append({
                    "filename": file_data["name"],
                    "success": False,
                    "error": str(e)
                })
            
            job["progress"] = ((job["completed_files"] + job["failed_files"]) / job["total_files"]) * 100
            if progress_callback:
                progress_callback(job["progress"])
        
        job["status"] = "completed" if job["failed_files"] == 0 else "partial"
        return True
    
    def _convert_content(self, content, output_format, options):
        result_buffer = io.BytesIO()
        
        if output_format == "Excel (XLSX)":
            convert_to_excel(content, result_buffer, options.get("include_metadata", True))
        elif output_format == "Word (DOCX)":
            convert_to_word(content, result_buffer)
        elif output_format == "Text (TXT)":
            text_content = "\n\n".join([p["content"] for p in content["text"]])
            result_buffer = io.BytesIO(text_content.encode('utf-8'))
        elif output_format == "CSV":
            text_stream = io.TextIOWrapper(result_buffer, 'utf-8', newline='')
            writer = csv.writer(text_stream)
            writer.writerow(["Page", "Content"])
            for page in content["text"]:
                writer.writerow([page["page"], page["content"]])
            text_stream.flush()
        elif output_format == "JSON":
            json_content = {
                "metadata": content["metadata"], 
                "pages": content["pages"], 
                "text": [{"page": p["page"], "content": p["content"]} for p in content["text"]], 
                "tables": [{"page": t["page"], "table": t["table"]} for t in content["tables"]]
            }
            result_buffer = io.BytesIO(json.dumps(json_content, indent=2, ensure_ascii=False).encode('utf-8'))
        elif output_format == "Markdown":
            md = convert_to_markdown(content)
            result_buffer = io.BytesIO(md.encode('utf-8'))
        elif output_format == "HTML":
            html_content = convert_to_html(content)
            result_buffer = io.BytesIO(html_content.encode('utf-8'))
        
        result_buffer.seek(0)
        return result_buffer
    
    def get_batch_results_zip(self, batch_id: str) -> io.BytesIO:
        if batch_id not in st.session_state.batch_jobs:
            return None
        
        job = st.session_state.batch_jobs[batch_id]
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for result in job["results"]:
                if result["success"]:
                    ext_map = {
                        "Excel (XLSX)": ".xlsx",
                        "Word (DOCX)": ".docx",
                        "Text (TXT)": ".txt",
                        "CSV": ".csv",
                        "JSON": ".json",
                        "Markdown": ".md",
                        "HTML": ".html"
                    }
                    ext = ext_map.get(job["output_format"], ".txt")
                    filename = Path(result["filename"]).stem + ext
                    zip_file.writestr(filename, result["output"].getvalue())
        
        zip_buffer.seek(0)
        return zip_buffer
    
    def render_batch_status(self, batch_id: str):
        if batch_id not in st.session_state.batch_jobs:
            return
        
        job = st.session_state.batch_jobs[batch_id]
        
        with st.container():
            st.markdown(f"### 📦 Batch Job: {batch_id}")
            progress = job["progress"]
            st.progress(progress / 100)
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Files", job["total_files"])
            with col2:
                st.metric("Completed", job["completed_files"])
            with col3:
                st.metric("Failed", job["failed_files"])
            with col4:
                st.metric("Status", job["status"].upper())
            
            if job["status"] in ["completed", "partial"]:
                results_df = pd.DataFrame([
                    {
                        "File": r["filename"],
                        "Status": "✅ Success" if r["success"] else "❌ Failed",
                        "Pages": r.get("pages", "N/A"),
                        "Tables": r.get("tables", "N/A"),
                        "Time": f"{r.get('processing_time', 0):.2f}s" if r.get("processing_time") else "N/A"
                    }
                    for r in job["results"]
                ])
                st.dataframe(results_df, use_container_width=True)
                
                if job["completed_files"] > 0:
                    zip_buffer = self.get_batch_results_zip(batch_id)
                    if zip_buffer:
                        st.download_button(
                            label=f"📥 Download All Results ({job['completed_files']} files)",
                            data=zip_buffer.getvalue(),
                            file_name=f"batch_{batch_id}_results.zip",
                            mime="application/zip",
                            use_container_width=True
                        )

# ============================================
# OCR LANGUAGE DETECTION
# ============================================
class OCRProcessor:
    def __init__(self):
        self.supported_languages = {
            'eng': 'English', 'spa': 'Spanish', 'fra': 'French', 'deu': 'German',
            'ita': 'Italian', 'por': 'Portuguese', 'rus': 'Russian', 'jpn': 'Japanese',
            'kor': 'Korean', 'chi_sim': 'Chinese (Simplified)', 'ara': 'Arabic'
        }
    
    def detect_language_from_pdf(self, pdf_bytes: bytes, sample_pages: int = 3) -> str:
        if not OCR_AVAILABLE:
            return 'eng'
        
        try:
            images = convert_from_bytes(pdf_bytes, first_page=1, last_page=sample_pages, dpi=100)
            text_samples = []
            for img in images:
                text = pytesseract.image_to_string(img, lang='eng')
                if len(text.strip()) > 50:
                    text_samples.append(text)
            
            if not text_samples:
                return 'eng'
            
            combined_text = " ".join(text_samples)
            detected_lang = detect(combined_text)
            
            lang_map = {
                'en': 'eng', 'es': 'spa', 'fr': 'fra', 'de': 'deu',
                'it': 'ita', 'pt': 'por', 'ru': 'rus', 'ja': 'jpn',
                'ko': 'kor', 'zh-cn': 'chi_sim', 'ar': 'ara'
            }
            
            return lang_map.get(detected_lang[:2], 'eng')
        except:
            return 'eng'
    
    def perform_ocr(self, pdf_bytes: bytes, languages: List[str] = None, dpi: int = 200) -> Dict:
        if not OCR_AVAILABLE:
            return {"text": "", "error": "OCR not available"}
        
        if languages is None:
            languages = ['eng']
        
        try:
            images = convert_from_bytes(pdf_bytes, dpi=dpi)
            all_text = []
            total_pages = len(images)
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for page_num, image in enumerate(images, 1):
                status_text.text(f"Processing page {page_num}/{total_pages}...")
                lang_str = '+'.join(languages)
                page_text = pytesseract.image_to_string(image, lang=lang_str)
                all_text.append({'page': page_num, 'text': page_text, 'length': len(page_text)})
                progress_bar.progress(page_num / total_pages)
            
            status_text.empty()
            progress_bar.empty()
            
            combined_text = "\n\n".join([p['text'] for p in all_text])
            
            return {
                "text": combined_text,
                "pages": all_text,
                "total_pages": total_pages,
                "total_chars": len(combined_text),
                "total_words": len(combined_text.split()),
                "languages_used": languages
            }
        except Exception as e:
            return {"text": "", "error": str(e)}
    
    def render_ocr_interface(self):
        st.markdown("### 🔍 OCR with Language Detection")
        
        uploaded_file = st.file_uploader("Upload PDF for OCR", type=['pdf'], key="ocr_upload")
        
        if uploaded_file:
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🔮 Auto-detect Language", use_container_width=True):
                    with st.spinner("Detecting language..."):
                        detected_lang = self.detect_language_from_pdf(uploaded_file.getvalue())
                        st.session_state.detected_lang = detected_lang
                        st.success(f"Detected language: {self.supported_languages.get(detected_lang, detected_lang)}")
            
            with col2:
                available_langs = list(self.supported_languages.keys())
                selected_langs = st.multiselect(
                    "Or select languages manually",
                    options=available_langs,
                    format_func=lambda x: self.supported_languages[x],
                    default=[st.session_state.get('detected_lang', 'eng')]
                )
            
            dpi = st.slider("OCR Quality (DPI)", 100, 300, 200)
            
            if st.button("🚀 Start OCR", use_container_width=True):
                with st.spinner("Performing OCR..."):
                    result = self.perform_ocr(uploaded_file.getvalue(), selected_langs or ['eng'], dpi)
                    
                    if "error" in result:
                        st.error(f"OCR failed: {result['error']}")
                    else:
                        st.success(f"OCR complete! Extracted {result['total_chars']} characters")
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Pages", result['total_pages'])
                        with col2:
                            st.metric("Characters", result['total_chars'])
                        with col3:
                            st.metric("Words", result['total_words'])
                        
                        with st.expander("View Extracted Text"):
                            st.text_area("OCR Result", result['text'], height=400)
                        
                        download_buffer = io.BytesIO(result['text'].encode('utf-8'))
                        st.download_button(
                            label="📥 Download OCR Text",
                            data=download_buffer.getvalue(),
                            file_name=f"ocr_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                            mime="text/plain",
                            use_container_width=True
                        )

# ============================================
# MOBILE RESPONSIVENESS
# ============================================
class MobileOptimizer:
    def __init__(self):
        self.is_mobile = self._detect_mobile()
        if self.is_mobile:
            self._apply_mobile_styles()
    
    def _detect_mobile(self) -> bool:
        try:
            user_agent = st.get_option("browser.userAgent", "")
            mobile_keywords = ['Android', 'iPhone', 'iPad', 'iPod', 'BlackBerry', 'Windows Phone', 'Mobile']
            return any(keyword in user_agent for keyword in mobile_keywords)
        except:
            return False
    
    def _apply_mobile_styles(self):
        st.markdown("""
        <style>
        @media (max-width: 768px) {
            .block-container { padding: 0.5rem !important; }
            .card, .card-soft, .hero { padding: 16px !important; }
            .title, .login-title { font-size: 20px !important; }
            .metric-v { font-size: 20px !important; }
            div.stButton > button { min-height: 44px !important; }
            input, select, textarea { font-size: 16px !important; }
        }
        @media (hover: none) and (pointer: coarse) {
            .stButton button, .stDownloadButton button { min-height: 44px !important; }
        }
        </style>
        """, unsafe_allow_html=True)
    
    def render_mobile_notice(self):
        if self.is_mobile:
            with st.sidebar:
                st.info("📱 Mobile Mode Active • Optimized for touch")

# ============================================
# PDF PROCESSING FUNCTIONS
# ============================================
def extract_pdf_intelligent(pdf_path, mode, extract_tables_flag):
    content = {"text": [], "tables": [], "pages": 0, "metadata": {}}
    
    try:
        doc = fitz.open(pdf_path)
        content["metadata"] = {
            "title": doc.metadata.get("title", "Unknown"),
            "author": doc.metadata.get("author", "Unknown"),
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
    md = ["# PDF Intelligence Report\n\n"]
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
    html = [f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>PDF Intelligence Report</title>
<style>
body{{font-family:sans-serif;margin:40px}}
h1{{color:#d71e28}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ddd;padding:8px}}
th{{background-color:#FDE8E8}}
</style>
</head>
<body>
<h1>PDF Intelligence Report</h1>
<p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"""]
    
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
                    html.append('</table>')
            html.append('<table><br>')
    
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
# DATABASE FUNCTIONS
# ============================================
def save_conversion_history(username, filename, output_format, file_size, processing_time=None, 
                           file_pages=None, batch_id=None, status="completed", error=None):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    try:
        c.execute("SELECT processing_time FROM conversion_history LIMIT 1")
    except sqlite3.OperationalError:
        db_manager.migrate_v1_to_v2()
    
    c.execute("""
        INSERT INTO conversion_history 
        (username, filename, output_format, file_size, timestamp, processing_time, file_pages, batch_id, conversion_status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (username, filename, output_format, file_size, datetime.now(), 
          processing_time, file_pages, batch_id, status, error))
    
    conn.commit()
    conn.close()

def get_user_history(username, limit=100):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("""
        SELECT * FROM conversion_history 
        WHERE username=? 
        ORDER BY timestamp DESC 
        LIMIT ?
    """, (username, limit))
    history = c.fetchall()
    conn.close()
    return history

def get_user_preferences(username):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM user_preferences WHERE username=?", (username,))
    prefs = c.fetchone()
    conn.close()
    
    if prefs:
        return {
            "default_output_format": prefs[1],
            "default_extraction_mode": prefs[2],
            "auto_convert": prefs[3],
            "notify_on_completion": prefs[4],
            "theme": prefs[5]
        }
    return {
        "default_output_format": "Excel (XLSX)",
        "default_extraction_mode": "Smart (Text + Tables)",
        "auto_convert": False,
        "notify_on_completion": True,
        "theme": "light"
    }

def save_user_preferences(username, preferences):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO user_preferences 
        (username, default_output_format, default_extraction_mode, auto_convert, notify_on_completion, theme)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (username, 
          preferences.get("default_output_format", "Excel (XLSX)"),
          preferences.get("default_extraction_mode", "Smart (Text + Tables)"),
          preferences.get("auto_convert", False),
          preferences.get("notify_on_completion", True),
          preferences.get("theme", "light")))
    conn.commit()
    conn.close()

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
        c.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                 (username, password_hash, role, datetime.now()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# ============================================
# STREAMLIT UI SETUP
# ============================================
def init_session_state():
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
    if "theme" not in st.session_state:
        st.session_state.theme = "light"
    if "detected_lang" not in st.session_state:
        st.session_state.detected_lang = "eng"

def get_theme_colors():
    if st.session_state.theme == "dark":
        return {
            "bg": "#0f0f0f", "panel": "#1a1a1a", "panel2": "#1e1e1e",
            "text": "#ffffff", "muted": "#a0a0a0", "border": "rgba(255,255,255,0.10)",
            "accent": "#ff4444", "accent2": "#cc0000",
        }
    else:
        return {
            "bg": "#ffffff", "panel": "#ffffff", "panel2": "#f7f7f7",
            "text": "#111111", "muted": "#5b5b5b", "border": "rgba(0,0,0,0.10)",
            "accent": "#d71e28", "accent2": "#b5161f",
        }

def apply_style():
    t = get_theme_colors()
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * {{ font-family: 'Inter', sans-serif !important; }}
    html, body, [data-testid="stAppViewContainer"], .stApp {{ background: {t['bg']} !important; color: {t['text']} !important; }}
    #MainMenu, footer {{ visibility: hidden; }}
    .block-container {{ max-width: 1200px !important; padding: 2rem !important; margin: 0 auto !important; }}
    section[data-testid="stSidebar"] {{ background: {t['panel']} !important; border-right: 1px solid {t['border']} !important; }}
    .card {{ background: {t['panel']}; border: 1px solid {t['border']}; border-radius: 18px; padding: 24px; margin-bottom: 20px; }}
    .card-soft {{ background: {t['panel2']}; border: 1px solid {t['border']}; border-radius: 18px; padding: 24px; margin-bottom: 20px; }}
    .hero {{ border: 1px solid {t['border']}; border-radius: 22px; padding: 32px 24px; margin-bottom: 24px; }}
    .title {{ font-size: 28px; font-weight: 800; color: {t['text']}; }}
    .subtitle {{ margin-top: 8px; color: {t['muted']}; font-size: 14px; }}
    .chip {{ display: inline-flex; align-items: center; gap: 8px; padding: 8px 14px; border-radius: 999px; border: 1px solid {t['border']}; font-size: 12px; background: {t['panel']}; }}
    .metric {{ border: 1px solid {t['border']}; border-radius: 18px; padding: 20px; background: {t['panel']}; }}
    .metric-v {{ font-size: 28px; font-weight: 850; color: {t['text']}; }}
    div.stButton > button {{ background: {t['accent']} !important; color: white !important; border-radius: 12px !important; padding: 12px 20px !important; font-weight: 700 !important; width: 100% !important; }}
    div.stButton > button:hover {{ background: {t['accent2']} !important; }}
    [data-testid="stFileUploader"] {{ border: 2px dashed {t['border']} !important; border-radius: 16px !important; padding: 32px 24px !important; }}
    </style>
    """, unsafe_allow_html=True)

def sign_in(username, password):
    if verify_user(username, password):
        st.session_state.authenticated = True
        st.session_state.username = username
        st.session_state.last_activity = datetime.now()
        return True
    return False

def logout():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

def safe_rerun():
    try:
        st.rerun()
    except:
        pass

def toggle_theme():
    st.session_state.theme = "dark" if st.session_state.theme == "light" else "light"
    safe_rerun()

def touch():
    st.session_state.last_activity = datetime.now()

def is_timed_out():
    last = st.session_state.get("last_activity")
    if not last:
        return False
    return (datetime.now() - last).total_seconds() > SESSION_TIMEOUT_MINUTES * 60

# ============================================
# MAIN APP
# ============================================
st.set_page_config(page_title=f"{APP_NAME}", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")
init_session_state()
apply_style()

db_manager = DatabaseManager()
db_manager.run_migrations()

notification_system = NotificationSystem()
mobile_optimizer = MobileOptimizer()
batch_processor = BatchProcessor()
ocr_processor = OCRProcessor()

# Authentication
if not st.session_state.authenticated:
    theme_icon = "🌙" if st.session_state.theme == "light" else "☀️"
    st.markdown(f'<div style="position:fixed;top:20px;right:20px;z-index:9999;">', unsafe_allow_html=True)
    if st.button(f"{theme_icon} Theme", key="theme_toggle_login"):
        toggle_theme()
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('<div style="height: 1.8rem;"></div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.25, 1])
    with c2:
        st.markdown(f"""
        <div class="card" style="margin-top: 10vh;">
            <div class="title" style="text-align:center; font-size:24px;">⚡ {APP_NAME}</div>
            <div class="subtitle" style="text-align:center;">Sign in to continue.</div>
        </div>
        """, unsafe_allow_html=True)

        tab1, tab2 = st.tabs(["Sign In", "Register"])
        
        with tab1:
            with st.form("login_form", clear_on_submit=True):
                username = st.text_input("Username", placeholder="Enter username")
                password = st.text_input("Password", type="password", placeholder="Enter password")
                ok = st.form_submit_button("Sign in", use_container_width=True)
            
            if ok and username and password:
                if sign_in(username, password):
                    st.success("Sign in successful!")
                    safe_rerun()
                else:
                    st.error("Invalid credentials")
        
        with tab2:
            with st.form("register_form", clear_on_submit=True):
                new_username = st.text_input("New Username", placeholder="Choose username")
                new_password = st.text_input("New Password", type="password", placeholder="Min 6 characters")
                confirm_password = st.text_input("Confirm Password", type="password", placeholder="Confirm password")
                reg = st.form_submit_button("Register", use_container_width=True)
            
            if reg and new_username and new_password and confirm_password:
                if new_password == confirm_password and len(new_password) >= 6:
                    if register_user(new_username, new_password):
                        st.success("Registration successful! Please sign in.")
                    else:
                        st.error("Username already exists")
    st.stop()

if st.session_state.authenticated and is_timed_out():
    st.session_state.authenticated = False
    st.warning("Session timed out. Sign in again.")
    safe_rerun()

touch()

# Sidebar
with st.sidebar:
    unread_count = notification_system.get_unread_count()
    st.markdown(f"**⚡ {st.session_state.username}**" + (f" 🔔({unread_count})" if unread_count > 0 else ""))
    st.markdown("---")
    
    if st.button("🌙 Dark Mode" if st.session_state.theme == "light" else "☀️ Light Mode", use_container_width=True):
        toggle_theme()
    
    st.markdown("---")
    page = st.radio("Navigation", [
        "📄 Convert PDF", "📦 Batch Convert", "🔍 OCR Scanner",
        "🔧 PDF Tools", "📊 History", "🔔 Notifications", "⚙️ Settings"
    ], label_visibility="collapsed")
    
    st.markdown("---")
    history = get_user_history(st.session_state.username, limit=5)
    if history:
        st.markdown("**Recent Activity**")
        for h in history[:5]:
            st.markdown(f"📄 {str(h[2])[:30]} → {h[3]}")
    
    st.markdown("---")
    if st.button("🚪 Sign Out", use_container_width=True):
        logout()
    
    mobile_optimizer.render_mobile_notice()

# Main content
st.markdown(f"""
<div class="hero" style="text-align:center;">
    <div class="title">⚡ {APP_NAME}</div>
    <div class="subtitle">Upload your PDF document. Extract content, convert formats, and manage your documents intelligently.</div>
    <div style="display:flex; gap:10px; justify-content:center; margin-top:16px;">
        <div class="chip">Version {APP_VERSION}</div>
        <div class="chip">User {st.session_state.username}</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Page routing
if page == "📄 Convert PDF":
    st.markdown('<div class="card"><strong>Document Conversion</strong><br>Upload your PDF for intelligent extraction.</div>', unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Choose a PDF file", type=['pdf'], key="convert_upload")
    if uploaded_file:
        st.info(f"📄 {uploaded_file.name} ({len(uploaded_file.getvalue())/1024:.2f} KB)")
        
        col1, col2 = st.columns(2)
        with col1:
            output_format = st.selectbox("Convert to", ["Excel (XLSX)", "Word (DOCX)", "Text (TXT)", "CSV", "JSON", "Markdown", "HTML"])
        with col2:
            extraction_modes = ["Smart (Text + Tables)", "Text Only", "Tables Only"]
            if OCR_AVAILABLE:
                extraction_modes.append("OCR (Scanned PDFs)")
            extraction_mode = st.selectbox("Extraction mode", extraction_modes)
        
        extract_tables = st.checkbox("Extract tables", value=True)
        include_metadata = st.checkbox("Include metadata", value=True)
        
        if st.button("🔄 Convert", use_container_width=True):
            with st.spinner("Processing..."):
                try:
                    start_time = time.time()
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        tmp_file.write(uploaded_file.getvalue())
                        tmp_path = tmp_file.name
                    
                    content = extract_pdf_intelligent(tmp_path, extraction_mode, extract_tables)
                    processing_time = time.time() - start_time
                    
                    result_buffer = io.BytesIO()
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    base_name = Path(uploaded_file.name).stem
                    
                    if output_format == "Excel (XLSX)":
                        convert_to_excel(content, result_buffer, include_metadata)
                        filename = f"{base_name}_{timestamp}.xlsx"
                        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    elif output_format == "Word (DOCX)":
                        convert_to_word(content, result_buffer)
                        filename = f"{base_name}_{timestamp}.docx"
                        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    elif output_format == "Text (TXT)":
                        text_content = "\n\n".join([p["content"] for p in content["text"]])
                        result_buffer = io.BytesIO(text_content.encode('utf-8'))
                        filename = f"{base_name}_{timestamp}.txt"
                        mime = "text/plain"
                    elif output_format == "CSV":
                        text_stream = io.TextIOWrapper(result_buffer, 'utf-8', newline='')
                        writer = csv.writer(text_stream)
                        writer.writerow(["Page", "Content"])
                        for p in content["text"]:
                            writer.writerow([p["page"], p["content"]])
                        text_stream.flush()
                        filename = f"{base_name}_{timestamp}.csv"
                        mime = "text/csv"
                    elif output_format == "JSON":
                        json_content = {"metadata": content["metadata"], "pages": content["pages"], "text": content["text"], "tables": content["tables"]}
                        result_buffer = io.BytesIO(json.dumps(json_content, indent=2).encode('utf-8'))
                        filename = f"{base_name}_{timestamp}.json"
                        mime = "application/json"
                    elif output_format == "Markdown":
                        md = convert_to_markdown(content)
                        result_buffer = io.BytesIO(md.encode('utf-8'))
                        filename = f"{base_name}_{timestamp}.md"
                        mime = "text/markdown"
                    else:
                        html_content = convert_to_html(content)
                        result_buffer = io.BytesIO(html_content.encode('utf-8'))
                        filename = f"{base_name}_{timestamp}.html"
                        mime = "text/html"
                    
                    os.unlink(tmp_path)
                    save_conversion_history(st.session_state.username, uploaded_file.name, output_format, len(uploaded_file.getvalue()), processing_time, content["pages"])
                    notification_system.add(f"Converted {uploaded_file.name} to {output_format}", "success", duration=3)
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Pages", content['pages'])
                    with col2:
                        st.metric("Tables", len(content['tables']))
                    with col3:
                        total_words = sum(t.get("word_count", 0) for t in content["text"])
                        st.metric("Words", total_words)
                    
                    result_buffer.seek(0)
                    st.download_button(label=f"💾 Download {filename}", data=result_buffer.getvalue(), file_name=filename, mime=mime, use_container_width=True)
                    st.balloons()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

elif page == "📦 Batch Convert":
    st.markdown('<div class="card"><strong>Batch Processing</strong><br>Convert multiple PDF files at once.</div>', unsafe_allow_html=True)
    
    uploaded_files = st.file_uploader(f"Upload PDF files (Max {MAX_BATCH_SIZE} files)", type=['pdf'], accept_multiple_files=True, key="batch_upload")
    
    if uploaded_files and len(uploaded_files) <= MAX_BATCH_SIZE:
        st.info(f"📁 {len(uploaded_files)} files selected")
        
        col1, col2 = st.columns(2)
        with col1:
            output_format = st.selectbox("Output Format", ["Excel (XLSX)", "Word (DOCX)", "Text (TXT)", "CSV", "JSON", "Markdown", "HTML"], key="batch_format")
        with col2:
            extraction_mode = st.selectbox("Extraction Mode", ["Smart (Text + Tables)", "Text Only", "Tables Only"], key="batch_mode")
        
        include_metadata = st.checkbox("Include metadata", value=True)
        extract_tables = st.checkbox("Extract tables", value=True)
        
        if st.button("🚀 Start Batch Conversion", use_container_width=True):
            batch_id = batch_processor.create_batch_job(uploaded_files, output_format, extraction_mode, {"include_metadata": include_metadata, "extract_tables": extract_tables})
            
            progress_bar = st.progress(0)
            def update_progress(progress):
                progress_bar.progress(int(progress))
            
            batch_processor.process_batch(batch_id, update_progress)
            progress_bar.empty()
            batch_processor.render_batch_status(batch_id)
    
    if st.session_state.active_batch and st.session_state.active_batch in st.session_state.batch_jobs:
        st.markdown("---")
        batch_processor.render_batch_status(st.session_state.active_batch)

elif page == "🔍 OCR Scanner":
    if OCR_AVAILABLE:
        ocr_processor.render_ocr_interface()
    else:
        st.error("OCR not available. Install pytesseract and pdf2image")

elif page == "🔧 PDF Tools":
    st.markdown('<div class="card"><strong>PDF Tools</strong><br>Merge, split, or rotate PDF documents.</div>', unsafe_allow_html=True)
    
    tool_tab1, tool_tab2, tool_tab3 = st.tabs(["Merge PDFs", "Split PDF", "Rotate PDF"])
    
    with tool_tab1:
        files = st.file_uploader("Upload PDFs to merge (2+)", type=['pdf'], accept_multiple_files=True, key="merge")
        if files and len(files) > 1 and st.button("Merge PDFs"):
            merged = merge_pdfs(files)
            st.download_button("Download Merged PDF", merged.getvalue(), f"merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf", "application/pdf")
    
    with tool_tab2:
        file = st.file_uploader("Upload PDF to split", type=['pdf'], key="split")
        if file:
            pages = st.number_input("Pages per split", min_value=1, value=1)
            if st.button("Split PDF"):
                splits = split_pdf(file.getvalue(), pages)
                if len(splits) == 1:
                    st.download_button("Download Split", splits[0].getvalue(), "split.pdf", "application/pdf")
                else:
                    zip_buf = io.BytesIO()
                    with zipfile.ZipFile(zip_buf, 'w') as zf:
                        for i, s in enumerate(splits, 1):
                            zf.writestr(f"part_{i:03d}.pdf", s.getvalue())
                    zip_buf.seek(0)
                    st.download_button(f"Download {len(splits)} Files (ZIP)", zip_buf.getvalue(), "splits.zip", "application/zip")
    
    with tool_tab3:
        file = st.file_uploader("Upload PDF to rotate", type=['pdf'], key="rotate")
        rotation = st.selectbox("Rotation", [90, 180, 270])
        if file and st.button("Rotate PDF"):
            rotated = rotate_pdf(file.getvalue(), rotation)
            st.download_button("Download Rotated PDF", rotated.getvalue(), f"rotated_{rotation}.pdf", "application/pdf")

elif page == "📊 History":
    st.markdown('<div class="card"><strong>Conversion History</strong><br>View your recent document conversions.</div>', unsafe_allow_html=True)
    
    history = get_user_history(st.session_state.username)
    if history:
        df = pd.DataFrame(history, columns=['ID', 'Username', 'Filename', 'Format', 'Timestamp', 'Size', 'Time', 'Pages', 'Batch', 'Status', 'Error'])
        display_df = df[['Filename', 'Format', 'Timestamp', 'Pages', 'Status']].copy()
        display_df['Size'] = df['Size'].apply(lambda x: f"{x/1024:.2f} KB" if x else "N/A")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Conversions", len(df))
        with col2:
            st.metric("Formats Used", len(df['Format'].unique()))
        with col3:
            avg_pages = df['Pages'].mean() if df['Pages'].notna().any() else 0
            st.metric("Avg Pages", f"{avg_pages:.0f}")
        
        st.dataframe(display_df, use_container_width=True)
        
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        st.download_button("📥 Download History (CSV)", csv_buffer.getvalue(), f"history_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")
    else:
        st.info("No conversion history yet.")

elif page == "🔔 Notifications":
    st.markdown('<div class="card"><strong>Notification Center</strong><br>View all your notifications and alerts.</div>', unsafe_allow_html=True)
    notification_system.render_notification_center()

elif page == "⚙️ Settings":
    st.markdown('<div class="card"><strong>Settings</strong><br>Configure your preferences.</div>', unsafe_allow_html=True)
    
    user_prefs = get_user_preferences(st.session_state.username)
    
    st.markdown(f"**Username:** {st.session_state.username}")
    st.markdown(f"**Session ID:** {st.session_state.session_id}")
    st.markdown(f"**Version:** {APP_VERSION}")
    st.markdown("---")
    
    default_format = st.selectbox("Default Output Format", ["Excel (XLSX)", "Word (DOCX)", "Text (TXT)", "CSV", "JSON", "Markdown", "HTML"], index=["Excel (XLSX)", "Word (DOCX)", "Text (TXT)", "CSV", "JSON", "Markdown", "HTML"].index(user_prefs["default_output_format"]))
    default_mode = st.selectbox("Default Extraction Mode", ["Smart (Text + Tables)", "Text Only", "Tables Only"], index=["Smart (Text + Tables)", "Text Only", "Tables Only"].index(user_prefs["default_extraction_mode"]))
    auto_convert = st.checkbox("Auto-convert on upload", value=user_prefs["auto_convert"])
    notify_completion = st.checkbox("Notify on conversion completion", value=user_prefs["notify_on_completion"])
    
    if st.button("💾 Save Preferences", use_container_width=True):
        save_user_preferences(st.session_state.username, {
            "default_output_format": default_format,
            "default_extraction_mode": default_mode,
            "auto_convert": auto_convert,
            "notify_on_completion": notify_completion,
            "theme": st.session_state.theme
        })
        st.success("Preferences saved!")

# Footer
st.markdown("---")
st.markdown(f"<div style='text-align:center; color:gray; padding:20px;'>⚡ {APP_NAME} v{APP_VERSION} • {datetime.now().strftime('%Y-%m-%d %H:%M')} • User: {st.session_state.username}</div>", unsafe_allow_html=True)
