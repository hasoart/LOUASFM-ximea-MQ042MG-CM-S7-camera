"""Basler pypylon backend, including ace Classic's older GenICam node names."""
from dataclasses import replace
import ipaddress
import math

from ..models import CameraSettings, Frame


def load_sdk():
    try:
        from pypylon import genicam, pylon
    except ImportError as error:
        raise RuntimeError("Не установлен pypylon. Установите requirements.txt в venv.") from error
    return pylon, genicam


class BaslerCamera:
    def __init__(self):
        self.pylon, self.genicam = load_sdk()
        self.factory = self.pylon.TlFactory.GetInstance()
        self.camera = None
        self.settings = None
        self.info = {}
        self.converter = None

    @staticmethod
    def _info(device):
        result = {"serial": device.GetSerialNumber(), "model": device.GetModelName()}
        for key, method in (("ip", "GetIpAddress"), ("mac", "GetMacAddress"), ("interface", "GetInterfaceID")):
            try:
                result[key] = getattr(device, method)()
            except Exception:  # Optional metadata is absent on some transport layers.
                result[key] = ""
        try:
            ipaddress.IPv4Address(result["ip"])
        except ValueError:
            result["ip"] = ""
        return result

    def discover(self):
        return [self._info(device) for device in self.factory.EnumerateDevices()]

    def open(self, serial="", ip=""):
        if self.camera is not None:
            raise RuntimeError("Камера уже подключена")
        if ip:
            ipaddress.IPv4Address(ip)
        devices = [d for d in self.factory.EnumerateDevices()
                   if (not serial or d.GetSerialNumber() == serial)
                   and (not ip or self._info(d)["ip"] == ip)]
        if not devices and ip and not serial:
            descriptor = self.pylon.DeviceInfo()
            descriptor.SetDeviceClass("BaslerGigE")
            descriptor.SetIpAddress(ip)
            devices = [descriptor]
        if not devices:
            raise RuntimeError("Камера не найдена. Проверьте питание, IP/подсеть и pylon Viewer.")
        if len(devices) > 1:
            raise RuntimeError("Найдено несколько камер: выберите серийный номер или IP")
        camera = self.pylon.InstantCamera(self.factory.CreateDevice(devices[0]))
        try:
            camera.Open()
            camera.MaxNumBuffer = 16
        except Exception:
            camera.Close()
            raise
        self.camera = camera
        self.info = self._info(camera.GetDeviceInfo())
        return self.info.copy()

    def _node(self, *names, required=True):
        for name in names:
            try:
                node = self.camera.GetNodeMap().GetNode(name)
            except self.genicam.LogicalErrorException:
                continue
            if node is not None and self.genicam.IsAvailable(node):
                return node
        if required:
            raise RuntimeError("Камера не поддерживает параметр " + "/".join(names))
        return None

    def _set(self, names, value, optional=False):
        if isinstance(names, str):
            names = (names,)
        node = self._node(*names, required=not optional)
        if node is None or not self.genicam.IsWritable(node):
            if optional:
                return None
            raise RuntimeError(f"Параметр {'/'.join(names)} недоступен для записи")
        node.SetValue(value)
        return node.GetValue()

    def _number(self, names, value):
        node = self._node(*names) if isinstance(names, tuple) else self._node(names)
        if not self.genicam.IsWritable(node):
            raise RuntimeError(f"{node.GetNode().GetName()}: параметр недоступен для записи")
        minimum, maximum = node.GetMin(), node.GetMax()
        if not minimum <= value <= maximum:
            raise ValueError(f"{node.GetNode().GetName()}: {value} вне диапазона {minimum}…{maximum}")
        if isinstance(minimum, int):
            increment = max(1, node.GetInc())
            value = int(minimum + math.floor((value-minimum)/increment) * increment)
        node.SetValue(value)
        return node.GetValue()

    def _choices(self, name):
        node = self._node(name, required=False)
        if node is None:
            return []
        return [entry.GetSymbolic() for entry in node.GetEntries() if self.genicam.IsAvailable(entry)]

    def _range(self, *names):
        node = self._node(*names, required=False)
        if node is None:
            return {}
        result = {"node": node.GetNode().GetName(), "min": node.GetMin(), "max": node.GetMax()}
        if isinstance(result["min"], int):
            result["inc"] = node.GetInc()
        return result

    def configure(self, settings: CameraSettings):
        settings.validate()
        if self.camera is None or self.camera.IsGrabbing():
            raise RuntimeError("Остановите захват перед изменением настроек")
        # Disable previous acquisition/frame trigger modes, including camera user sets.
        selectors = self._choices("TriggerSelector")
        for selector in selectors:
            self._set("TriggerSelector", selector)
            self._set("TriggerMode", "Off", optional=True)
        self._set("AcquisitionMode", "Continuous")
        self._set("ExposureAuto", "Off", optional=True)
        self._set("GainAuto", "Off", optional=True)
        self._set("ExposureMode", "Timed", optional=True)
        exposure = self._number(("ExposureTime", "ExposureTimeAbs"), settings.exposure_us)
        gain = self._number(("Gain", "GainRaw"), self._node("Gain", "GainRaw").GetMin()
                            if settings.gain is None else settings.gain)
        for offset in ("OffsetX", "OffsetY"):
            self._number(offset, 0)
        # Shrink before binning to avoid a full-width ROI exceeding the new sensor width.
        for axis in ("Width", "Height"):
            self._number(axis, self._node(axis).GetMin())
        for axis in ("BinningHorizontal", "BinningVertical"):
            node = self._node(axis, required=False)
            if node is not None:
                self._number(axis, settings.binning)
            elif settings.binning != 1:
                raise ValueError("Эта камера не поддерживает выбранный binning")
        self._set("PixelFormat", settings.pixel_format)
        width = self._number("Width", settings.width or self._node("Width").GetMax())
        height = self._number("Height", settings.height or self._node("Height").GetMax())
        offset_x = self._number("OffsetX", settings.offset_x)
        offset_y = self._number("OffsetY", settings.offset_y)
        if self._node("GevSCPSPacketSize", required=False) is not None:
            packet = self._number("GevSCPSPacketSize", settings.packet_size)
            delay = self._number("GevSCPD", settings.inter_packet_delay)
        else:
            packet, delay = settings.packet_size, settings.inter_packet_delay
        rate_node = self._node("AcquisitionFrameRateEnable", required=False)
        if rate_node is not None:
            self._set("AcquisitionFrameRateEnable", settings.frame_rate > 0)
        if settings.frame_rate:
            if rate_node is None:
                raise ValueError("Эта камера не поддерживает ограничитель FPS")
            self._number(("AcquisitionFrameRate", "AcquisitionFrameRateAbs"), settings.frame_rate)
        if "FrameStart" not in selectors:
            raise ValueError("Камера не поддерживает FrameStart")
        self._set("TriggerSelector", "FrameStart")
        sources = self._choices("TriggerSource")
        if settings.trigger_mode != "free":
            source = "Software" if settings.trigger_mode == "software" else settings.trigger_source
            if source not in sources:
                raise ValueError(f"Источник {source} недоступен; доступны: {sources}")
            self._set("TriggerSource", source)
            if settings.trigger_mode == "external":
                if self._node("LineSelector", required=False) is not None:
                    self._set("LineSelector", source)
                    self._set("LineMode", "Input", optional=True)
                    self._set("LineInverter", False, optional=True)
                self._set("TriggerActivation", settings.trigger_activation)
            self._set("TriggerMode", "On")
        else:
            self._set("TriggerMode", "Off")
        self.converter = None
        if "Packed" in settings.pixel_format or settings.pixel_format.endswith("p"):
            self.converter = self.pylon.ImageFormatConverter()
            self.converter.OutputPixelFormat = self.pylon.PixelType_Mono16
            self.converter.OutputBitAlignment = self.pylon.OutputBitAlignment_LsbAligned
        self.settings = replace(settings, exposure_us=exposure, gain=gain, width=width, height=height,
                                offset_x=offset_x, offset_y=offset_y, packet_size=packet, inter_packet_delay=delay)
        capabilities = {"pixel_formats": [p for p in self._choices("PixelFormat") if p.startswith("Mono")],
                        "trigger_sources": [s for s in sources if s.startswith("Line")],
                        "exposure_us": self._range("ExposureTime", "ExposureTimeAbs"),
                        "gain": self._range("Gain", "GainRaw"),
                        "width": self._range("Width"), "height": self._range("Height"),
                        "binning": self._range("BinningHorizontal"),
                        "gain_node": self._node("Gain", "GainRaw").GetNode().GetName()}
        return self.settings, capabilities

    def start(self):
        self.camera.StartGrabbing(self.pylon.GrabStrategy_OneByOne)

    def read(self, timeout_ms=100):
        result = self.camera.RetrieveResult(timeout_ms, self.pylon.TimeoutHandling_Return)
        if result is None or not result.IsValid():
            return None  # Waiting for the next physical trigger is normal.
        try:
            if not result.GrabSucceeded():
                raise RuntimeError(f"Неполный кадр: {result.GetErrorCode()} {result.GetErrorDescription()}")
            image = self.converter.Convert(result) if self.converter else result
            return Frame(image.Array.copy(), int(result.GetBlockID()), int(result.GetTimeStamp()),
                         metadata={"backend": "basler", "camera": self.info.copy()})
        finally:
            result.Release()

    def trigger(self):
        if self.settings.trigger_mode != "software":
            raise RuntimeError("Для команды Software нужен программный режим триггера")
        # pypylon exposes WaitForFrameTriggerReady, but not C++'s CanWait... .
        # Older ace cameras may not expose the acquisition-status feature.
        if "FrameTriggerWait" in self._choices("AcquisitionStatusSelector"):
            self.camera.WaitForFrameTriggerReady(1000, self.pylon.TimeoutHandling_ThrowException)
        self.camera.ExecuteSoftwareTrigger()

    def stop(self):
        if self.camera is not None and self.camera.IsGrabbing():
            self.camera.StopGrabbing()

    def close(self):
        if self.camera is not None:
            try:
                self.stop()
            finally:
                self.camera.Close()
                self.camera = None

    def force_ip(self, mac, address, mask, gateway="0.0.0.0"):
        if self.camera is not None:
            raise RuntimeError("Сначала отключите камеру")
        address = str(ipaddress.IPv4Address(address))
        gateway = str(ipaddress.IPv4Address(gateway))
        network = ipaddress.IPv4Network(f"{address}/{mask}", strict=False)
        if str(network.netmask) != mask or ipaddress.IPv4Address(address) in (network.network_address, network.broadcast_address):
            raise ValueError("Проверьте адрес и маску сети")
        compact_mac = mac.replace(":", "").replace("-", "")
        if len(compact_mac) != 12 or any(c not in "0123456789abcdefABCDEF" for c in compact_mac):
            raise ValueError("Укажите MAC камеры: 12 шестнадцатеричных цифр")
        transport = self.factory.CreateTl("BaslerGigE")
        transport.ForceIp(compact_mac, address, mask, gateway)
        return "Временный IP назначен. Повторите поиск; настройки сетевой карты ПК не менялись."
