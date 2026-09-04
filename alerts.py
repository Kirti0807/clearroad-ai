"""
Voice alerting with a per-class cooldown so the driver isn't spammed with
"pedestrian! pedestrian! pedestrian!" every single frame a person stays in view.

Platform-aware backend:
- Windows: talks to SAPI directly via pywin32. pyttsx3's runAndWait() loop
  is known to go silent after the first call on Windows even when the
  engine is re-initialized each time -- talking to SAPI directly sidesteps
  that issue entirely and is what pyttsx3 wraps under the hood anyway.
- Linux (e.g. inside the Docker container): win32com doesn't exist here,
  so we fall back to pyttsx3, which uses the espeak-ng backend installed
  in the Dockerfile. The Windows-only silent-after-first-call bug is a
  SAPI-specific issue and doesn't affect the espeak backend.
"""

import platform
import queue
import threading
import time

import config

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    import win32com.client
else:
    import pyttsx3


class VoiceAlertSystem:
    def __init__(self):
        self._last_alert_time: dict[str, float] = {}
        self._speech_queue: "queue.Queue[str]" = queue.Queue()
        self._stop_event = threading.Event()

        # The voice engine isn't safe to call from multiple threads
        # concurrently, so we run a single dedicated speech thread and feed
        # it messages through a queue rather than calling it directly from
        # the detection thread.
        self._speech_thread = threading.Thread(target=self._speech_worker, daemon=True)
        self._speech_thread.start()

    def _speech_worker(self):
        if IS_WINDOWS:
            self._speech_worker_windows()
        else:
            self._speech_worker_linux()

    def _speech_worker_windows(self):
        # COM objects must be initialized on the thread that uses them.
        import pythoncom
        pythoncom.CoInitialize()

        voice = win32com.client.Dispatch("SAPI.SpVoice")

        while not self._stop_event.is_set():
            try:
                message = self._speech_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            # Flags=0 means synchronous (blocks until this message finishes
            # speaking) -- fine here since this thread has nothing else to do.
            voice.Speak(message, 0)

        pythoncom.CoUninitialize()

    def _speech_worker_linux(self):
        engine = pyttsx3.init(driverName="espeak")
        while not self._stop_event.is_set():
            try:
                message = self._speech_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            engine.say(message)
            engine.runAndWait()

    def maybe_alert(self, class_name: str, box_height_ratio: float):
        """
        Queues a spoken alert if the object is close enough (proximity proxy)
        and the per-class cooldown has elapsed.
        """
        if box_height_ratio < config.HAZARD_PROXIMITY_HEIGHT_RATIO:
            return

        now = time.time()
        last_time = self._last_alert_time.get(class_name, 0)
        if now - last_time < config.ALERT_COOLDOWN_SECONDS:
            return

        self._last_alert_time[class_name] = now
        self._speech_queue.put(f"{class_name} ahead")

    def shutdown(self):
        self._stop_event.set()
        self._speech_thread.join(timeout=2)