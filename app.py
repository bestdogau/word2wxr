"""
Word to WordPress XML Converter — Web App
Powered by Streamlit + DeepSeek AI
"""

import streamlit as st
import tempfile
import os
import io
import time
import zipfile
from datetime import datetime

from docx_parser import parse_docx
from reference_analyzer import build_style_guide, get_structure_rules, extract_style_guide
from ai_converter import convert_with_ai, DEFAULT_MODEL
from wxr_generator import WXRGenerator


# --- Page Config ---
st.set_page_config(
    page_title="Word → WordPress Converter",
    page_icon="📝",
    layout="wide"
)

# --- Password Protection ---
# To enable: add password = "your-password" in Streamlit Cloud Secrets
def check_password():
    """Returns True if password is correct or not set."""
    try:
        if "password" not in st.secrets:
            return True
    except Exception:
        # No secrets file at all (local dev) — allow access
        return True
    
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if st.session_state.authenticated:
        return True
    
    pwd = st.text_input("Enter password to access this app:", type="password")
    if pwd:
        if pwd == st.secrets["password"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")
    return False

if not check_password():
    st.stop()

# --- Custom CSS ---
st.markdown("""
<style>
    .stApp { max-width: 1000px; margin: 0 auto; }
    .success-box { padding: 1rem; background: #d4edda; border-radius: 8px; border-left: 4px solid #28a745; margin: 1rem 0; }
    .info-box { padding: 1rem; background: #fff3cd; border-radius: 8px; border-left: 4px solid #f9c030; margin: 1rem 0; }
    .error-box { padding: 1rem; background: #f8d7da; border-radius: 8px; border-left: 4px solid #dc3545; margin: 1rem 0; }
    .cost-badge { display: inline-block; background: #e8f5e9; color: #2e7d32; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; }
</style>
""", unsafe_allow_html=True)

# --- Header ---
st.title("📝 Word → WordPress XML Converter")
st.caption("AI-powered conversion using DeepSeek V3.2 via OpenRouter")

# --- Sidebar: Settings ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    api_key = st.text_input(
        "OpenRouter API Key",
        type="password",
        placeholder="sk-or-v1-...",
        help="Get your key at openrouter.ai/keys"
    )
    
    model = st.selectbox(
        "AI Model",
        options=[
            "deepseek/deepseek-v3.2",
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
            "anthropic/claude-sonnet-4",
        ],
        index=0,
        help="DeepSeek is cheapest (~$0.01/post). GPT-4o Mini is faster (~$0.03/post)."
    )
    
    output_mode = st.selectbox(
        "Output Mode",
        options=["Single combined XML", "Separate XML per file"],
        index=0,
        help="Combined is best for bulk import",
        key="output_mode_select",
    )
    
    st.divider()
    st.markdown("**Cost Estimates**")
    st.markdown("""
    - DeepSeek V3.2: ~$0.01/post
    - GPT-4o Mini: ~$0.03/post
    - GPT-4o: ~$0.12/post
    - Claude Sonnet: ~$0.15/post
    """)
    
    st.divider()
    st.markdown("**How to get API key:**")
    st.markdown("1. Go to [openrouter.ai](https://openrouter.ai)")
    st.markdown("2. Sign up → Keys → Create Key")
    st.markdown("3. Add $5 credit (lasts ~500 posts)")

# --- Main Area ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Reference XML")
    ref_file = st.file_uploader(
        "Upload your WordPress export XML",
        type=["xml"],
        help="Export from WordPress Dashboard → Tools → Export"
    )
    if ref_file:
        st.success(f"✓ {ref_file.name}")

with col2:
    st.subheader("2. Word Documents")
    docx_files = st.file_uploader(
        "Upload .docx files to convert",
        type=["docx"],
        accept_multiple_files=True,
        help="Drop up to 30 files at once"
    )
    if docx_files:
        st.success(f"✓ {len(docx_files)} file(s) uploaded")

# --- Convert Button ---
st.divider()

can_convert = api_key and ref_file and docx_files
if not can_convert:
    missing = []
    if not api_key: missing.append("API key")
    if not ref_file: missing.append("reference XML")
    if not docx_files: missing.append("Word documents")
    st.info(f"Upload {', '.join(missing)} to start converting")

