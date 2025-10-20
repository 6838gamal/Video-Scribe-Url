# Dockerfile
FROM python:3.11-slim

# تثبيت أدوات النظام المطلوبة
RUN apt-get update && apt-get install -y ffmpeg wget build-essential git && rm -rf /var/lib/apt/lists/*

# نسخ المتطلبات
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# نسخ التطبيق
COPY app.py /app/

# تعيين المنفذ
EXPOSE 8501

# أمر التشغيل
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
