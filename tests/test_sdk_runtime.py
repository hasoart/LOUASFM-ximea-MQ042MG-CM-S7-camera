from pathlib import Path
import pytest
from louasfm_camera import sdk_runtime
from louasfm_camera.config import ConfigStore


def test_locate_unmodified_sdk_python_layout_with_spaces(tmp_path):
    parent = tmp_path / "SDK with spaces" / "API/Python/v3"
    (parent / "ximea").mkdir(parents=True)
    (parent / "ximea/xiapi.py").write_text("# SDK package")
    assert parent in sdk_runtime.python_package_parents(tmp_path / "SDK with spaces")
    assert parent in sdk_runtime.python_package_parents(parent)
    assert parent in sdk_runtime.python_package_parents(parent / "ximea")


def test_project_local_sdk_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(sdk_runtime, "ROOT", tmp_path)
    monkeypatch.delenv("XIMEA_SDK_ROOT", raising=False)
    monkeypatch.delenv("XI_API_DIR", raising=False)
    (tmp_path / "state").mkdir()
    sdk = tmp_path / "official SDK"
    (tmp_path / "state/ximea-sdk-path.txt").write_text(str(sdk))
    assert sdk.resolve() in sdk_runtime.configured_roots()


def test_missing_native_library_gives_actionable_error(monkeypatch):
    monkeypatch.setattr(sdk_runtime, "prepare_sdk_paths", lambda: [Path("/missing/sdk")])

    def missing(name):
        raise OSError("native library unavailable")

    monkeypatch.setattr(sdk_runtime.importlib, "import_module", missing)
    with pytest.raises(RuntimeError, match="configure_ximea_sdk.py") as error:
        sdk_runtime.load_xiapi()
    assert "--demo" in str(error.value)


def test_basler_settings_are_rejected_without_rewriting(tmp_path):
    path = tmp_path / "settings.json"
    data = '{"schema_version":1,"backend":"basler","camera":{"packet_size":1500}}'
    path.write_text(data)
    with pytest.raises(ValueError):
        ConfigStore(path).load()
    assert path.read_text() == data
