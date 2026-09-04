# ClearRoad AI -- app container
# Note: this runs a Tkinter-based GUI app, so it needs an X server on the
# host to display to (VcXsrv/XLaunch on Windows) -- see docker-compose.yml
# for the DISPLAY env var wiring, and the README for VcXsrv setup.

FROM python:3.10-slim

# System libs needed by opencv-python and Tkinter's display connection.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    python3-tk \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
