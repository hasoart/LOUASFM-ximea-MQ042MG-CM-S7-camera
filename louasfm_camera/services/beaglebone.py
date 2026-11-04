"""Read-only client of ThuliumBB's existing UDP 9998 monitoring protocol."""
from dataclasses import dataclass, field
import copy
import json
import math
import socket
import threading
import time


@dataclass
class BoardState:
    pulses: dict = field(default_factory=dict)
    names: dict = field(default_factory=dict)
    links: dict = field(default_factory=dict)
    cycles: int = 0
    first_edges: int = 0
    bad_cycle: bool = False
    last_message: str = ""
    last_received_monotonic: float = 0.0


def decode_message(packet):
    message = packet.decode("utf-8").strip()
    task, _, body = message.partition(" ")
    if task in ("Close",):
        return task, None
    if task == "First_edge":
        value = float(body)
        if not math.isfinite(value):
            raise ValueError("Некорректное время First_edge")
        return task, value
    if task not in ("Pulses", "Channel_names", "Channel_links", "Cycle_finished", "Scan_params", "DDS_data", "Initial_values"):
        return task, None
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError(f"{task}: ожидался объект JSON")
    if task == "Pulses":
        if len(data) > 512:
            raise ValueError("Слишком много каналов")
        for channel, edges in data.items():
            if not isinstance(channel, str) or not isinstance(edges, list):
                raise ValueError("Некорректный канал схемы")
            previous = -math.inf
            for edge in edges:
                if not isinstance(edge, (list, tuple)) or len(edge) != 2:
                    raise ValueError("Ожидалась пара [время, уровень]")
                if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in edge):
                    raise ValueError("Некорректные значения импульса")
                if edge[0] < previous:
                    raise ValueError("Времена импульсов должны возрастать")
                previous = edge[0]
    if task == "Cycle_finished" and (not isinstance(data.get("bad_cycle"), bool) or not isinstance(data.get("t"), (int, float))):
        raise ValueError("Некорректное сообщение Cycle_finished")
    return task, data


def trigger_edges(pulses, channel="D0", activation="RisingEdge"):
    result = []
    edges = pulses.get(channel, [])
    # In steady periodic operation the last level carries into the next cycle.
    # A forced-HIGH channel is not a new edge at t=0 on every cycle.
    previous = edges[-1][1] if edges else 0
    for timestamp, level in edges:
        if activation == "RisingEdge" and previous == 0 and level == 1:
            result.append(timestamp)
        elif activation == "FallingEdge" and previous == 1 and level == 0:
            result.append(timestamp)
        previous = level
    return result


class BoardClient:
    def __init__(self, on_message, on_status, on_error):
        self.on_message = on_message
        self.on_status = on_status
        self.on_error = on_error
        self.state = BoardState()
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.socket = None

    def connect(self, host, port):
        if self.thread is not None and self.thread.is_alive():
            raise RuntimeError("Сначала отключите BeagleBone")
        if not host.strip() or not 1 <= int(port) <= 65535:
            raise ValueError("Проверьте адрес и UDP порт")
        self.stop_event.clear()
        with self.lock:
            self.state = BoardState()
        self.thread = threading.Thread(target=self._run, args=(host, int(port)), name="beaglebone-monitor", daemon=True)
        self.thread.start()

    def _run(self, host, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket = sock
        try:
            sock.settimeout(0.25)
            sock.connect((host, port))
            sock.send(b"Hi")
            self.on_status("Ожидание ответа BeagleBone")
            waiting_since = time.monotonic()
            stale_reported = False
            while not self.stop_event.is_set():
                try:
                    packet = sock.recv(65535)  # Old client truncated schemes at 1024 bytes.
                except socket.timeout:
                    with self.lock:
                        last = self.state.last_received_monotonic
                    if time.monotonic() - (last or waiting_since) > 10 and not stale_reported:
                        self.on_status("Нет UDP сообщений >10 с: проверьте BBMain и откройте его веб-интерфейс")
                        stale_reported = True
                    continue
                try:
                    task, data = decode_message(packet)
                except (ValueError, TypeError, UnicodeError) as error:
                    self.on_error(f"Пропущен некорректный UDP пакет: {error}")
                    continue
                stale_reported = False
                if task == "Close":
                    self.on_status("BeagleBone закрыл соединение")
                    break
                with self.lock:
                    self.state.last_received_monotonic = time.monotonic()
                    self.state.last_message = task
                    if task == "Pulses":
                        self.state.pulses = data
                    elif task == "Channel_names":
                        self.state.names = data
                    elif task == "Channel_links":
                        self.state.links = data
                    elif task == "First_edge":
                        self.state.first_edges += 1
                    elif task == "Cycle_finished":
                        self.state.cycles += 1
                        self.state.bad_cycle = data["bad_cycle"]
                self.on_message(task, data)
                self.on_status("Подключён; получены UDP данные")
        except OSError as error:
            if not self.stop_event.is_set():
                self.on_error(f"BeagleBone: {error}")
        finally:
            try:
                sock.send(b"Close")
            except OSError:
                pass
            sock.close()
            self.socket = None
            self.on_status("BeagleBone отключён")

    def snapshot(self):
        with self.lock:
            return copy.deepcopy({"pulses": self.state.pulses, "channel_names": self.state.names,
                                  "cycles_observed": self.state.cycles, "first_edges_observed": self.state.first_edges,
                                  "bad_cycle_last_reported": self.state.bad_cycle,
                                  "last_message": self.state.last_message,
                                  "last_message_age_s": time.monotonic()-self.state.last_received_monotonic
                                  if self.state.last_received_monotonic else None})

    def close(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                raise RuntimeError("Поток BeagleBone не завершился")
            self.thread = None
