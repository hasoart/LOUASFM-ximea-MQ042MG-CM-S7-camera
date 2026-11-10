# Working on LOUASFM XIMEA camera

This is the independent XIMEA fork of `LOUASFM-balser-acA2500-14gm-camera`,
derived from local Basler commit `f651ea4`; public history excludes legacy/vendor
artifacts. Preserve the sibling Basler program and
ThuliumBB unchanged. The new target, identified from the user's product link,
is XIMEA **MQ042MG-CM-S7**, xiQ USB3, CMOSIS CMV4000 global shutter, mono.

## Target and boundaries

- Windows x64 / Python 3.11 is the hardware target; Linux uses the same code and
  has a camera-free demo. Use this fork's own `.venv` and requirements files.
- Use the manufacturer's xiAPI Python module from the installed XIMEA SDK,
  with explicit setup for the venv. Do not silently install arbitrary PyPI
  repackagings or mix a Python wrapper with unrelated native libraries.
- Camera transport is USB3: no camera IP, ForceIP, pylon, or GigE parameters in
  the active UI or installation instructions. The BeagleBone IP/UDP remain.
- Scope remains camera viewing, settings, snapshots, recording, ROI/profiles and
  board monitoring. Old scanners/atom calibration stay in the original local repository.
  `legacy/` and binary SDKs are excluded from the public repository.
- Download references from official XIMEA sites and preserve attribution,
  source URLs and checksums. SDK/driver installation on the operator's system
  is explicit and documented, not performed by the application.

## Hardware and data contracts

- Discover by device info without opening/altering acquisition; select by serial.
  All SDK operations belong to the one acquisition worker.
- xiAPI uses `exposure` (integer microseconds), `gain` (dB), `imgdataformat`,
  `trigger_selector=XI_TRG_SEL_FRAME_START`, selected GPI + `XI_GPI_TRIGGER`,
  rising/falling/software trigger source. Query parameter min/max/inc; do not
  assume GenICam names. Only status XI_TIMEOUT is normal while waiting.
- Sensor ADC is 10 bit for this model; MONO16/RAW16 is a uint16 container, not
  evidence of 16 bit sensor precision. Preserve native pixel codes and metadata.
- Copy image data before another get_image/close; use FIFO (`recent_frame=0`),
  detect frame-number gaps during one uninterrupted start where supported, and
  stop recording explicitly on incomplete frames, dropped frames or disk errors.
- Do not assume Basler's 6-pin Hirose wiring. S7 has a different Binder/M5 I/O
  connector; verify the exact S7 manual, voltage/current and pin numbering.
- Binning/downsampling, frame rate, HDR, bit depth and correction settings are
  camera-specific. Unsupported requested features must produce a clear error.
- USB3, port/controller bandwidth, power and disk throughput need real validation.
  Demo/fake SDK tests are not physical-camera or Windows validation.

## Architecture and verification

Keep drivers, storage, analysis and UDP parser independent of Qt. The GUI uses
signals and a bounded latest-frame slot; accepted recording jobs drain on exit.
Persist validated settings atomically, preserve backup, never overwrite corrupt
JSON silently. UDP 9998 is monitoring metadata; HTTP 8081 starts the ThuliumBB
web app. Never imply exact frame/cycle association from asynchronous UDP.

Run `.venv/bin/python -m pytest`, `.venv/bin/ruff check louasfm_camera tests scripts`,
compilation and a Linux GUI smoke test after relevant code changes. Test xiAPI
with a strict fake following the official wrapper as well as an installed native
SDK if available; keep hardware limitations explicit. Keep Russian README,
START_HERE, CAMERA, SDK installation and TESTING current. Commit tested steps.
Do not commit venvs, SDK binaries, runtime state, captured images or logs.
