"""
Camera streaming bridge -- run this on your Windows host (NOT inside
Docker) alongside `docker compose up`.

Why this exists: Docker on Windows can't pass a physical webcam device
straight into a Linux container the way it can on native Linux (there's
no /dev/video0 to map). Instead of that direct hardware passthrough, this
script captures your webcam locally and re-serves it as a live MJPEG
network stream. The containerized app then reads that stream over the
network -- from OpenCV's point of view, an MJPEG HTTP stream and a local
camera device both just look like "a sequence of frames," so no changes
were needed to preprocessing.py, detector.py, or pipeline.py.

This mirrors how many real IP cameras and dashcams actually work (they
stream over a network too), so it's a reasonable stand-in for how a real
vehicle deployment might feed a networked camera into a containerized
processing pipeline, not just a workaround.

Usage:
    python host_camera_server.py

Then, with docker-compose.yml's app service pointed at
http://host.docker.internal:5000/video_feed (see the CLEARROAD_VIDEO_SOURCE
env var there), run `docker compose up --build` in another terminal.

Requires Flask (not in requirements.txt, since this only runs on the
host, not inside the container): pip install flask
"""

import cv2
from flask import Flask, Response

import config

app = Flask(__name__)

# Uses the same VIDEO_SOURCE the native app would use for a webcam (0 by
# default). If you've set CLEARROAD_VIDEO_SOURCE for the container, that
# does NOT affect this script -- this always captures directly from the
# local device index below.
CAMERA_INDEX = 0


def generate_frames():
    capture = cv2.VideoCapture(CAMERA_INDEX)
    if not capture.isOpened():
        raise RuntimeError(f"Could not open camera at index {CAMERA_INDEX}")

    try:
        while True:
            success, frame = capture.read()
            if not success:
                break

            # MJPEG streaming works by repeatedly sending JPEG-encoded
            # frames separated by a boundary marker -- this is the
            # "multipart/x-mixed-replace" format browsers and OpenCV
            # both know how to read as a live stream.
            ok, buffer = cv2.imencode(".jpg", frame)
            if not ok:
                continue
            frame_bytes = buffer.tobytes()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )
    finally:
        capture.release()


@app.route("/video_feed")
def video_feed():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/")
def index():
    return (
        "ClearRoad AI camera bridge is running. "
        "Point VIDEO_SOURCE at /video_feed to consume the stream."
    )


if __name__ == "__main__":
    # host="0.0.0.0" so the stream is reachable from inside the Docker
    # container (via host.docker.internal), not just from this machine.
    app.run(host="0.0.0.0", port=5000, threaded=True)