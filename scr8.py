"""
app.py
Final Streamlit app:
- Supports URLs from YouTube, Facebook, Instagram, TikTok, Google Drive (public), direct audio/video links
- Supports file upload
- Downloads audio server-side using yt-dlp (best-effort)
- Uploads audio to AssemblyAI and polls for transcript
- Saves transcripts to transcripts/
- Provides TXT + PDF downloads
- Bilingual UI (Arabic / English)
- 30-second cooldown between requests
- Language detection on resulting transcript (langdetect)
"""

import os
import time
import json
import tempfile
import shutil
import requests
import streamlit as st
from datetime import datetime
from io import BytesIO
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from langdetect import detect_langs, DetectorFactory

# make language detection deterministic
DetectorFactory.seed = 0

# ---------------------------
# Load config / env
# ---------------------------
load_dotenv()
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")

if not ASSEMBLYAI_API_KEY:
    st.error("⚠️ ASSEMBLYAI_API_KEY not found in environment. Put it in .env or env vars.")
    st.stop()

HEADERS = {"authorization": ASSEMBLYAI_API_KEY}

# ---------------------------
# Streamlit page config
# ---------------------------
st.set_page_config(page_title="🎧 Universal Transcriber (AssemblyAI)", page_icon="🎙️", layout="centered")

# Languages UI content
LANGS = {
    "ar": {
        "title": "🎧 تحويل من رابط/ملف إلى نص (AssemblyAI)",
        "desc": "ألصق رابطاً (YouTube/Facebook/Instagram/TikTok/Google Drive أو رابط صوت مباشر) أو ارفع ملفًا، ثم اضغط ابدأ.",
        "url_label": "أدخل رابط الفيديو/الصوت:",
        "upload_label": "أو ارفع ملف صوتي/فيديو (mp3/mp4/wav/m4a):",
        "start_btn": "🚀 ابدأ التفريغ",
        "waiting": "⏳ جاري التفريغ — الرجاء الانتظار ...",
        "cooldown": "⚠️ انتظر 30 ثانية قبل طلب جديد.",
        "no_input": "⚠️ الرجاء إدخال رابط أو رفع ملف أولاً.",
        "success": "✅ تم التفريغ بنجاح!",
        "error": "❌ حدث خطأ أثناء التفريغ.",
        "download_txt": "⬇️ تحميل TXT",
        "download_pdf": "⬇️ تحميل PDF",
        "saved": "📁 حفظ النسخة في مجلد transcripts/",
        "youtube_warn": "ملاحظة: بعض روابط YouTube/منصات قد تتطلب مصادقة (cookies). جرب رفع الملف إن فشل الرابط.",
        "lang_detected": "لغة النص المحتملة:",
    },
    "en": {
        "title": "🎧 URL/File → Text (AssemblyAI)",
        "desc": "Paste a URL (YouTube/Facebook/Instagram/TikTok/Google Drive or direct audio) or upload a file, then click Start.",
        "url_label": "Enter video/audio URL:",
        "upload_label": "Or upload an audio/video file (mp3/mp4/wav/m4a):",
        "start_btn": "🚀 Start Transcription",
        "waiting": "⏳ Transcribing — please wait ...",
        "cooldown": "⚠️ Please wait 30 seconds before making another request.",
        "no_input": "⚠️ Please enter a URL or upload a file first.",
        "success": "✅ Transcription completed!",
        "error": "❌ An error occurred during transcription.",
        "download_txt": "⬇️ Download TXT",
        "download_pdf": "⬇️ Download PDF",
        "saved": "📁 Saved transcript to transcripts/ folder",
        "youtube_warn": "Note: some YouTube/platform links require authentication (cookies). Upload the file if URL fails.",
        "lang_detected": "Detected language probabilities:",
    }
}

# session language default
if "ui_lang" not in st.session_state:
    st.session_state.ui_lang = "ar"
ui_lang = st.session_state.ui_lang
t = LANGS[ui_lang]

# language toggle
col1, col2 = st.columns([9, 1])
with col2:
    if st.button("English" if ui_lang == "ar" else "العربية"):
        st.session_state.ui_lang = "en" if ui_lang == "ar" else "ar"
        st.experimental_rerun()

st.title(t["title"])
st.caption(t["desc"])
st.markdown("---")

# Inputs
video_url = st.text_input(t["url_label"])
uploaded_file = st.file_uploader(t["upload_label"], type=["mp3", "mp4", "wav", "m4a"])

# cooldown logic
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = 0

