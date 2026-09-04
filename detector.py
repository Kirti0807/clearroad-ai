"""
Thin wrapper around YOLOv8n so the rest of the app doesn't need to know
about ultralytics' API directly -- makes it easy to swap models later
(e.g. a fine-tuned fog-specific model) without touching the GUI/pipeline code.
"""

from dataclasses import dataclass

from ultralytics import YOLO

import config


@dataclass
class Detection:
    class_name: str       # Friendly label, e.g. "pedestrian"
    confidence: float
    box: tuple             # (x1, y1, x2, y2) in pixel coords
    box_height_ratio: float  # box height / frame height -- used as a proximity proxy


class HazardDetector:
    def __init__(self, model_path: str = config.YOLO_MODEL_PATH):
        self._model = YOLO(model_path)
        self._target_classes = config.YOLO_TARGET_CLASSES

    def detect(self, frame_bgr) -> list[Detection]:
        frame_height = frame_bgr.shape[0]

        results = self._model.predict(
            source=frame_bgr,
            conf=config.YOLO_CONFIDENCE_THRESHOLD,
            verbose=False,
        )[0]

        detections: list[Detection] = []
        for box in results.boxes:
            raw_class_name = results.names[int(box.cls[0])]
            if raw_class_name not in self._target_classes:
                continue  # Ignore classes we don't care about (e.g. "chair", "kite")

            x1, y1, x2, y2 = box.xyxy[0].tolist()
            confidence = float(box.conf[0])
            box_height_ratio = (y2 - y1) / frame_height

            detections.append(
                Detection(
                    class_name=self._target_classes[raw_class_name],
                    confidence=round(confidence, 2),
                    box=(int(x1), int(y1), int(x2), int(y2)),
                    box_height_ratio=round(box_height_ratio, 3),
                )
            )
        return detections
