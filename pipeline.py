"""
Runs video capture + CLAHE + YOLO detection on a background thread and
pushes finished frames to a queue the GUI can safely poll.

This is the piece that keeps the GUI responsive: without this thread,
running detection in the same loop as the customtkinter window would
freeze the UI every time a frame is processed.
"""

import queue
import threading
import time

import cv2

import config
import db
from alerts import VoiceAlertSystem
from detector import HazardDetector
from preprocessing import VisibilityEnhancer

# Logging every single frame would flood the DB at 15fps for little benefit.
# Log on this cadence instead -- frequent enough for a meaningful dashboard
# trend line, infrequent enough to not hammer the connection.
DB_LOG_INTERVAL_SECONDS = 2.0


class HazardPipeline:
    def __init__(self, video_source=config.VIDEO_SOURCE, enable_db_logging=True):
        self._video_source = video_source
        self._enhancer = VisibilityEnhancer()
        self._detector = HazardDetector()
        self._alerts = VoiceAlertSystem()
        self._enable_db_logging = enable_db_logging
        self._last_db_log_time = 0.0

        # Holds the latest processed (frame, detections, visibility_score) tuple.
        # maxsize=1 + non-blocking put deliberately drops stale frames rather
        # than backing up -- the GUI only ever wants the newest frame.
        self._output_queue: "queue.Queue[tuple]" = queue.Queue(maxsize=1)

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        if self._enable_db_logging:
            try:
                db.init_schema()
            except Exception:
                # DB not reachable (e.g. not started yet) -- keep running in
                # live-view-only mode rather than blocking app startup on it.
                self._enable_db_logging = False
        self._thread.start()

    def _run(self):
        capture = cv2.VideoCapture(self._video_source)
        if not capture.isOpened():
            raise RuntimeError(f"Could not open video source: {self._video_source}")

        frame_interval = 1.0 / config.TARGET_FPS

        while not self._stop_event.is_set():
            loop_start = time.time()

            success, frame = capture.read()
            if not success:
                break  # End of file, or camera disconnected.

            enhanced = self._enhancer.enhance(frame)
            visibility_score = self._enhancer.estimate_visibility_score(frame)
            detections = self._detector.detect(enhanced)

            for detection in detections:
                self._alerts.maybe_alert(detection.class_name, detection.box_height_ratio)

            if self._enable_db_logging and (loop_start - self._last_db_log_time) >= DB_LOG_INTERVAL_SECONDS:
                self._last_db_log_time = loop_start
                db.log_visibility(visibility_score)
                db.log_hazards(detections, visibility_score)

            # Drop any stale unread frame before pushing the new one.
            if self._output_queue.full():
                try:
                    self._output_queue.get_nowait()
                except queue.Empty:
                    pass
            self._output_queue.put((enhanced, detections, visibility_score))

            elapsed = time.time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        capture.release()

    def get_latest(self, timeout=0.1):
        """Returns (frame, detections, visibility_score) or None if nothing new yet."""
        try:
            return self._output_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        self._stop_event.set()
        self._thread.join(timeout=2)
        self._alerts.shutdown()
