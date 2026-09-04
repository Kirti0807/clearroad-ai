"""
Main application window: live video feed with bounding boxes drawn on
detected hazards, plus a small status panel. Polls the pipeline's output
queue on a Tkinter `.after()` timer instead of blocking, which is what
keeps this responsive alongside the background processing thread.
"""

import cv2
import customtkinter as ctk
from PIL import Image

import config
from dashboard import DashboardFrame
from pipeline import HazardPipeline

# Distinct colors per hazard class so the driver can tell object types
# apart at a glance without reading the label every time.
BOX_COLORS = {
    "pedestrian": (0, 0, 255),     # red -- highest caution
    "car": (0, 255, 0),
    "truck": (0, 165, 255),
    "bus": (255, 0, 0),
    "motorcycle": (0, 255, 255),
    "cyclist": (255, 0, 255),
}


class ClearRoadApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(config.WINDOW_TITLE)
        self.geometry(config.WINDOW_SIZE)
        ctk.set_appearance_mode("dark")

        self._build_layout()

        self._pipeline = HazardPipeline()
        self._pipeline.start()

        self._poll_pipeline()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        live_tab = self.tabview.add("Live Feed")
        dashboard_tab = self.tabview.add("Admin Dashboard")

        # --- Live Feed tab ---
        self.video_label = ctk.CTkLabel(live_tab, text="")
        self.video_label.pack(padx=10, pady=10)

        status_frame = ctk.CTkFrame(live_tab)
        status_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.visibility_label = ctk.CTkLabel(
            status_frame, text="Visibility score: --", font=("Arial", 14)
        )
        self.visibility_label.pack(side="left", padx=10, pady=8)

        self.hazard_count_label = ctk.CTkLabel(
            status_frame, text="Hazards in view: 0", font=("Arial", 14)
        )
        self.hazard_count_label.pack(side="left", padx=10, pady=8)

        # --- Admin Dashboard tab ---
        # Lazily built, refreshed each time the tab is selected (see below)
        # rather than polled continuously -- dashboard data changes on the
        # order of seconds, not frames, so there's no need to redraw charts
        # on every GUI tick the way the live feed does.
        self.dashboard_frame = DashboardFrame(dashboard_tab)
        self.dashboard_frame.pack(fill="both", expand=True)
        self.tabview.configure(command=self._on_tab_changed)

    def _on_tab_changed(self):
        if self.tabview.get() == "Admin Dashboard":
            self.dashboard_frame.refresh()

    def _poll_pipeline(self):
        result = self._pipeline.get_latest(timeout=0.01)
        if result is not None:
            frame, detections, visibility_score = result
            self._render_frame(frame, detections)
            self.visibility_label.configure(text=f"Visibility score: {visibility_score}")
            self.hazard_count_label.configure(text=f"Hazards in view: {len(detections)}")

        # Re-poll shortly; this is what keeps the UI thread free between frames.
        self.after(30, self._poll_pipeline)

    def _render_frame(self, frame_bgr, detections):
        annotated = frame_bgr.copy()
        for detection in detections:
            x1, y1, x2, y2 = detection.box
            color = BOX_COLORS.get(detection.class_name, (255, 255, 255))
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            label = f"{detection.class_name} {detection.confidence:.2f}"
            cv2.putText(
                annotated, label, (x1, max(y1 - 8, 0)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2,
            )

        resized = cv2.resize(annotated, config.VIDEO_DISPLAY_SIZE)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        # CTkImage (rather than a raw PIL.ImageTk.PhotoImage) is what
        # customtkinter expects -- it scales correctly on HighDPI displays,
        # which a plain PhotoImage does not.
        ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=config.VIDEO_DISPLAY_SIZE)

        self.video_label.configure(image=ctk_image)
        self.video_label.image = ctk_image  # Keep a reference -- Tkinter drops unreferenced images.

    def _on_close(self):
        self._pipeline.stop()
        self.destroy()