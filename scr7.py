import os
import time
import yt_dlp
import streamlit as st
import assemblyai as aai

# إعداد مفاتيح البيئة
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

# إعداد الواجهة
st.set_page_config(page_title="🎧 تفريغ الفيديو إلى نص", page_icon="🎙️", layout="centered")

# لغات الواجهة
LANG = {
    "ar": {
        "title": "🎧 تفريغ محتوى الفيديو إلى نص",
        "desc": "ألصق رابط الفيديو من YouTube أو ارفع ملفًا صوتيًا، واضغط الزر لتحصل على النص.",
        "video_label": "🎥 أدخل رابط الفيديو:",
        "upload_label": "📁 أو اختر ملفًا صوتيًا/فيديو:",
        "btn": "بدء التفريغ",
        "success": "✅ تم استخراج النص بنجاح!",
        "download": "📄 تحميل النص كملف",
        "wait": "⏳ يرجى الانتظار 30 ثانية قبل إعادة الطلب",
        "error": "حدث خطأ أثناء معالجة الفيديو 😞",
        "lang_switch": "تبديل اللغة إلى English"
    },
    "en": {
        "title": "🎧 Video-to-Text Transcription",
        "desc": "Paste a YouTube video link or upload an audio file, then click the button to get the transcript.",
        "video_label": "🎥 Enter video link:",
        "upload_label": "📁 Or upload an audio/video file:",
        "btn": "Start Transcription",
        "success": "✅ Transcript generated successfully!",
        "download": "📄 Download Text File",
        "wait": "⏳ Please wait 30 seconds before trying again",
        "error": "An error occurred while processing the video 😞",
        "lang_switch": "تبديل اللغة إلى العربية"
    }
}

# اللغة الحالية
if "lang" not in st.session_state:
    st.session_state.lang = "ar"
t = LANG[st.session_state.lang]

# التبديل بين اللغتين
if st.button(t["lang_switch"]):
    st.session_state.lang = "en" if st.session_state.lang == "ar" else "ar"
    st.rerun()

# عنوان ووصف الصفحة
st.title(t["title"])
st.write(t["desc"])

# وظيفة تحميل الصوت من يوتيوب
def download_audio(video_url):
    output_file = "audio.mp3"
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_file,
        "quiet": True,
        "cookiefile": "cookies.txt",  # دعم ملفات الكوكيز لتجاوز القيود
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(video_url, download=True)
    return output_file

# تخزين آخر وقت تنفيذ
if "last_run" not in st.session_state:
    st.session_state.last_run = 0

# إدخال المستخدم
video_url = st.text_input(t["video_label"])
uploaded_file = st.file_uploader(t["upload_label"], type=["mp3", "mp4", "wav", "m4a"])

if st.button(t["btn"]):
    now = time.time()
    if now - st.session_state.last_run < 30:
        st.warning(t["wait"])
    else:
        st.session_state.last_run = now
        try:
            # تحديد مصدر الصوت
            audio_path = None
            if video_url:
                with st.spinner("📥 يتم تحميل الصوت من يوتيوب..."):
                    audio_path = download_audio(video_url)
            elif uploaded_file:
                audio_path = f"temp_{uploaded_file.name}"
                with open(audio_path, "wb") as f:
                    f.write(uploaded_file.read())
            else:
                st.error("⚠️ يرجى إدخال رابط أو رفع ملف.")
                st.stop()

            # بدء التفريغ باستخدام AssemblyAI
            with st.spinner("🧠 جارٍ تحليل وتفريغ الصوت..."):
                transcriber = aai.Transcriber()
                transcript = transcriber.transcribe(audio_path)

            # عرض النص وتحميله
            if transcript.status == aai.TranscriptStatus.completed:
                st.success(t["success"])
                st.text_area("📜 النص:", transcript.text, height=400)
                st.download_button(
                    label=t["download"],
                    data=transcript.text,
                    file_name="transcript.txt",
                    mime="text/plain"
                )
            else:
                st.error(f"{t['error']}\n\n🔍 التفاصيل: {transcript.error}")
        except Exception as e:
            st.error(f"{t['error']}\n\n🔍 التفاصيل: {e}")
