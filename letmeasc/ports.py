from __future__ import annotations

from serial.tools import list_ports


def list_serial_ports() -> list[str]:
    return [port.device for port in list_ports.comports()]


def format_serial_ports() -> str:
    ports = list_serial_ports()
    if not ports:
        return "No serial ports detected."
    lines = ["Detected serial ports:"]
    lines.extend(f"- {port}" for port in ports)
    return "\n".join(lines)
