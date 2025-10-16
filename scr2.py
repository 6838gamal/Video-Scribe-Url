import streamlit as st
import time
import requests
import yt_dlp
import os
from io import BytesIO

# إعداد الصفحة
st.set_page_config(page_title="🎧 Video Transcriber", layout="centered")

# واجهة متعددة اللغات
LANGUAGES = {
    "العربية": {
        "title": "🎧 تفريغ الفيديو إلى نص",
        "video_url": "أدخل رابط الفيديو:",
        "transcribe": "تفريغ النص",
        "download": "تحميل النص",
        "cooldown": "⏳ الرجاء الانتظار 30 ثانية قبل المحاولة مرة أخرى.",
        "success": "✅ تم التفريغ بنجاح!",
        "error": "حدث خطأ أثناء التفريغ. الرجاء المحاولة لاحقًا.",
        "no_url": "❌ يرجى إدخال رابط فيديو أولًا.",
        "loading": "⏳ جاري استخراج النص...",
        "fail_audio": "⚠️ لم يتم تحميل الصوت من الفيديو."
    },
    "English": {
        "title": "🎧 Video to Text Transcription",
        "video_url": "Enter video URL:",
        "transcribe": "Transcribe",
        "download": "Download Text",
        "cooldown": "⏳ Please wait 30 seconds before trying again.",
        "success": "✅ Transcription completed successfully!",
        "error": "An error occurred during transcription. Please try again later.",
        "no_url": "❌ Please enter a video URL first.",
        "loading": "⏳ Extracting text...",
        "fail_audio": "⚠️ Audio extraction from video failed."
    }
}

# اختيار اللغة
lang_choice = st.sidebar.selectbox("🌐 Language / اللغة", options=["العربية", "English"])
t = LANGUAGES[lang_choice]

st.title(t["title"])

# جلب المفاتيح من متغيرات البيئة
ASSEMBLY_KEY = os.getenv("ASSEMBLYAI_API_KEY")
DEEPGRAM_KEY = os.getenv("DEEPGRAM_API_KEY")

# التحقق من وجود المفاتيح
if not ASSEMBLY_KEY:
    st.warning("⚠️ لم يتم العثور على متغير البيئة: ASSEMBLYAI_API_KEY")
if not DEEPGRAM_KEY:
    st.warning("⚠️ لم يتم العثور على متغير البيئة: DEEPGRAM_API_KEY")

video_url = st.text_input(t["video_url"], "")

# مؤقت منع التكرار
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = 0

def can_transcribe():
    now = time.time()
    if now - st.session_state.last_request_time < 30:
        return False
    st.session_state.last_request_time = now
    return True

# تحميل الصوت من YouTube
def download_audio_from_youtube(url):
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'outtmpl': 'audio.%(ext)s',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")
        return filename
    except Exception as e:
        st.error(f"{t['fail_audio']} {e}")
        return None

# تفريغ الصوت عبر AssemblyAI
def transcribe_assemblyai(audio_file):
    try:
        headers = {"authorization": ASSEMBLY_KEY}
        upload_url = "https://api.assemblyai.com/v2/upload"

        with open(audio_file, "rb") as f:
            upload_response = requests.post(upload_url, headers=headers, data=f)
        upload_response.raise_for_status()
        audio_url = upload_response.json()["upload_url"]

        transcript_request = {"audio_url": audio_url}
        response = requests.post("https://api.assemblyai.com/v2/transcript", json=transcript_request, headers=headers)
        response.raise_for_status()
        transcript_id = response.json()["id"]

        # الانتظار حتى الانتهاء
        while True:
            poll = requests.get(f"https://api.assemblyai.com/v2/transcript/{transcript_id}", headers=headers).json()
            if poll["status"] == "completed":
                return poll["text"]
            elif poll["status"] == "error":
                raise Exception(poll["error"])
            time.sleep(3)
    except Exception:
        return None

# تفريغ الصوت عبر Deepgram كخيار احتياطي
def transcribe_deepgram(audio_file):
    try:
        headers = {"Authorization": f"Token {DEEPGRAM_KEY}"}
        with open(audio_file, "rb") as f:
            response = requests.post(
                "https://api.deepgram.com/v1/listen?model=whisper-large",
                headers=headers,
                data=f
            )
        if response.status_code == 200:
            return response.json()["results"]["channels"][0]["alternatives"][0]["transcript"]
        else:
            raise Exception(response.text)
    except Exception:
        return None

# زر التفريغ
if st.button(t["transcribe"]):
    if not can_transcribe():
        st.warning(t["cooldown"])
    elif not video_url:
        st.error(t["no_url"])
    else:
        try:
            with st.spinner(t["loading"]):
                audio_file = download_audio_from_youtube(video_url)
                if not audio_file:
                    st.error(t["fail_audio"])
                    st.stop()

                transcript = transcribe_assemblyai(audio_file)
                if not transcript:
                    transcript = transcribe_deepgram(audio_file)

                if not transcript:
                    st.error(t["error"])
                else:
                    st.success(t["success"])
                    st.text_area("📝", transcript, height=300)
                    st.download_button(t["download"], transcript, file_name="transcript.txt")
        except Exception as e:
            st.error(f"{t['error']}\n\n{e}")
        finally:
            if os.path.exists("audio.mp3"):
                os.remove("audio.mp3")
