import os
import streamlit as st
import subprocess
import tempfile
import assemblyai as aai
import time

# إعداد مفاتيح البيئة
ASSEMBLY_KEY = os.getenv("ASSEMBLYAI_API_KEY", "")
COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")

aai.settings.api_key = ASSEMBLY_KEY


# --------------------------- 🔐 التحقق من الكوكيز ----------------------------
def ensure_cookies():
    """يتأكد من وجود ملف الكوكيز"""
    if os.path.exists(COOKIES_FILE):
        return True
    else:
        return False


# --------------------------- 🎧 تحميل الصوت ----------------------------
def download_audio(url):
    """تحميل الصوت من الرابط"""
    st.info("🎬 جاري تحميل الصوت من الرابط...")
    temp_file = os.path.join(tempfile.gettempdir(), "audio.mp3")
    cmd = [
        "yt-dlp",
        "-f", "bestaudio",
        "--no-playlist",
        "-x",
        "--audio-format", "mp3",
        "-o", temp_file,
    ]

    if ensure_cookies():
        cmd.extend(["--cookies", COOKIES_FILE])

    cmd.append(url)

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return temp_file
    except subprocess.CalledProcessError as e:
        st.error("❌ فشل تحميل الصوت من الرابط. جرب رفع الملف مباشرة أو تحقق من الكوكيز.")
        st.caption(str(e))
        return None


# --------------------------- 🧾 التفريغ النصي ----------------------------
def transcribe_audio(file_path):
    """تفريغ النص من الصوت باستخدام AssemblyAI"""
    transcriber = aai.Transcriber()
    with st.spinner("🧠 جاري التفريغ النصي..."):
        transcript = transcriber.transcribe(file_path)
        return transcript.text


# --------------------------- 🌐 إعداد الواجهة ----------------------------
LANGUAGES = {
    "ar": {
        "title": "🎧 تفريغ محتوى الفيديو إلى نص",
        "desc": "ألصق رابط الفيديو أو ارفع ملفًا صوتيًا، واحصل على النص الكامل.",
        "input_label": "📎 أدخل الرابط:",
        "or_upload": "أو ارفع ملفًا صوتيًا / فيديو 🎵",
        "button": "ابدأ التفريغ",
        "downloading": "جارٍ التحميل...",
        "transcribing": "جارٍ التفريغ النصي...",
        "error": "❌ حدث خطأ أثناء المعالجة.",
        "success": "✅ تم التفريغ بنجاح!",
        "download": "💾 تحميل النص كملف",
        "switch": "🇺🇸 English",
    },
    "en": {
        "title": "🎧 Video/Audio to Text Transcriber",
        "desc": "Paste the video link or upload an audio file to extract text.",
        "input_label": "📎 Enter video/audio URL:",
        "or_upload": "Or upload an audio/video file 🎵",
        "button": "Start Transcription",
        "downloading": "Downloading audio...",
        "transcribing": "Transcribing text...",
        "error": "❌ An error occurred during processing.",
        "success": "✅ Transcription completed successfully!",
        "download": "💾 Download transcript",
        "switch": "🇸🇦 العربية",
    },
}


# --------------------------- 🚀 واجهة التطبيق ----------------------------
def main():
    st.set_page_config(page_title="Smart Transcriber", page_icon="🎧", layout="centered")

    # 🌐 اختيار اللغة
    if "lang" not in st.session_state:
        st.session_state.lang = "ar"

    lang = st.session_state.lang
    t = LANGUAGES[lang]

    # زر التبديل
    if st.button(t["switch"]):
        st.session_state.lang = "en" if lang == "ar" else "ar"
        st.rerun()

    # العنوان والوصف
    st.markdown(
        f"<h2 style='text-align:center; color:#00b4d8;'>{t['title']}</h2>", unsafe_allow_html=True
    )
    st.write(t["desc"])

    # إدخال الرابط
    url = st.text_input(t["input_label"])

    # أو رفع الملف
    uploaded_file = st.file_uploader(t["or_upload"], type=["mp3", "mp4", "wav", "m4a"])

    if st.button(t["button"]):
        try:
            start_time = time.time()

            # تحميل أو استخدام الملف
            if url:
                audio_path = download_audio(url)
                if not audio_path:
                    st.error(t["error"])
                    return
            elif uploaded_file:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                    tmp.write(uploaded_file.read())
                    audio_path = tmp.name
            else:
                st.warning("⚠️ يرجى إدخال الرابط أو رفع الملف.")
                return

            # التفريغ
            transcript_text = transcribe_audio(audio_path)

            # النجاح
            if transcript_text:
                st.success(t["success"])
                st.text_area("📝 النص المستخرج:", transcript_text, height=300)

                # زر التحميل
                st.download_button(
                    label=t["download"],
                    data=transcript_text,
                    file_name="transcript.txt",
                    mime="text/plain",
                )

                duration = time.time() - start_time
                st.caption(f"⏱️ استغرق التنفيذ: {duration:.2f} ثانية")
            else:
                st.error(t["error"])

        except Exception as e:
            st.error(f"{t['error']}\n\n🔍 التفاصيل: {str(e)}")


if __name__ == "__main__":
    main()