if st.button("🚀 Convert to WordPress XML", disabled=not can_convert, type="primary", use_container_width=True):
    
    # Clear any previous results when starting a new conversion
    st.session_state.pop("conversion_results", None)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Save reference XML
        ref_path = os.path.join(tmpdir, ref_file.name)
        with open(ref_path, 'wb') as f:
            f.write(ref_file.getvalue())
        
        # Analyze reference
        progress = st.progress(0, text="Analyzing reference XML...")
        
        try:
            style_guide = build_style_guide(ref_path)
            structure_rules = get_structure_rules()
            generator = WXRGenerator(ref_path)
        except Exception as e:
            st.error(f"Failed to parse reference XML: {e}")
            st.stop()
        
        st.markdown(f"""
        <div class="info-box">
            <strong>Site:</strong> {generator.site_url}<br>
            <strong>Author:</strong> {generator.default_creator}<br>
            <strong>Model:</strong> {model}<br>
            <strong>Files:</strong> {len(docx_files)}
        </div>
        """, unsafe_allow_html=True)
        
        # Process each file
        items = []
        results_xml = {}   # {filename: wxr_string}
        file_logs = []     # [(name, success_bool, error_or_none)]
        
        for idx, docx_file in enumerate(docx_files):
            file_num = idx + 1
            progress_pct = file_num / len(docx_files)
            progress.progress(progress_pct, text=f"Converting {file_num}/{len(docx_files)}: {docx_file.name}")
            
            # Save docx to temp
            docx_path = os.path.join(tmpdir, docx_file.name)
            with open(docx_path, 'wb') as f:
                f.write(docx_file.getvalue())
            
            with st.expander(f"📄 {docx_file.name}", expanded=(idx == 0)):
                try:
                    # Parse
                    parsed = parse_docx(docx_path)
                    if not parsed['title']:
                        basename = os.path.splitext(docx_file.name)[0]
                        parsed['title'] = basename.replace('-', ' ').replace('_', ' ').title()
                    
                    st.write(f"**Title:** {parsed['title']}")
                    meta = parsed.get('meta', {})
                    if meta.get('seo_title'):
                        st.write(f"**SEO:** {meta['seo_title'][:60]}")
                    if meta.get('focus_keyword'):
                        st.write(f"**Keyword:** {meta['focus_keyword']}")
                    
                    # Convert with AI
                    start_time = time.time()
                    st.info("⏳ Calling AI... (30-90 seconds for DeepSeek)")
                    
                    gutenberg_html = convert_with_ai(
                        parsed, style_guide, structure_rules,
                        api_key, model
                    )
                    
                    elapsed = time.time() - start_time
                    
                    if gutenberg_html:
                        item_xml = generator.generate_single(parsed, gutenberg_html)
                        items.append(item_xml)
                        
                        # Store individual WXR for separate-file mode
                        slug = meta.get('slug', parsed['title'].lower().replace(' ', '-')[:50])
                        single_wxr = generator.generate_wxr([item_xml])
                        results_xml[f"{slug}_import.xml"] = single_wxr
                        
                        st.success(f"✓ Converted in {elapsed:.0f}s — {len(gutenberg_html):,} chars")
                        file_logs.append((docx_file.name, True, None))
                    else:
                        st.error("✗ AI conversion failed")
                        file_logs.append((docx_file.name, False, "AI returned empty"))
                        
                except Exception as e:
                    st.error(f"✗ Error: {e}")
                    file_logs.append((docx_file.name, False, str(e)))
            
            # Small delay between API calls
            if idx < len(docx_files) - 1:
                time.sleep(1)
        
        progress.progress(1.0, text="Done!")
        
        # ── Save results to session_state so downloads survive reruns ──
        if items:
            combined_wxr = generator.generate_wxr(items)
            st.session_state["conversion_results"] = {
                "combined_wxr": combined_wxr,
                "separate_files": results_xml,
                "success_count": len(items),
                "total_count": len(docx_files),
                "file_logs": file_logs,
            }
            # Force rerun so the download section below renders cleanly
            st.rerun()
        else:
            st.error("No files were converted successfully.")


# ══════════════════════════════════════════════════════════════════════════════
# PERSISTENT DOWNLOAD SECTION — renders from session_state, survives reruns
# ══════════════════════════════════════════════════════════════════════════════
if "conversion_results" in st.session_state:
    res = st.session_state["conversion_results"]
    
    st.divider()
    
    # ── Summary ──
    st.markdown(f"""
    <div class="success-box">
        <strong>✅ Conversion Complete!</strong><br>
        {res['success_count']}/{res['total_count']} files converted successfully
    </div>
    """, unsafe_allow_html=True)
    
    # Show errors if any
    errors = [log for log in res["file_logs"] if not log[1]]
    if errors:
        with st.expander(f"⚠️ {len(errors)} file(s) had errors", expanded=False):
            for fname, _, err in errors:
                st.error(f"**{fname}**: {err}")
    
    # ── Download Buttons ──
    st.subheader("📥 Download Your Files")
    
    current_mode = st.session_state.get("output_mode_select", "Single combined XML")
    
    if current_mode == "Single combined XML" or res["success_count"] == 1:
        # --- Single combined XML download ---
        combined = res["combined_wxr"]
        file_size = len(combined.encode("utf-8"))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        st.download_button(
            label=f"⬇️  Download Combined XML  —  {res['success_count']} post(s), {file_size:,} bytes",
            data=combined.encode("utf-8"),
            file_name=f"wordpress_import_{timestamp}.xml",
            mime="application/xml",
            use_container_width=True,
            type="primary",
            key="download_combined",
        )
    else:
        # --- Separate files: ZIP + individual downloads ---
        separate = res["separate_files"]
        
        # Build ZIP in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname, wxr_content in separate.items():
                zf.writestr(fname, wxr_content)
        zip_buffer.seek(0)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        st.download_button(
            label=f"⬇️  Download All as ZIP  —  {len(separate)} file(s)",
            data=zip_buffer.getvalue(),
            file_name=f"wordpress_imports_{timestamp}.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary",
            key="download_zip",
        )
        
        # Individual file downloads
        with st.expander("Or download individually", expanded=False):
            for fname, wxr_content in separate.items():
                st.download_button(
                    label=f"⬇️  {fname}",
                    data=wxr_content.encode("utf-8"),
                    file_name=fname,
                    mime="application/xml",
                    key=f"dl_{fname}",
                )
    
    st.caption("**Next step:** WordPress Dashboard → Tools → Import → WordPress Importer → Upload XML")
    
    # Option to clear and start fresh
    if st.button("🔄 Clear results & convert again"):
        st.session_state.pop("conversion_results", None)
        st.rerun()
