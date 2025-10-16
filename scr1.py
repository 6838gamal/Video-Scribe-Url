import streamlit as st
import requests
from pytube import YouTube
import time
from io import BytesIO
from reportlab.pdfgen import canvas

# إعداد الواجهة
st.set_page_config(page_title="🎬 Video to Text", page_icon="🎧", layout="wide")

# --------- اختيار اللغة ---------
lang_ui = st.sidebar.radio("🌐 Language / اللغة", ["English", "العربية"])

# النصوص حسب اللغة
texts = {
    "English": {
        "title": "🎬 Video to Text Transcriber",
        "desc": "Paste your video link, choose the API service, and extract the transcript instantly.",
        "service": "Select Service",
        "api_key": "Enter API Key",
        "video_url": "Video URL",
        "button": "🚀 Transcribe Now",
        "success": "✅ Transcription completed successfully!",
        "error": "⚠️ An error occurred during processing:",
        "wait": "⏳ Processing, please wait...",
        "download_txt": "⬇️ Download as TXT",
        "download_pdf": "📄 Download as PDF",
        "warning": "⚠️ Please enter both video URL and API key first.",
    },
    "العربية": {
        "title": "🎬 محول الفيديو إلى نصوص",
        "desc": "ألصق رابط الفيديو، اختر الخدمة، واضغط زرًا واحدًا لاستخراج النص فورًا.",
        "service": "اختر الخدمة",
        "api_key": "أدخل مفتاح API",
        "video_url": "رابط الفيديو",
        "button": "🚀 ابدأ استخراج النص",
        "success": "✅ تم استخراج النص بنجاح!",
        "error": "⚠️ حدث خطأ أثناء المعالجة:",
        "wait": "⏳ جاري المعالجة، يرجى الانتظار...",
        "download_txt": "⬇️ تحميل النص كملف TXT",
        "download_pdf": "📄 تحميل النص كملف PDF",
        "warning": "⚠️ الرجاء إدخال رابط الفيديو ومفتاح API أولًا.",
    }
}

t = texts[lang_ui]

# --------- تصميم أنيق ---------
st.markdown("""
<style>
    body, .stApp {
        background-color: #0e1117;
        color: #f1f1f1;
        font-family: 'Cairo', sans-serif;
    }
    h1, h2, h3, label {
        color: #00b4d8 !important;
    }
    textarea {
        background-color: #1a1d23 !important;
        color: #e6e6e6 !important;
        border-radius: 10px;
    }
    div[data-testid="stDownloadButton"] button {
        background-color: #00b4d8 !important;
        color: white !important;
        border-radius: 8px;
        border: none;
    }
    div[data-testid="stDownloadButton"] button:hover {
        background-color: #0096c7 !important;
    }
    .stTextInput>div>div>input {
        background-color: #1a1d23 !important;
        color: #fff !important;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# --------- العناوين ---------
st.title(t["title"])
st.caption(t["desc"])

# --------- المدخلات ---------
col1, col2 = st.columns(2)
with col1:
    service = st.selectbox(t["service"], ["AssemblyAI", "Deepgram"])
with col2:
    api_key = st.text_input(t["api_key"], type="password")

video_url = st.text_input(f"🎥 {t['video_url']}")

# --------- زر التنفيذ ---------
if st.button(t["button"]):
    if not video_url or not api_key:
        st.warning(t["warning"])
    else:
        try:
            st.info("📥 Downloading audio from video...")
            yt = YouTube(video_url)
            stream = yt.streams.filter(only_audio=True).first()
            audio_path = stream.download(filename="audio.mp4")
            st.success("✅ Audio extracted successfully.")

            transcript_text = ""

            if service == "AssemblyAI":
                # رفع الملف
                st.info("📤 Uploading audio to AssemblyAI...")
                upload_url = "https://api.assemblyai.com/v2/upload"
                headers = {"authorization": api_key}
                with open(audio_path, "rb") as f:
                    upload_response = requests.post(upload_url, headers=headers, data=f)
                audio_url = upload_response.json()["upload_url"]

                json_data = {"audio_url": audio_url}
                response = requests.post("https://api.assemblyai.com/v2/transcript", headers=headers, json=json_data)
                transcript_id = response.json()["id"]

                with st.spinner(t["wait"]):
                    while True:
                        status = requests.get(f"https://api.assemblyai.com/v2/transcript/{transcript_id}", headers=headers).json()
                        if status["status"] == "completed":
                            transcript_text = status["text"]
                            break
                        elif status["status"] == "error":
                            st.error("❌ API error during transcription.")
                            break
                        time.sleep(3)

            elif service == "Deepgram":
                st.info("📤 Uploading audio to Deepgram...")
                upload_url = "https://api.deepgram.com/v1/listen"
                headers = {"Authorization": f"Token {api_key}"}
                with open(audio_path, "rb") as f:
                    response = requests.post(upload_url, headers=headers, files={"file": f})
                result = response.json()
                transcript_text = result["results"]["channels"][0]["alternatives"][0]["transcript"]

            # عرض النص النهائي
            if transcript_text:
                st.success(t["success"])
                st.text_area("📝", transcript_text, height=400)

                # تحميل TXT
                txt_bytes = transcript_text.encode("utf-8")
                st.download_button(
                    label=t["download_txt"],
                    data=txt_bytes,
                    file_name="transcript.txt",
                    mime="text/plain"
                )

                # تحميل PDF
                pdf_buffer = BytesIO()
                pdf = canvas.Canvas(pdf_buffer)
                pdf.setFont("Helvetica", 12)
                lines = transcript_text.split("\n")
                y = 800
                for line in lines:
                    if y < 50:
                        pdf.showPage()
                        y = 800
                    pdf.drawString(50, y, line[:90])
                    y -= 20
                pdf.save()
                pdf_buffer.seek(0)
                st.download_button(
                    label=t["download_pdf"],
                    data=pdf_buffer,
                    file_name="transcript.pdf",
                    mime="application/pdf"
                )

        except Exception as e:
            st.error(f"{t['error']} {e}")
