import streamlit as st
import os
import time
import requests
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")

if not ASSEMBLYAI_API_KEY:
    st.error("⚠️ لم يتم العثور على مفتاح ASSEMBLYAI_API_KEY في ملف .env")
    st.stop()

# إعداد الترجمات
LANGUAGES = {
    "العربية": {
        "title": "🎧 تحويل الفيديو إلى نص",
        "desc": "ألصق رابط الفيديو من YouTube أو رابط ملف صوتي مباشر، واضغط الزر لتحصل على النص.",
        "url_label": "أدخل رابط الفيديو:",
        "process_btn": "ابدأ التفريغ",
        "download_txt": "تحميل النص (TXT)",
        "download_pdf": "تحميل النص (PDF)",
        "waiting": "⏳ جاري استخراج النص...",
        "error": "حدث خطأ أثناء معالجة الفيديو 😞",
        "cooldown": "⏱ يرجى الانتظار 30 ثانية قبل المحاولة مرة أخرى.",
        "success": "✅ تم التفريغ بنجاح!",
        "switch": "English",
    },
    "English": {
        "title": "🎧 Video to Text Transcription",
        "desc": "Paste a YouTube video link or direct audio URL, then click to get the text.",
        "url_label": "Enter video URL:",
        "process_btn": "Transcribe",
        "download_txt": "Download TXT",
        "download_pdf": "Download PDF",
        "waiting": "⏳ Please wait while processing...",
        "error": "An error occurred during processing 😞",
        "cooldown": "⏱ Please wait 30 seconds before retrying.",
        "success": "✅ Transcription completed successfully!",
        "switch": "العربية",
    }
}

# إعداد الصفحة
st.set_page_config(page_title="Video Transcriber", page_icon="🎧", layout="centered")

# مؤقت التبريد
if "last_request" not in st.session_state:
    st.session_state["last_request"] = 0

# اللغة المختارة
if "language" not in st.session_state:
    st.session_state["language"] = "ar"
lang = st.session_state["language"]
t = LANGUAGES[lang]

# زر تبديل اللغة
col1, col2 = st.columns([8, 1])
with col2:
    if st.button(t["switch"]):
        st.session_state["language"] = "en" if lang == "ar" else "ar"
        st.rerun()

st.title(t["title"])
st.markdown(t["desc"])
video_url = st.text_input(t["url_label"], "")

# دالة إنشاء PDF
def create_pdf(text: str) -> BytesIO:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    pdf.setFont("Helvetica", 12)
    y_position = height - 50
    for line in text.splitlines():
        if y_position < 50:
            pdf.showPage()
            pdf.setFont("Helvetica", 12)
            y_position = height - 50
        pdf.drawString(50, y_position, line)
        y_position -= 18
    pdf.save()
    buffer.seek(0)
    return buffer

# تنفيذ التفريغ
if st.button(t["process_btn"]):
    elapsed = time.time() - st.session_state["last_request"]
    if elapsed < 30:
        st.warning(t["cooldown"])
    elif not video_url.strip():
        st.error("⚠️ يرجى إدخال رابط فيديو صالح.")
    else:
        st.session_state["last_request"] = time.time()
        with st.spinner(t["waiting"]):
            try:
                # إرسال الرابط مباشرة إلى AssemblyAI
                headers = {"authorization": ASSEMBLYAI_API_KEY, "content-type": "application/json"}
                payload = {"audio_url": video_url}
                response = requests.post("https://api.assemblyai.com/v2/transcript", json=payload, headers=headers)
                response.raise_for_status()
                transcript_id = response.json()['id']

                # متابعة حالة التفريغ
                while True:
                    poll = requests.get(f"https://api.assemblyai.com/v2/transcript/{transcript_id}", headers=headers)
                    status = poll.json()['status']
                    if status == "completed":
                        text = poll.json().get("text", "")
                        st.success(t["success"])
                        st.text_area("📄 النص المستخرج:", text, height=300)
                        st.download_button(t["download_txt"], text, "transcript.txt")
                        pdf_data = create_pdf(text)
                        st.download_button(t["download_pdf"], pdf_data, "transcript.pdf", mime="application/pdf")
                        break
                    elif status == "error":
                        st.error(f"{t['error']}\n\n🔍 التفاصيل: {poll.json().get('error', '')}")
                        break
                    time.sleep(3)

            except Exception as e:
                st.error(f"{t['error']}\n\n🔍 التفاصيل: {e}")
