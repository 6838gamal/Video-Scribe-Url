import streamlit as st
import requests
import os
import time
from dotenv import load_dotenv
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# تحميل متغيرات البيئة
load_dotenv()
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")

# التحقق من وجود المفتاح
if not ASSEMBLYAI_API_KEY:
    st.error("⚠️ لم يتم العثور على مفتاح ASSEMBLYAI_API_KEY في ملف .env")
    st.stop()

# إعداد الترجمات
LANGUAGES = {
    "العربية": {
        "title": "🎧 تحويل الفيديو إلى نص",
        "url_label": "ألصق رابط الفيديو من YouTube:",
        "start_btn": "ابدأ التفريغ",
        "processing": "⏳ جاري استخراج النص...",
        "done": "✅ تم استخراج النص بنجاح!",
        "download_txt": "تحميل النص (TXT)",
        "download_pdf": "تحميل النص (PDF)",
        "error": "حدث خطأ أثناء معالجة الفيديو.",
        "cooldown": "⏱ يرجى الانتظار 30 ثانية قبل المحاولة مرة أخرى.",
        "empty_url": "⚠️ الرجاء إدخال رابط فيديو صالح.",
    },
    "English": {
        "title": "🎧 Video to Text Transcription",
        "url_label": "Paste YouTube video URL:",
        "start_btn": "Start Transcription",
        "processing": "⏳ Processing transcription...",
        "done": "✅ Transcription completed successfully!",
        "download_txt": "Download Text (TXT)",
        "download_pdf": "Download Text (PDF)",
        "error": "An error occurred while processing the video.",
        "cooldown": "⏱ Please wait 30 seconds before trying again.",
        "empty_url": "⚠️ Please enter a valid video URL.",
    },
}

# إعداد الصفحة
st.set_page_config(page_title="Video Transcriber", page_icon="🎧", layout="centered")

# اختيار اللغة
lang = st.sidebar.selectbox("🌐 Language / اللغة", list(LANGUAGES.keys()))
L = LANGUAGES[lang]

# مؤقت التبريد
if "last_request" not in st.session_state:
    st.session_state.last_request = 0

# واجهة المستخدم
st.markdown(
    """
    <style>
    .main {background-color: #f9fafc; color: #111;}
    .stTextInput>div>div>input {border-radius: 10px;}
    .stButton>button {
        background-color: #3b82f6;
        color: white;
        font-weight: 600;
        border-radius: 10px;
        padding: 0.5rem 1.5rem;
    }
    .stButton>button:hover {
        background-color: #2563eb;
    }
    textarea {font-size: 16px;}
    </style>
    """,
    unsafe_allow_html=True
)

st.title(L["title"])
video_url = st.text_input(L["url_label"], placeholder="https://www.youtube.com/watch?v=...")

# دالة لإنشاء PDF
def create_pdf(text: str) -> BytesIO:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    pdf.setFont("Helvetica", 12)
    y_position = height - 60
    for line in text.splitlines():
        if y_position < 60:
            pdf.showPage()
            pdf.setFont("Helvetica", 12)
            y_position = height - 60
        pdf.drawString(50, y_position, line)
        y_position -= 18
    pdf.save()
    buffer.seek(0)
    return buffer

# تنفيذ العملية
if st.button(L["start_btn"]):
    elapsed = time.time() - st.session_state.last_request
    if elapsed < 30:
        st.warning(L["cooldown"])
    else:
        if not video_url.strip():
            st.error(L["empty_url"])
        else:
            st.session_state.last_request = time.time()
            with st.spinner(L["processing"]):
                try:
                    headers = {"authorization": ASSEMBLYAI_API_KEY}
                    payload = {"audio_url": video_url}

                    transcript_request = requests.post(
                        "https://api.assemblyai.com/v2/transcript",
                        json=payload,
                        headers=headers
                    )

                    if transcript_request.status_code == 200:
                        transcript_id = transcript_request.json()["id"]

                        # التحقق من الحالة
                        while True:
                            status_check = requests.get(
                                f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
                                headers=headers
                            )
                            status_data = status_check.json()
                            status = status_data.get("status")

                            if status == "completed":
                                text = status_data.get("text", "")
                                st.success(L["done"])
                                st.text_area("📝 النص المستخرج:", text, height=350)

                                # أزرار التحميل
                                st.download_button(
                                    L["download_txt"], 
                                    data=text, 
                                    file_name="transcript.txt"
                                )

                                pdf_data = create_pdf(text)
                                st.download_button(
                                    L["download_pdf"],
                                    data=pdf_data,
                                    file_name="transcript.pdf",
                                    mime="application/pdf"
                                )
                                break
                            elif status == "error":
                                st.error(L["error"])
                                break
                            time.sleep(5)
                    else:
                        st.error(L["error"])

                except Exception as e:
                    st.error(f"{L['error']}\n\nالتفاصيل: {e}")
