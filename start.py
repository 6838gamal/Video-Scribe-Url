#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py
Streamlit single-file: تنزيل صوت من أي رابط يدعمه yt-dlp -> تحويل WAV -> كشف لغة تلقائي (langdetect)
-> تقسيم (قابل للتعديل) -> تحويل كل جزء إلى نص (speech_recognition) -> تنزيل النص.
مواصفات: واجهة احترافية، رسائل وتنبيهات، شريط تقدم، لوج مفصل، دعم ملف كوكيز.
"""

import os
import sys
import subprocess
import shutil
import tempfile
import re
import time
from pathlib import Path
from typing import Tuple, List

import streamlit as st

# ---- محاولات استيراد الحزم المطلوبة ----
missing_reqs = []
try:
    import speech_recognition as sr
except Exception:
    missing_reqs.append("SpeechRecognition")

try:
    from langdetect import detect
except Exception:
    missing_reqs.append("langdetect")

try:
    from tqdm import tqdm  # used locally in loops (not essential for UI)
except Exception:
    missing_reqs.append("tqdm")

# ---- إعداد الصفحة ----
st.set_page_config(page_title="Video → Text (Auto Lang) — Pro UI", layout="wide")
st.title("🎬 Video → Text (WAV) — ذكي مع كشف اللغة")
st.markdown(
    "ادخل رابط فيديو (YouTube, TikTok, Instagram, Facebook, ... )، سيقوم التطبيق بتنزيل الصوت (WAV)، "
    "الكشف التلقائي للغة، تقسيمه إن لزم، ثم تحويله إلى نص قابل للتنزيل."
)

# ---- متطلبات النظام الأساسية ----
def check_binary(name: str) -> bool:
    return shutil.which(name) is not None

bin_yt_dlp = check_binary("yt-dlp")
bin_ffmpeg = check_binary("ffmpeg")
bin_ffprobe = check_binary("ffprobe")

# ---- شريط جانبي للإعدادات ----
st.sidebar.header("⚙️ الإعدادات")
sample_seconds = st.sidebar.number_input("مدة العيّنة لاكتشاف اللغة (ثواني)", value=20, min_value=5, max_value=60, step=5)
segment_seconds = st.sidebar.number_input("طول كل جزء عند التقسيم (ثواني)", value=300, min_value=60, max_value=1800, step=30)
auto_remove_tmp = st.sidebar.checkbox("حذف الملفات المؤقتة بعد الانتهاء", value=True)
show_detailed_logs = st.sidebar.checkbox("عرض مخرجات yt-dlp/ffmpeg التفصيلية", value=False)
concurrency_sleep = st.sidebar.number_input("مهلة قصيرة بين أجزاء المعالجة (ثواني)", value=0.1, min_value=0.0, max_value=2.0, step=0.1)

st.sidebar.markdown("---")
st.sidebar.write("**تثبيت سريع للمتطلبات (مثال Debian/Ubuntu):**")
st.sidebar.code("sudo apt update && sudo apt install -y ffmpeg")
st.sidebar.code("pip install yt-dlp SpeechRecognition langdetect tqdm pydub streamlit")

# ---- عرض تحذيرات/نواقص ----
if missing_reqs or not bin_yt_dlp or not bin_ffmpeg:
    st.warning("⚠️ هناك تبعيات ناقصة أو برامج نظامية مفقودة.")
    if missing_reqs:
        st.info("مكتبات Python المفقودة: " + ", ".join(missing_reqs))
    if not bin_yt_dlp:
        st.info("أداة النظام المفقودة: yt-dlp")
    if not bin_ffmpeg:
        st.info("أداة النظام المفقودة: ffmpeg")
    st.markdown(
        "يرجى تثبيت الأدوات المطلوبة قبل المتابعة. انظر ال sidebar للخطوات السريعة."
    )

# ---- منطقة الإدخال الرئيسية ----
st.subheader("1) أدخل رابط الفيديو")
url = st.text_input("🌐 رابط الفيديو (أي رابط يدعمه yt-dlp):", placeholder="https://...")

st.subheader("2) خيارات متقدمة (اختياري)")
cookie_file = st.text_input("ملف كوكيز (مسار كامل) - اتركه فارغاً إن لم يكن مطلوباً:", placeholder="/path/to/cookies.txt")
filename_prefix = st.text_input("بادئة اسم الملف (اختياري)", placeholder="")  # optional prefix
start_button = st.button("▶ ابدأ العملية", type="primary")

# ---- دوال مساعدة ----
def safe_filename(s: str) -> str:
    s2 = re.sub(r"[^\w\-_\. ]", "_", s)
    return s2.strip().replace(" ", "_")

def run_cmd_capture(cmd: List[str], cwd=None, env=None) -> Tuple[int, str, str]:
    """Run command and capture stdout/stderr. Return (rc, stdout, stderr)."""
    try:
        completed = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False)
        return completed.returncode, completed.stdout or "", completed.stderr or ""
    except Exception as e:
        return 1, "", str(e)

def stream_ffmpeg_progress(cmd: List[str], total_seconds: float, log_output_area, prog_bar):
    """
    Run ffmpeg and parse stderr lines to extract 'time=' and update progress bar.
    total_seconds may be 0 (unknown) -> show indeterminate updates.
    """
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, bufsize=1)
    if proc.stderr is None:
        return proc.wait()
    for line in proc.stderr:
        if show_detailed_logs:
            log_output_area.text(line.strip())
        m = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
        if m and total_seconds:
            h, mm, ss = m.groups()
            elapsed = int(h) * 3600 + int(mm) * 60 + float(ss)
            percent = min(int((elapsed / total_seconds) * 100), 100)
            prog_bar.progress(percent)
    proc.wait()
    return proc.returncode

def get_duration_seconds(file_path: Path) -> float:
    """Use ffprobe to get duration in seconds. Return 0.0 on failure."""
    if not bin_ffprobe:
        return 0.0
    rc, out, err = run_cmd_capture(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)])
    if rc == 0:
        try:
            return float(out.strip())
        except Exception:
            return 0.0
    return 0.0

# ---- منطقة لعرض السجل والمخرجات ----
st.subheader("سجل التنفيذ")
log_area = st.empty()
log_text_lines = []

def log(msg: str, level: str = "info"):
    timestamp = time.strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    log_text_lines.append(line)
    # show recent lines (limit)
    max_lines = 200
    txt = "\n".join(log_text_lines[-max_lines:])
    log_area.code(txt)

# ---- وظيفة المعالجة الرئيسية ----
def process_url_to_text(url: str, cookie_file: str, prefix: str):
    if not url:
        st.error("لا يوجد رابط. الرجاء إدخال رابط صالح.")
        return

    # فحص المتطلبات الأساسية مجدداً
    if not bin_yt_dlp:
        st.error("yt-dlp غير مثبت على النظام. لا يمكن المتابعة.")
        return
    if not bin_ffmpeg:
        st.error("ffmpeg غير مثبت على النظام. لا يمكن المتابعة.")
        return
    try:
        import speech_recognition as sr  # reimport to ensure available at runtime
        from langdetect import detect
    except Exception as e:
        st.error(f"مكتبة بايثون مفقودة: {e}")
        return

    # مجلد عمل مؤقت
    with tempfile.TemporaryDirectory(prefix="vid2text_") as base_tmp:
        tmp_dir = Path(base_tmp) / "download"
        split_dir = Path(base_tmp) / "split"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        split_dir.mkdir(parents=True, exist_ok=True)

        # ---------- تنزيل الصوت مباشرة بصيغة WAV باستخدام yt-dlp ----------
        log("بدء تحميل الصوت عبر yt-dlp ...")
        st.info("⏳ جاري تنزيل الصوت وتحويله إلى WAV (yt-dlp)...")
        yt_cmd = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "wav",
            "--no-playlist",
            "-o", str(tmp_dir / "%(title).100s-%(id)s.%(ext)s"),
            "--no-warnings",
            "--embed-metadata",
        ]
        if cookie_file:
            yt_cmd += ["--cookies", cookie_file]
            log(f"استخدام ملف الكوكيز: {cookie_file}")
        yt_cmd.append(url)

        rc, out, err = run_cmd_capture(yt_cmd)
        if rc != 0:
            log(f"خطأ في yt-dlp: rc={rc}. stderr: {err}", "error")
            st.error("❌ فشل تحميل/استخراج الصوت. راجع السجل التفصيلي أدناه.")
            if show_detailed_logs:
                st.code(err or out)
            return
        else:
            log("تم تنزيل الصوت (أو استخراج) بنجاح.")

        # إيجاد ملف wav الناتج
        wav_files = sorted(tmp_dir.glob("*.wav"))
        if not wav_files:
            log("لم يتم العثور على ملف WAV بعد تشغيل yt-dlp.", "error")
            st.error("❌ لم يتم العثور على ملف WAV في مجلد التنزيل.")
            return

        src_wav = wav_files[0]
        title_base = safe_filename(src_wav.stem)
        if prefix:
            title_base = safe_filename(prefix) + "_" + title_base
        dst_wav = Path.cwd() / f"{title_base}.wav"

        # نقل الملف الى المجلد الحالي
        shutil.move(str(src_wav), str(dst_wav))
        log(f"نُقل ملف WAV إلى: {dst_wav}")
        st.success(f"✅ تم تنزيل الصوت: {dst_wav.name}")

        # ---------- كشف اللغة من عيّنة قصيرة ----------
        recognizer = sr.Recognizer()
        detected_lang = "en"
        st.info("🧠 جارِ اكتشاف اللغة من عيّنة قصيرة...")
        log("استخراج عيّنة (مدة {} ثانية) لاكتشاف اللغة...".format(sample_seconds))
        try:
            with sr.AudioFile(str(dst_wav)) as src:
                sample_audio = recognizer.record(src, duration=sample_seconds)
                # محاولة سريعة بدون تحديد لغة أولاً
                try:
                    sample_text = recognizer.recognize_google(sample_audio)
                except Exception:
                    # تجربة مع العربية كبديل لو فشلت
                    try:
                        sample_text = recognizer.recognize_google(sample_audio, language="ar")
                    except Exception:
                        sample_text = ""
                if sample_text.strip():
                    try:
                        detected_lang = detect(sample_text)
                        log(f"تم اكتشاف اللغة: {detected_lang} (من نص تجريبي)")
                        st.success(f"🌍 اللغة المكتشفة: {detected_lang}")
                    except Exception as e:
                        log(f"فشل كشف اللغة عبر langdetect: {e}", "warning")
                        st.warning("⚠️ تعذر كشف اللغة بدقة. سيتم استخدام الإنجليزية (en).")
                        detected_lang = "en"
                else:
                    log("لم ينتج نص كافٍ من العيّنة لاكتشاف اللغة.", "warning")
                    st.warning("⚠️ لم نتمكن من الحصول على نص من العيّنة لاكتشاف اللغة. سيتم استخدام الإنجليزية (en).")
                    detected_lang = "en"
        except Exception as e:
            log(f"خطأ أثناء أخذ العيّنة: {e}", "error")
            st.warning("⚠️ فشل أخذ العيّنة لاكتشاف اللغة. سيتم استخدام الإنجليزية (en).")
            detected_lang = "en"

        # ---------- تقسيم الصوت إلى أجزاء ----------
        st.info("⏳ جارِ تقسيم الصوت إلى أجزاء...")
        log(f"تنفيذ ffmpeg لتقسيم الصوت إلى أجزاء بطول {segment_seconds} ثانية...")
        split_cmd = [
            "ffmpeg", "-y", "-i", str(dst_wav),
            "-f", "segment",
            "-segment_time", str(int(segment_seconds)),
            "-c", "copy",
            str(split_dir / "part_%03d.wav")
        ]
        rc, out, err = run_cmd_capture(split_cmd)
        if rc != 0:
            log(f"خطأ في تقسيم الصوت ffmpeg: {err}", "error")
            st.error("❌ فشل تقسيم الصوت. راجع السجل التفصيلي.")
            if show_detailed_logs:
                st.code(err or out)
            return
        split_files = sorted(split_dir.glob("*.wav"))
        total_parts = len(split_files)
        st.success(f"✅ تم تقسيم الصوت إلى {total_parts} جزء.")
        log(f"عدد الأجزاء: {total_parts}")

        # ---------- تحويل كل جزء إلى نص مع شريط تقدم ----------
        st.info("🎤 جارِ تحويل الأجزاء إلى نص (قد يستغرق وقتًا)...")
        text_lines = []
        failed_parts = []
        progress_placeholder = st.empty()
        progress_bar = st.progress(0)
        part_preview = st.empty()
        parts_processed = 0

        for idx, part in enumerate(split_files, start=1):
            parts_processed += 1
            prefix_msg = f"• معالجة الجزء {idx}/{total_parts}: {part.name}"
            log(prefix_msg)
            part_preview.info(prefix_msg)

            try:
                with sr.AudioFile(str(part)) as src:
                    audio_data = recognizer.record(src)
                    # محاولة التعرف باستخدام اللغة المكتشفة
                    try:
                        text = recognizer.recognize_google(audio_data, language=detected_lang)
                    except Exception as e1:
                        # إذا فشل، حاول بدون لغة ثم بالعربية ثم بالإنجليزية كنسخة احتياطية
                        try:
                            text = recognizer.recognize_google(audio_data)
                        except Exception:
                            try:
                                text = recognizer.recognize_google(audio_data, language="ar")
                            except Exception:
                                try:
                                    text = recognizer.recognize_google(audio_data, language="en")
                                except Exception as e_final:
                                    raise e_final
                    # إذا نجح:
                    text_lines.append(text)
                    # عرض مقتطف
                    preview = text[:600] + ("..." if len(text) > 600 else "")
                    part_preview.success(preview)
                    log(f"نجح الجزء {part.name} — طول النص {len(text)} حرفاً")
            except Exception as e:
                failed_parts.append(part.name)
                log(f"فشل الجزء {part.name}: {e}", "warning")
                part_preview.warning(f"⚠️ فشل الجزء {part.name}: {e}")
            # تحديث التقدّم
            percent = int((parts_processed / total_parts) * 100)
            progress_bar.progress(percent)
            progress_placeholder.text(f"التقدم العام: {percent}%")
            time.sleep(float(concurrency_sleep))

        # ---------- حفظ النص النهائي ----------
        final_txt = Path.cwd() / f"{title_base}.txt"
        with open(final_txt, "w", encoding="utf-8") as f:
            for line in text_lines:
                f.write(line + "\n\n")
        st.success(f"✅ حفظ النص في: {final_txt.name}")
        log(f"تم حفظ النص النهائي: {final_txt}")

        # ---------- عرض نتائج نهائية وتنزيل ملفات ----------
        if failed_parts:
            st.error(f"⚠️ لم يتم التعرف على {len(failed_parts)} جزء. يمكنك مراجعتها في السجل.")
            st.write("قائمة الأجزاء الفاشلة:")
            for p in failed_parts:
                st.write(" - " + p)
        else:
            st.success("✅ جميع الأجزاء تمت بنجاح.")

        col1, col2 = st.columns(2)
        with col1:
            with open(final_txt, "rb") as f:
                st.download_button("⬇️ تنزيل ملف النص (.txt)", f, file_name=final_txt.name)
        with col2:
            with open(dst_wav, "rb") as f:
                st.download_button("⬇️ تنزيل ملف الصوت (.wav)", f, file_name=dst_wav.name)

        if auto_remove_tmp:
            # حذف المجلدات المؤقتة يتم تلقائياً عند الخروج من with TemporaryDirectory
            log("سيتم حذف الملفات المؤقتة تلقائياً.")
        else:
            st.info(f"المجلد المؤقت محفوظ في: {base_tmp} (لم يُحذف تلقائياً)")

        st.balloons()
        progress_bar.progress(100)
        return

# ---- التشغيل عند نقر الزر ----
if start_button:
    log_text_lines.clear()
    log("بدأ المستخدم العملية.")
    process_url_to_text(url.strip(), cookie_file.strip() if cookie_file else "", filename_prefix.strip())
