FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY streamlit_app.py sitecustomize.py ./

ENV PYTHONPATH=/app/src \
    OUTPUT_DIR=/app/output \
    PYTHONUNBUFFERED=1

RUN mkdir -p /app/output/logs

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
