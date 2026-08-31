"""Local machine vitals: CPU, memory, disk, network, temperature, uptime.

Everything here is read from the running kernel, so it is cheap enough to poll
every few seconds. The sparkline history is kept on this side rather than in the
browser so it survives a page reload and is shared by every viewer.
"""
import re
import shutil
import subprocess
import threading
import time
from collections import deque

try:  # psutil is a hard requirement, but a missing dep must degrade, not crash
    import psutil
except ImportError:  # pragma: no cover - exercised only on a broken install
    psutil = None

HISTORY_WINDOW = 600   # seconds of sparkline history (10 minutes)
MAX_SAMPLES = 400      # hard bound, even if something polls faster than expected

TEMP_WARM = 70.0
TEMP_HOT = 85.0

# Preferred temperature sources, best first. coretemp/k10temp are the real CPU
# package sensors; acpitz is a motherboard zone and only a last resort.
CHIP_PRIORITY = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz")
LABEL_PRIORITY = ("package id 0", "tctl", "tdie", "cpu")

# Virtual and container interfaces are not "the network" for a desktop readout.
SKIP_NIC_PREFIXES = ("lo", "docker", "veth", "br-", "virbr", "tun", "tap")

_SENSORS_LINE = re.compile(
    r"^\s*(?P<label>[A-Za-z0-9 ._+-]+?)\s*:\s*\+?(?P<value>-?\d+(?:\.\d+)?)\s*.?C\b"
)


class SystemError(RuntimeError):
    """Raised when the machine's vitals cannot be read at all."""


def temp_level(celsius):
    if celsius is None:
        return "unknown"
    if celsius >= TEMP_HOT:
        return "hot"
    if celsius >= TEMP_WARM:
        return "warm"
    return "normal"


def _interesting_nic(name):
    return not any(name.startswith(prefix) for prefix in SKIP_NIC_PREFIXES)