def can_request():
    now = time.time()
    if now - st.session_state.last_request_time < 30:
        return False
    st.session_state.last_request_time = now
    return True

# helper: create pdf bytes
def create_pdf_bytes(text):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica", 11)
    margin = 50
    y = height - margin
    for paragraph in text.splitlines():
        if paragraph.strip() == "":
            y -= 10
            continue
        # naive wrap for long lines
        while len(paragraph) > 120:
            line = paragraph[:120]
            c.drawString(margin, y, line)
            paragraph = paragraph[120:]
            y -= 14
            if y < margin:
                c.showPage()
                c.setFont("Helvetica", 11)
                y = height - margin
        c.drawString(margin, y, paragraph)
        y -= 14
        if y < margin:
            c.showPage()
            c.setFont("Helvetica", 11)
            y = height - margin
    c.save()
    buffer.seek(0)
    return buffer

# helpers: AssemblyAI endpoints (no external SDK required)
def upload_file_to_assemblyai(filepath):
    url = "https://api.assemblyai.com/v2/upload"
    with open(filepath, "rb") as f:
        r = requests.post(url, headers=HEADERS, data=f)
    r.raise_for_status()
    return r.json()["upload_url"]

def create_transcript_from_audio_url(audio_url, language_code=None):
    url = "https://api.assemblyai.com/v2/transcript"
    payload = {"audio_url": audio_url}
    if language_code:
        payload["language_code"] = language_code
    r = requests.post(url, headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()

def poll_transcript(transcript_id, poll_interval=3, timeout=60*10):
    url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
    start = time.time()
    while True:
        r = requests.get(url, headers=HEADERS)
        r.raise_for_status()
        d = r.json()
        status = d.get("status")
        if status == "completed":
            return d
        if status == "error":
            raise RuntimeError("AssemblyAI error: " + str(d.get("error")))
        if time.time() - start > timeout:
            raise RuntimeError("Timeout waiting for transcription completion.")
        time.sleep(poll_interval)

# create transcripts directory
os.makedirs("transcripts", exist_ok=True)

# function: download audio via yt-dlp to a temp file
def download_audio_with_ytdlp(url):
    """
    Attempts to download best audio using yt-dlp into a temp file.
    Returns local file path.
    Raises Exception on failure.
    """
    import yt_dlp
    tmpdir = tempfile.mkdtemp(prefix="yt_")
    outtmpl = os.path.join(tmpdir, "audio.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        # cookiefile optional: server admin may place cookies.txt in app dir and set USE_COOKIES=True
    }
    # if cookies file present and env says use it, include
    cookies_path = "cookies.txt"
    if os.path.exists(cookies_path) and os.getenv("USE_SERVER_COOKIES", "false").lower() in ("1", "true", "yes"):
        ydl_opts["cookiefile"] = cookies_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # find downloaded file path
            # yt-dlp's prepare_filename uses ext; attempt to detect the file
            for fname in os.listdir(tmpdir):
                full = os.path.join(tmpdir, fname)
                if os.path.isfile(full):
                    return full, tmpdir
            raise RuntimeError("No audio file produced by yt-dlp.")
    except Exception as e:
        # cleanup tmpdir
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass
        raise

# Main button
if st.button(t["start_btn"]):
    # Basic input validation
    if not video_url and not uploaded_file:
        st.error(t["no_input"])
        st.stop()
    if not can_request():
        st.warning(t["cooldown"])
        st.stop()

    temp_local_path = None
    tmpdir_for_cleanup = None

    try:
        with st.spinner(t["waiting"]):
            audio_upload_url = None

            # 1) If user uploaded file -> save locally and upload to AssemblyAI
            if uploaded_file:
                # save temp file
                suffix = os.path.splitext(uploaded_file.name)[1] or ".mp3"
                temp_local = f"uploaded_{int(time.time())}{suffix}"
                with open(temp_local, "wb") as f:
                    f.write(uploaded_file.read())
                temp_local_path = temp_local

                # upload to AssemblyAI
                audio_upload_url = upload_file_to_assemblyai(temp_local_path)

            else:
                # 2) User provided URL -> try to download via yt-dlp first (best coverage)
                # If download fails, fallback: try to ask AssemblyAI to fetch URL directly.
                try:
                    local_file, tmpdir_for_cleanup = download_audio_with_ytdlp(video_url)
                    temp_local_path = local_file
                    # quick sanity: ensure file size not tiny and not HTML disguised
                    size = os.path.getsize(local_file)
                    if size < 2000:
                        # too small -> probably HTML or error page
                        raise RuntimeError("Downloaded file too small; likely HTML or error page.")
                    # upload local file to AssemblyAI
                    audio_upload_url = upload_file_to_assemblyai(local_file)

                except Exception as dl_err:
                    # fallback: try AssemblyAI direct URL transcription
                    st.warning("⚠️ yt-dlp failed to download audio; attempting URL-based transcription. " +
                               ("(If this fails, please upload the file or enable server cookies.)" if ui_lang == "en" else "(إذا فشل هذا، ارفع الملف أو فعّل ملفات الكوكيز على الخادم)."))
                    # try to create transcript with the provided URL directly
                    try:
                        resp = create_transcript_from_audio_url = create_transcript_from_audio_url  # silence linter
                    except Exception:
                        pass
                    # attempt creating transcript directly using audio URL (AssemblyAI will try to fetch it)
                    try:
                        ct = create_transcript_from_audio_url(video_url)
                        transcript_id = ct.get("id")
                        if not transcript_id:
                            raise RuntimeError("AssemblyAI did not return a transcript id for URL-based request.")
                        result = poll_transcript(transcript_id)
                        transcript_text = result.get("text", "")
                        if not transcript_text:
                            raise RuntimeError("Transcript completed but returned empty text.")
                        # success path for URL-based
                        transcript_id = result.get("id")
                        st.success(t["success"])
                        st.text_area("📄", transcript_text, height=350)
                        st.download_button(label=t["download_txt"], data=transcript_text, file_name=f"transcript_{transcript_id}.txt")
                        pdf_bytes = create_pdf_bytes(transcript_text)
                        st.download_button(label=t["download_pdf"], data=pdf_bytes, file_name=f"transcript_{transcript_id}.pdf", mime="application/pdf")
                        # save to disk
                        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
                        fname = f"transcripts/transcript_{transcript_id}_{ts}.txt"
                        with open(fname, "w", encoding="utf-8") as f:
                            f.write(transcript_text)
                        st.info(t["saved"])
                        # detect language
                        try:
                            langs = detect_langs(transcript_text)
                            st.write(t["lang_detected"], ", ".join([str(l) for l in langs[:3]]))
                        except Exception:
                            pass
                        raise SystemExit  # jump to finally (cleanup) by exiting normal flow
                    except SystemExit:
                        pass
                    except Exception as url_err:
                        # both download and direct URL approach failed -> show helpful message
                        raise RuntimeError(f"Download error: {dl_err}\n\nURL-based attempt error: {url_err}")

            # If we have audio_upload_url from uploaded file or from yt-dlp path:
            if audio_upload_url:
                # create transcript
                create_resp = create_transcript_from_audio_url(audio_upload_url)
                transcript_id = create_resp.get("id")
                if not transcript_id:
                    raise RuntimeError("Failed to create transcript job; no id returned.")
                # poll until done
                result = poll_transcript(transcript_id)
                transcript_text = result.get("text", "")
                if not transcript_text:
                    raise RuntimeError("Transcript completed but returned empty text.")

                # display + downloads
                st.success(t["success"])
                st.text_area("📄", transcript_text, height=350)
                st.download_button(label=t["download_txt"], data=transcript_text, file_name=f"transcript_{transcript_id}.txt")
                pdf_bytes = create_pdf_bytes(transcript_text)
                st.download_button(label=t["download_pdf"], data=pdf_bytes, file_name=f"transcript_{transcript_id}.pdf", mime="application/pdf")

                # save to transcripts/
                ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
                fname = f"transcripts/transcript_{transcript_id}_{ts}.txt"
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(transcript_text)
                st.info(t["saved"])

                # detect language
                try:
                    langs = detect_langs(transcript_text)
                    st.write(t["lang_detected"], ", ".join([str(l) for l in langs[:3]]))
                except Exception:
                    pass

    except Exception as e:
        st.error(f"{t['error']}\n\nDetails: {str(e)}")
        # helpful hint for YouTube-like URLs
        if video_url and ("youtube" in video_url or "youtu.be" in video_url):
            st.warning(t["youtube_warn"])
    finally:
        # cleanup temp files
        try:
            if temp_local_path and os.path.exists(temp_local_path):
                os.remove(temp_local_path)
        except Exception:
            pass
        try:
            if tmpdir_for_cleanup and os.path.exists(tmpdir_for_cleanup):
                shutil.rmtree(tmpdir_for_cleanup)
        except Exception:
            pass
