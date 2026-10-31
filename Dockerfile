# Use an official lightweight Python runtime base layer
FROM python:3.12-slim

# Set system environment adjustments to keep Python output responsive
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STREAMLIT_SERVER_PORT=8080 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Install system dependencies (Portaudio and Build Essential for compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    portaudio19-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set the active working context directory inside the container
WORKDIR /app

# Copy dependency requirements files and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your complete application, scripts, and the pre-seeded sqlite database file
COPY app.py .
COPY community_hero.db .

# Expose the standard Cloud Run port target descriptor
EXPOSE 8080

# Trigger the Streamlit server execution command on container launch
CMD ["streamlit", "run", "app.py"]