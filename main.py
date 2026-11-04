"""Compatibility launcher: python main.py or python -m louasfm_camera."""
from louasfm_camera.app import main
if __name__ == "__main__":
    raise SystemExit(main())
