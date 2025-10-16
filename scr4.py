import os
import time
import tempfile
import streamlit as st
import requests
import yt_dlp
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# تحميل متغيرات البيئة
load_dotenv()
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")

# إعدادات الواجهة
st.set_page_config(page_title="🎧 تفريغ الفيديو", page_icon="🎙️", layout="centered")

# تهيئة الجلسة
if "last_request_time" not in st.session_state:
    st.session_state["last_request_time"] = 0

if "language" not in st.session_state:
    st.session_state["language"] = "ar"

# ترجمة الواجهة
texts = {
    "ar": {
        "title": "🎧 تفريغ محتوى الفيديو إلى نص",
        "desc": "ألصق رابط الفيديو من YouTube أو رابط ملف صوتي مباشر، واضغط الزر لتحصل على النص.",
        "url_label": "أدخل رابط الفيديو:",
        "process_btn": "بدء التفريغ",
        "download_txt": "تحميل النص (TXT)",
        "download_pdf": "تحميل النص (PDF)",
        "waiting": "⏳ يُرجى الانتظار قليلاً أثناء المعالجة...",
        "error": "حدث خطأ أثناء معالجة الفيديو 😞",
        "success": "✅ تم التفريغ بنجاح!",
        "cooldown": "⚠️ يُرجى الانتظار 30 ثانية قبل المحاولة مجددًا.",
        "switch": "English"
    },
    "en": {
        "title": "🎧 Video to Text Transcriber",
        "desc": "Paste a YouTube video link or direct audio URL, then click to get the text.",
        "url_label": "Enter video URL:",
        "process_btn": "Transcribe",
        "download_txt": "Download TXT",
        "download_pdf": "Download PDF",
        "waiting": "⏳ Please wait while processing...",
        "error": "An error occurred during processing 😞",
        "success": "✅ Transcription completed successfully!",
        "cooldown": "⚠️ Please wait 30 seconds before retrying.",
        "switch": "العربية"
    }
}

# زر التبديل بين اللغتين
col1, col2 = st.columns([8, 1])
with col2:
    if st.button(texts[st.session_state.language]["switch"]):
        st.session_state.language = "en" if st.session_state.language == "ar" else "ar"
        st.rerun()

t = texts[st.session_state.language]

st.title(t["title"])
st.markdown(t["desc"])

video_url = st.text_input(t["url_label"], "")

def download_audio(url):
    """تنزيل الصوت من الفيديو"""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'{tmpdir}/audio.%(ext)s',
                'quiet': True,
                'noplaylist': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                if not os.path.exists(filename):
                    raise Exception("لم يتم العثور على ملف الصوت بعد التحميل.")
                return filename
    except Exception as e:
        raise Exception(f"فشل تحميل الصوت من الفيديو: {e}")

def upload_to_assemblyai(file_path):
    """رفع الملف الصوتي إلى AssemblyAI"""
    headers = {"authorization": ASSEMBLYAI_API_KEY}
    try:
        with open(file_path, 'rb') as f:
            response = requests.post(
                'https://api.assemblyai.com/v2/upload',
                headers=headers,
                data=f
            )
        response.raise_for_status()
        return response.json()['upload_url']
    except Exception as e:
        raise Exception(f"فشل رفع الصوت: {e}")

def transcribe_audio(audio_url):
    """تفريغ النص"""
    headers = {"authorization": ASSEMBLYAI_API_KEY, "content-type": "application/json"}
    json_data = {"audio_url": audio_url}
    try:
        response = requests.post("https://api.assemblyai.com/v2/transcript", json=json_data, headers=headers)
        response.raise_for_status()
        transcript_id = response.json()['id']

        while True:
            poll = requests.get(f"https://api.assemblyai.com/v2/transcript/{transcript_id}", headers=headers)
            status = poll.json()['status']
            if status == 'completed':
                return poll.json()['text']
            elif status == 'error':
                raise Exception(poll.json()['error'])
            time.sleep(3)
    except Exception as e:
        raise Exception(f"فشل في تفريغ النص: {e}")

def save_as_pdf(text):
    """حفظ النص كملف PDF"""
    pdf_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica", 12)
    y = height - 50
    for line in text.split('\n'):
        c.drawString(50, y, line)
        y -= 20
        if y < 50:
            c.showPage()
            y = height - 50
    c.save()
    return pdf_path

if st.button(t["process_btn"]):
    now = time.time()
    if now - st.session_state["last_request_time"] < 30:
        st.warning(t["cooldown"])
    elif not video_url.strip():
        st.error("⚠️ يرجى إدخال رابط فيديو صالح.")
    else:
        st.session_state["last_request_time"] = now
        try:
            with st.spinner(t["waiting"]):
                audio_path = download_audio(video_url)
                upload_url = upload_to_assemblyai(audio_path)
                text = transcribe_audio(upload_url)
                st.success(t["success"])
                st.text_area("📄 النص المستخرج:", text, height=300)

                st.download_button(label=t["download_txt"], data=text, file_name="transcript.txt")
                pdf_path = save_as_pdf(text)
                with open(pdf_path, "rb") as pdf_file:
                    st.download_button(label=t["download_pdf"], data=pdf_file, file_name="transcript.pdf", mime="application/pdf")

        except Exception as e:
            st.error(f"{t['error']} \n\n🔍 التفاصيل: {str(e)}")
