# Working on LOUASFM Basler camera

## Scope and boundaries

- The original program is preserved in `legacy/` and baseline commit `f793a16`.
  Do not import its Windows DLLs, scanner modules or calibration constants in the
  new application. Atom-number calibration and automatic parameter scans are
  intentionally deferred by the user; keep their sources available.
- Supported target is Windows x64 with Python 3.11 and Basler acA2500-14gm GigE.
  Linux preview and camera support use the same code. Use this repo's `.venv`;
  install through requirements files. Do not modify the ThuliumBB repository.
- The requested folder spelling is `LOUASFM-balser-acA2500-14gm-camera`; the
  manufacturer is Basler. Keep that folder name.

## Architecture

- `cameras/` implements a small device interface, pypylon and simulated backends.
  No Qt imports in camera drivers, storage, protocol or image analysis.
- `services/` owns acquisition, ordered image writing, and UDP communication.
  Camera operations belong to one worker thread; GUI updates run on the Qt thread.
  Preview uses a bounded latest-frame slot. Recording never silently drops frames: 
  stop and report a full queue or grab failure.
- Save raw integer pixels as lossless TIFF/PNG; display contrast never changes
  stored values. Copy SDK buffers before releasing grab results.
- Settings are atomic JSON writes with validation, a previous-file backup and
  explicit errors. Never replace corrupt settings with defaults silently.
- Query GenICam node availability/ranges/increments; ace Classic uses
  ExposureTimeAbs and GainRaw. Do not assume newer ace 2 feature names.
- Use FrameStart, Timed exposure, selectable Line1/RisingEdge defaults. UDP
  events are monitoring metadata, not precise exposure triggers. Do not infer
  guaranteed frame/cycle association from asynchronous UDP delivery.
- Current ThuliumBB protocol: UDP 9998, Hi/Close commands, messages prefixed
  Pulses, Channel_names, Channel_links, First_edge, Cycle_finished and Close.
  Port 8081 is HTTP. Leave BeagleBone outputs/settings untouched in client tests.
- Network readdressing is explicit, temporary ForceIP while disconnected; never
  silently change the host network or persist a camera IP.

## Verification

Run `.venv/bin/python -m pytest` and `.venv/bin/ruff check louasfm_camera tests`.
Use `QT_QPA_PLATFORM=offscreen` for headless Qt checks and Basler's
`PYLON_CAMEMU=1` for SDK emulator tests. Document limits: emulator success is
not a real GigE/camera/wiring measurement, nor a Windows execution test.
Keep requirements reproducible, Russian operator documentation up to date, and
make meaningful tested Git checkpoints. Do not commit `.venv`, runtime config,
images, logs or old vendor binaries.