class SystemMonitor:
    def __init__(self):
        self._lock = threading.Lock()
        self._history = deque(maxlen=MAX_SAMPLES)
        self._last_net = None  # (monotonic, bytes_sent, bytes_recv)
        if psutil is not None:
            # cpu_percent(interval=None) is a delta since the previous call, so
            # prime it here - otherwise the very first reading is always 0%.
            try:
                psutil.cpu_percent(interval=None)
                self._last_net = self._net_counters()
            except Exception:  # noqa: BLE001 - priming is best-effort
                pass

    # ---------- temperature ----------

    def _temp_from_psutil(self):
        try:
            chips = psutil.sensors_temperatures()
        except (AttributeError, OSError):
            return None, None
        if not chips:
            return None, None

        def label_rank(entry):
            label = (entry.label or "").lower()
            for index, wanted in enumerate(LABEL_PRIORITY):
                if label.startswith(wanted):
                    return index
            return len(LABEL_PRIORITY)

        for chip in CHIP_PRIORITY:
            entries = [e for e in chips.get(chip, []) if e.current]
            if not entries:
                continue
            best = min(entries, key=label_rank)
            return round(float(best.current), 1), chip
        # Unknown chip name: fall back to the hottest reading we can see.
        every = [e for group in chips.values() for e in group if e.current]
        if every:
            hottest = max(every, key=lambda e: e.current)
            return round(float(hottest.current), 1), "sensors"
        return None, None

    def _temp_from_cli(self):
        """Parse `sensors` output when psutil has no reading of its own."""
        if not shutil.which("sensors"):
            return None, None
        try:
            proc = subprocess.run(
                ["sensors"], capture_output=True, text=True, timeout=4, check=False
            )
        except (OSError, subprocess.SubprocessError):
            return None, None
        # lm-sensors prints per-feature errors to stderr but still emits usable
        # readings on stdout, so a non-zero exit code is not disqualifying.
        best = None
        cores = []
        for line in (proc.stdout or "").splitlines():
            match = _SENSORS_LINE.match(line)
            if not match:
                continue
            label = match.group("label").strip().lower()
            value = float(match.group("value"))
            if label.startswith(("package id", "tctl", "tdie")):
                best = value
                break
            if label.startswith("core "):
                cores.append(value)
        if best is None and cores:
            best = max(cores)
        return (round(best, 1), "lm-sensors") if best is not None else (None, None)

    def _temperature(self):
        value, source = self._temp_from_psutil()
        if value is None:
            value, source = self._temp_from_cli()
        return value, source

    # ---------- network ----------

    @staticmethod
    def _net_counters():
        sent = recv = 0
        for name, counters in psutil.net_io_counters(pernic=True).items():
            if not _interesting_nic(name):
                continue
            sent += counters.bytes_sent
            recv += counters.bytes_recv
        return time.monotonic(), sent, recv

    def _net_rates(self):
        """Bytes/sec since the previous sample, or None on the first call."""
        try:
            now, sent, recv = self._net_counters()
        except Exception:  # noqa: BLE001 - a missing NIC must not sink the card
            return None, None
        previous = self._last_net
        self._last_net = (now, sent, recv)
        if previous is None:
            return None, None
        elapsed = now - previous[0]
        if elapsed <= 0:
            return None, None
        # A NIC that went away (or a counter that wrapped) reads as a negative
        # delta; report 0 rather than a nonsense spike.
        up = max(0.0, (sent - previous[1]) / elapsed)
        down = max(0.0, (recv - previous[2]) / elapsed)
        return round(up, 1), round(down, 1)

    # ---------- history ----------

    def _record(self, cpu, up, down):
        now = time.time()
        with self._lock:
            self._history.append(
                {
                    "t": round(now, 1),
                    "cpu": cpu,
                    "up": up or 0.0,
                    "down": down or 0.0,
                }
            )
            cutoff = now - HISTORY_WINDOW
            while self._history and self._history[0]["t"] < cutoff:
                self._history.popleft()
            return list(self._history)

    # ---------- snapshot ----------

    def snapshot(self):
        if psutil is None:
            raise SystemError(
                "psutil is not installed - run "
                "backend/venv/bin/pip install -r backend/requirements.txt"
            )
        try:
            cpu = round(float(psutil.cpu_percent(interval=None)), 1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            boot = psutil.boot_time()
        except Exception as exc:  # noqa: BLE001
            raise SystemError(f"Could not read machine vitals: {exc}") from exc

        up, down = self._net_rates()
        temperature, temp_source = self._temperature()
        history = self._record(cpu, up, down)

        try:
            load1, load5, load15 = psutil.getloadavg()
        except (AttributeError, OSError):
            load1 = load5 = load15 = None

        try:
            cores = psutil.cpu_count(logical=True) or 0
        except Exception:  # noqa: BLE001
            cores = 0

        uptime = max(0.0, time.time() - boot)

        return {
            "available": True,
            "cpu": {
                "percent": cpu,
                "cores": cores,
                "load": None
                if load1 is None
                else [round(load1, 2), round(load5, 2), round(load15, 2)],
                # A load average only means something relative to core count.
                "load_per_core": None
                if load1 is None or not cores
                else round(load1 / cores, 2),
            },
            "memory": {
                "used": memory.total - memory.available,
                "total": memory.total,
                "percent": round(
                    (memory.total - memory.available) / memory.total * 100, 1
                )
                if memory.total
                else 0.0,
            },
            "disk": {
                "used": disk.used,
                "total": disk.total,
                "percent": round(disk.percent, 1),
                "mount": "/",
            },
            "network": {
                # null (not 0) on the first sample: we have no interval to
                # divide by yet, and "0 B/s" would be a lie.
                "up": up,
                "down": down,
            },
            "temperature": {
                "celsius": temperature,
                "source": temp_source,
                "level": temp_level(temperature),
                "warm_at": TEMP_WARM,
                "hot_at": TEMP_HOT,
            },
            "uptime_seconds": round(uptime),
            "boot_time": boot,
            "history": history,
            "history_window": HISTORY_WINDOW,
        }
