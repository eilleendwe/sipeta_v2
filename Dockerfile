# Image untuk Hugging Face Spaces (SDK Docker). Streamlit Community Cloud tidak memakai berkas ini.
FROM python:3.11-slim

# Spaces menjalankan container sebagai user id 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

EXPOSE 7860
# enableXsrfProtection=false: Spaces menampilkan app di dalam iframe, dan tanpa ini unggahan berkas
# ditolak (403).
CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0", \
     "--server.headless=true", "--server.enableXsrfProtection=false"]
