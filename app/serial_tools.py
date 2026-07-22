from __future__ import annotations

from dataclasses import dataclass

try:
    from PyQt6.QtSerialPort import QSerialPortInfo
except ImportError:
    QSerialPortInfo = None


@dataclass(frozen=True)
class SerialDevice:
    port: str
    label: str


def scan_serial_ports() -> list[SerialDevice]:
    if QSerialPortInfo is None:
        return []
    devices: list[SerialDevice] = []
    for info in QSerialPortInfo.availablePorts():
        description = info.description() or "串口设备"
        manufacturer = info.manufacturer()
        details = " / ".join(part for part in (description, manufacturer) if part)
        devices.append(SerialDevice(info.portName(), f"{info.portName()} - {details}"))
    return sorted(devices, key=lambda item: item.port)
