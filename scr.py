import streamlit as st
import requests
import os
from pytube import YouTube
import time

# ---------------- إعداد الصفحة ----------------
st.set_page_config(
    page_title="🎬 Video Transcriber",
    page_icon="🎧",
    layout="wide"
)

st.title("🎬 محول الفيديو إلى نصوص")
st.write("قم بلصق رابط الفيديو أو رفع ملف صوتي/فيديو، واختر الخدمة واللغة.")

# ---------------- الإعدادات ----------------
col1, col2, col3 = st.columns(3)
with col1:
    input_type = st.radio("📥 مصدر الإدخال:", ["رابط الفيديو", "رفع ملف"])
with col2:
    service = st.selectbox("🧠 الخدمة:", ["AssemblyAI", "Deepgram"])
with col3:
    lang = st.selectbox("🌐 اللغة:", ["العربية", "الإنجليزية"])

api_key = st.text_input("🔑 مفتاح الـ API الخاص بك:", type="password")

# ---------------- معالجة الإدخال ----------------
audio_path = None

if input_type == "رابط الفيديو":
    video_url = st.text_input("🎥 أدخل رابط الفيديو:")
    if video_url and st.button("⬇️ تحميل الصوت"):
        try:
            st.info("📥 جاري تحميل الصوت من الفيديو...")
            yt = YouTube(video_url)
            stream = yt.streams.filter(only_audio=True).first()
            audio_path = stream.download(filename="audio.mp4")
            st.success("✅ تم استخراج الصوت بنجاح.")
        except Exception as e:
            st.error(f"⚠️ خطأ أثناء التحميل: {e}")

else:
    uploaded_file = st.file_uploader("📂 ارفع ملف صوتي أو فيديو", type=["mp4", "mp3", "wav", "m4a"])
    if uploaded_file:
        with open("uploaded_audio.mp4", "wb") as f:
            f.write(uploaded_file.read())
        audio_path = "uploaded_audio.mp4"
        st.success("✅ تم رفع الملف بنجاح.")

# ---------------- بدء التفريغ ----------------
if audio_path and api_key and st.button("🚀 ابدأ التفريغ"):
    try:
        if service == "AssemblyAI":
            st.info("⏳ رفع الصوت إلى AssemblyAI...")
            upload_url = "https://api.assemblyai.com/v2/upload"
            headers = {"authorization": api_key}
            with open(audio_path, "rb") as f:
                upload_response = requests.post(upload_url, headers=headers, data=f)
            audio_url = upload_response.json()["upload_url"]

            # إعداد اللغة
            language_code = "ar" if lang == "العربية" else "en_us"

            # بدء عملية التفريغ
            transcript_endpoint = "https://api.assemblyai.com/v2/transcript"
            json_data = {"audio_url": audio_url, "language_code": language_code}
            response = requests.post(transcript_endpoint, headers=headers, json=json_data)
            transcript_id = response.json()["id"]

            # انتظار النتيجة
            progress = st.progress(0)
            for percent in range(0, 100, 10):
                progress.progress(percent)
                time.sleep(1)

            while True:
                status = requests.get(f"{transcript_endpoint}/{transcript_id}", headers=headers).json()
                if status["status"] == "completed":
                    progress.progress(100)
                    st.success("✅ تم التفريغ بنجاح!")
                    st.text_area("📝 النص الناتج:", status["text"], height=400)
                    break
                elif status["status"] == "error":
                    st.error("❌ حدث خطأ أثناء التفريغ.")
                    break
                time.sleep(3)

        elif service == "Deepgram":
            st.info("⏳ جاري إرسال الملف إلى Deepgram...")
            upload_url = f"https://api.deepgram.com/v1/listen?language={'ar' if lang == 'العربية' else 'en'}"
            headers = {"Authorization": f"Token {api_key}"}
            with open(audio_path, "rb") as f:
                response = requests.post(upload_url, headers=headers, files={"file": f})
            result = response.json()
            transcript = result["results"]["channels"][0]["alternatives"][0]["transcript"]
            st.success("✅ تم التفريغ بنجاح!")
            st.text_area("📝 النص الناتج:", transcript, height=400)

    except Exception as e:
        st.error(f"⚠️ حدث خطأ أثناء التفريغ: {e}")
