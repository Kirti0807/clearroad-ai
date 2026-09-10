# ClearRoad AI

AI-powered smart road visibility & hazard detection for drivers in fog,
haze, or heavy rain.

## Problem

Reduced visibility from fog is a major cause of road accidents — drivers
can't spot pedestrians, vehicles, or obstacles in time to react, especially
on highways and in regions with seasonal fog. Existing driver-assistance
systems fall short in a few specific ways:

- **Expensive** — LiDAR/radar-based ADAS systems are out of reach for most vehicles
- **Not built for fog specifically** — standard camera-based detection performs
  poorly on hazy footage, since fog degrades contrast and edge detail before
  a model even sees anything useful
- **Not real-time or accessible** — much of the research in this space is
  offline image enhancement, not a live, driver-facing warning system

## How ClearRoad AI solves it

Rather than feeding a foggy frame straight into a detector, the pipeline
enhances first, detects second:

1. **CLAHE enhancement** — boosts local contrast in hazy regions before
   detection runs, so YOLO isn't trying to find objects buried in haze
2. **YOLOv8 Nano detection** — small enough to run in real time without
   expensive onboard compute, so it's actually deployable
3. **Voice alerts** — bounding boxes plus spoken warnings ("pedestrian
   ahead") mean the driver doesn't have to stare at a screen to react
4. **Visibility/hazard analytics** — the admin dashboard turns individual
   detections into trends over time (e.g. spotting a chronically foggy
   stretch of road), useful beyond a single driver

**One-line pitch:** restores visibility in degraded footage in real time
and turns that into both immediate driver alerts and longer-term hazard
analytics — using just a camera and lightweight models, no specialized
sensors required.

## Project structure

```
clearroad_ai/
├── main.py               # Entry point — run this
├── gui.py                 # customtkinter window: Live Feed + Admin Dashboard tabs
├── pipeline.py              # Background thread: capture → CLAHE → YOLO → alerts → DB logging
├── preprocessing.py          # CLAHE visibility enhancement
├── detector.py                 # YOLOv8n wrapper
├── alerts.py                    # Voice alert system (platform-aware: SAPI on Windows, espeak on Linux/Docker)
├── db.py                          # CockroachDB/PostgreSQL schema + queries
├── dashboard.py                    # Admin dashboard UI (charts, logs, user management)
├── config.py                        # All tunable settings live here
├── host_camera_server.py            # Streams the host webcam over HTTP for the Docker container to consume
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Option A — Run locally without Docker (fastest way to start)

1. **Create a virtual environment** (Python 3.10 recommended):
   ```bash
   python -m venv venv
   venv\Scripts\activate        # Windows
   source venv/bin/activate     # macOS/Linux
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run a local CockroachDB instance** (or skip this — see "Running without a database" below):
   ```bash
   docker run -d --name clearroad-db -p 26257:26257 -p 8080:8080 \
     cockroachdb/cockroach:v23.2.0 start-single-node --insecure
   ```

4. **Run the app:**
   ```bash
   python main.py
   ```
   Defaults to your live webcam (`VIDEO_SOURCE = 0`). First run
   auto-downloads `yolov8n.pt` (~6MB) — needs internet once.

This is the fully working, low-latency version — live camera, detection,
voice alerts, and dashboard all confirmed working end-to-end here.

## Option B — Run everything with Docker Compose (with live camera)

This runs the app **and** CockroachDB together in containers, with your
**live** webcam bridged in over the network. Three pieces need to be
running at once, in this order:

1. **Install and start VcXsrv (XLaunch)** — lets the containerized GUI
   window display on your desktop:
   - Download VcXsrv, install, then run XLaunch
   - Choose "Multiple windows" → Display number `0` → "Start no client"
   - On "Extra settings", **check "Disable access control"**
   - Finish, and leave it running in the background

2. **Start the camera bridge** (in one terminal, on the host):
   ```bash
   pip install flask
   python host_camera_server.py
   ```
   This captures your webcam locally and re-serves it as a live MJPEG
   stream at `http://<your-ip>:5000/video_feed` — the same idea as how a
   real IP camera or networked dashcam works. Leave this running.

3. **Find your Windows host IP** (`ipconfig`, use your active adapter's
   IPv4 address), then in a **second terminal**:
   ```bash
   $env:DISPLAY="<your-ip>:0.0"     # PowerShell
   docker compose up --build
   ```
   `docker-compose.yml` points the container at
   `http://host.docker.internal:5000/video_feed` via the
   `CLEARROAD_VIDEO_SOURCE` env var, so it consumes your live camera bridge
   rather than a file.

### Why the bridge, instead of direct webcam passthrough?

Docker on Linux can map a physical camera straight into a container with
`--device=/dev/video0`. **Windows has no equivalent** — there's no
`/dev/video0` for Docker Desktop to pass through, so direct device
passthrough (what an earlier version of `docker-compose.yml` attempted)
fails outright on Windows/WSL2. The host-camera-stream bridge above works
around that by treating the camera as a network source instead of a local
device — which also happens to mirror how a lot of real dashcams and IP
cameras are actually deployed.

### Known Docker-on-Windows trade-offs (validated, not guessed)

- **Noticeably laggier than Option A.** Frames now travel: webcam → JPEG
  encode → network → container decode → CLAHE → YOLO (CPU-only, no GPU
  passthrough) → network → VcXsrv → your screen. Every hop adds latency.
- **No voice alerts.** VcXsrv solves *video* forwarding, not *audio*.
  Getting sound out of a Windows-hosted Linux container needs a separate
  audio bridge (e.g. a PulseAudio server on the host) that isn't set up
  here. Voice alerts are confirmed working in Option A.
- **These are Windows-specific dev-environment frictions, not flaws in the
  detection pipeline.** The actual target deployment for a system like
  this is Linux-based edge hardware (Raspberry Pi, NVIDIA Jetson, etc.),
  where camera passthrough, audio, and GUI display are all natively
  supported by Docker — none of the workarounds above would be needed.

If you don't need live camera through Docker specifically, it's simpler to
skip the bridge: set `CLEARROAD_VIDEO_SOURCE` to a video file path instead
(or remove the env var and hardcode `VIDEO_SOURCE` in `config.py`) and
Docker Compose will use that instead.

## Running without a database

The app degrades gracefully — if CockroachDB isn't running or reachable,
`pipeline.py` catches the connection failure at startup and disables DB
logging automatically. The live feed, detection, and voice alerts all keep
working; only the Admin Dashboard tab shows empty charts and "No hazard
events logged yet."

## Testing with real fog (not just a clear room/webcam)

A normal indoor webcam feed has no fog, so CLAHE has nothing to visibly
enhance. To actually see it work, point `VIDEO_SOURCE` at real foggy
footage:
```python
VIDEO_SOURCE = "foggy_test.mp4"
```
Free sources: Pexels/Pixabay ("foggy road" search), or the DAWN/RESIDE
research datasets. Validated on a real foggy driving clip — CLAHE
noticeably improved contrast, and YOLO correctly reported zero hazards on
fog-only frames with no actual pedestrians/vehicles present (i.e. it
didn't hallucinate hazards where there weren't any).

## Tuning (all in `config.py`)

Current tuned values, arrived at through live testing (not just defaults):

| Setting | Value | Why |
|---|---|---|
| `YOLO_CONFIDENCE_THRESHOLD` | `0.35` | More sensitive than the 0.4 default; catches more real detections at the cost of occasional low-confidence false positives (e.g. a patterned curtain read as a person at ~0.48) |
| `HAZARD_PROXIMITY_HEIGHT_RATIO` | `0.25` | Lowered from 0.35 so voice alerts fire earlier (further away), giving more reaction time |
| `ALERT_COOLDOWN_SECONDS` | `4` | Repeats the alert roughly every 4s while a hazard stays in view, without spamming every frame |
| `TARGET_FPS` | `15` | CPU-bound inference means real frame processing time is the actual bottleneck, not this cap |

Push `YOLO_CONFIDENCE_THRESHOLD` up toward 0.45-0.5 if false positives
become a problem; push it down toward 0.25 if real hazards are being
missed.

## Known limitations

- `estimate_visibility_score()` in `preprocessing.py` is a heuristic based
  on pixel intensity spread — a reasonable relative trend line, not a
  calibrated visibility measurement (a very hazy scene scored 85.6/100 in
  testing, higher than expected — worth stating plainly rather than
  overclaiming precision).
- `HAZARD_PROXIMITY_HEIGHT_RATIO` (bounding-box height as a proximity
  proxy) stands in for real distance estimation. A production system would
  want depth/distance data instead.
- The dashboard refreshes on tab-select and via the Refresh button, not
  continuously — intentional, since chart/log data changes on the order of
  seconds, not frames.
- User management (`Users` panel on the dashboard) is a basic list/add UI
  over the `users` table, not an access-control system — anyone can add
  any name, nothing is actually restricted by role. Real authentication
  (hashed passwords, enforced roles) was scoped out but not built.
- There's a small amount of end-to-end latency in the native build too
  (CPU-only YOLO inference), noticeable as bounding boxes trailing slightly
  behind real movement — expected on CPU, would improve substantially on a
  GPU or an edge accelerator (e.g. Jetson).

## Suggested next steps

- Fine-tune YOLOv8n on a fog-specific dataset instead of using it out-of-the-box
- Add real authentication (hashed passwords, enforced admin/viewer roles) to the dashboard
- Replace the proximity heuristic with real distance estimation (e.g. stereo camera or monocular depth model)
- Set up an audio bridge (e.g. PulseAudio) so voice alerts work inside the Docker container, not just natively
- Deploy to actual Linux edge hardware (Raspberry Pi / Jetson) to validate camera, audio, and GUI passthrough without the Windows-specific workarounds in this README
- Deploy the CockroachDB layer to CockroachDB Cloud's free tier for a fully cloud-hosted demo
