import os
import time
import streamlit as st
import yt_dlp
import requests
import assemblyai as aai
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from langdetect import detect

# =========================
# إعداد البيئة
# =========================
load_dotenv()
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

# =========================
# النصوص متعددة اللغات
# =========================
LANG = {
    "ar": {
        "title": "🎧 تفريغ محتوى الفيديو إلى نص",
        "desc": "ألصق رابط الفيديو من YouTube أو TikTok أو Facebook أو Instagram أو Google Drive أو رابط مباشر، أو ارفع ملفًا من جهازك.",
        "input_label": "🎥 أدخل رابط الفيديو أو الملف الصوتي:",
        "button": "بدء التفريغ",
        "upload_option": "📁 أو ارفع ملف صوتي/فيديو من جهازك:",
        "processing": "⏳ جاري معالجة الرابط، يرجى الانتظار...",
        "success": "✅ تم استخراج النص بنجاح!",
        "download_txt": "⬇️ تحميل النص كملف TXT",
        "download_pdf": "📄 تحميل النص كملف PDF",
        "lang_detected": "🌐 اللغة المكتشفة في النص:",
        "fail": "❌ حدث خطأ أثناء التفريغ.",
        "select_lang": "🌍 اختر لغة الواجهة:",
        "cookies_warn": "⚠️ بعض الروابط (مثل YouTube) تحتاج ملف cookies صالح من المتصفح."
    },
    "en": {
        "title": "🎧 Transcribe Video or Audio to Text",
        "desc": "Paste a video link from YouTube, TikTok, Facebook, Instagram, Google Drive, or upload a file from your device.",
        "input_label": "🎥 Enter video or audio URL:",
        "button": "Start Transcription",
        "upload_option": "📁 Or upload a video/audio file:",
        "processing": "⏳ Processing the link, please wait...",
        "success": "✅ Text extracted successfully!",
        "download_txt": "⬇️ Download TXT file",
        "download_pdf": "📄 Download PDF file",
        "lang_detected": "🌐 Detected language:",
        "fail": "❌ Transcription failed.",
        "select_lang": "🌍 Choose interface language:",
        "cookies_warn": "⚠️ Some links (like YouTube) need valid browser cookies."
    }
}

# =========================
# واجهة Streamlit
# =========================
st.set_page_config(page_title="Video Transcriber", page_icon="🎧", layout="centered")

if "lang" not in st.session_state:
    st.session_state["lang"] = "ar"

lang = st.radio("🌍 Language / اللغة:", ["العربية", "English"])
st.session_state["lang"] = "en" if lang == "English" else "ar"
t = LANG[st.session_state["lang"]]

st.title(t["title"])
st.write(t["desc"])
st.info(t["cookies_warn"])

url = st.text_input(t["input_label"])
uploaded_file = st.file_uploader(t["upload_option"], type=["mp3", "mp4", "wav", "m4a"])

# =========================
# تحميل الصوت من الرابط
# =========================
def download_audio_from_url(video_url):
    output_file = "audio_temp.mp3"
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_file,
        'quiet': True,
        'noplaylist': True,
        # ملف الكوكيز المستخدم لتجاوز حواجز يوتيوب وفيسبوك
        'cookiefile': 'com_cookies.txt',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        return output_file
    except Exception as e:
        print(f"Download error: {e}")
        return None

# =========================
# حفظ النص إلى PDF
# =========================
def save_to_pdf(text, filename="transcript.pdf"):
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont("Helvetica", 11)
    for line in text.split('\n'):
        if y < 50:
            c.showPage()
            y = height - 50
        c.drawString(50, y, line)
        y -= 15
    c.save()
    return filename

# =========================
# زر التنفيذ
# =========================
if st.button(t["button"]):
    if not url and not uploaded_file:
        st.warning("⚠️ الرجاء إدخال رابط أو رفع ملف.")
    else:
        with st.spinner(t["processing"]):
            audio_path = None

            if uploaded_file:
                audio_path = f"temp_{uploaded_file.name}"
                with open(audio_path, "wb") as f:
                    f.write(uploaded_file.read())
            elif url:
                audio_path = download_audio_from_url(url)

            if audio_path and os.path.exists(audio_path):
                try:
                    transcriber = aai.Transcriber()
                    transcript = transcriber.transcribe(audio_path)

                    if transcript.status == aai.TranscriptStatus.error:
                        st.error(f"{t['fail']} ({transcript.error})")
                    else:
                        text = transcript.text
                        detected_lang = detect(text)
                        lang_name = "العربية" if detected_lang == "ar" else "English"

                        st.success(t["success"])
                        st.write(f"{t['lang_detected']} **{lang_name}**")
                        st.text_area("📝", text, height=300)

                        txt_file = "transcript.txt"
                        with open(txt_file, "w", encoding="utf-8") as f:
                            f.write(text)
                        pdf_file = save_to_pdf(text)

                        with open(txt_file, "rb") as f:
                            st.download_button(t["download_txt"], f, file_name="transcript.txt")
                        with open(pdf_file, "rb") as f:
                            st.download_button(t["download_pdf"], f, file_name="transcript.pdf")

                except Exception as e:
                    st.error(f"{t['fail']}\n\nDetails: {e}")
            else:
                st.error("❌ فشل تحميل الصوت من الرابط. جرب رفع الملف مباشرة أو استخدم ملف cookies.")
