#!/usr/bin/env python3
"""
Mock HID interface for testing GSP 670 device interactions.

Provides a fake HID device that responds to SECOM commands with
verifiable responses, without requiring actual hardware.
"""

import struct
from typing import Optional, List, Tuple
from dataclasses import dataclass, field

from gsp670.protocol import Frame, Opcode


@dataclass
class HIDReport:
    """A single HID report (input or output)."""
    report_id: int
    data: bytes
    
    def to_bytes(self) -> bytes:
        return bytes([self.report_id]) + self.data
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'HIDReport':
        return cls(report_id=data[0], data=data[1:])


@dataclass
class SecomResponse:
    """Expected SECOM response to a command."""
    marker: bytes  # 2 bytes
    opcode: int
    payload: bytes


class MockHIDDevice:
    """
    Mock HID device for testing.
    
    Simulates a GSA 70 dongle responding to SECOM commands.
    """
    
    def __init__(self):
        self._input_reports: List[HIDReport] = []
        self._output_reports: List[HIDReport] = []
        self._last_output: Optional[HIDReport] = None
        self._responses: dict = {}
        self._connected = True
        
        # Set up default responses
        self._setup_default_responses()
    
    def _setup_default_responses(self):
        """Set up default responses for common commands."""
        # Get firmware version (0x00) -> ACK
        self.add_response(
            expected_opcode=0x00,
            marker=b'\x05\x30',
            payload=b'\x01\x00\x03\x00\x0e\x00\x02\x00'
        )
        
        # Get serial number (0x01) -> data
        self.add_response(
            expected_opcode=0x01,
            marker=b'\x04\x00',
            payload=b'TEST\x00' + b'\x00' * 31
        )
        
        # Get device name (0x02) -> data
        self.add_response(
            expected_opcode=0x02,
            marker=b'\x04\x00',
            payload=b'EPOS GSA 70\x00'.ljust(20, b'\x00')
        )
        
        # Get battery (0x0e) -> ACK (battery is polled, not event)
        self.add_response(
            expected_opcode=0x0e,
            marker=b'\x05\x30',
            payload=b'\x12\x00\x03\x00\x50\x00'  # 80% battery
        )
        
        # Get sidetone (0x10) -> ACK
        self.add_response(
            expected_opcode=0x10,
            marker=b'\x05\x30',
            payload=b'\x0a\x00\x0c\x00\x32\x00'  # 50 sidetone
        )
        
        # Set sidetone (0x11) -> ACK
        self.add_response(
            expected_opcode=0x11,
            marker=b'\x05\x30',
            payload=b'\x0a\x00\x0b\x00'  # echo
        )
        
        # Set noise reduction (0x12) -> ACK
        self.add_response(
            expected_opcode=0x12,
            marker=b'\x05\x30',
            payload=b'\x0a\x00\x11\x00'
        )
        
        # Get noise reduction (0x13) -> ACK
        self.add_response(
            expected_opcode=0x13,
            marker=b'\x05\x30',
            payload=b'\x0a\x00\x12\x00\x01\x00'  # level 1
        )
        
        # Get sub-devices (0x04) -> sub-dev reply
        self.add_response(
            expected_opcode=0x04,
            marker=b'\x04\x00',
            payload=b'\x04\x00\x04\x00\x00\x00'  # 0 devices
        )
        
        # Set auto power off (0x1a) -> ACK
        self.add_response(
            expected_opcode=0x1a,
            marker=b'\x05\x30',
            payload=b'\x01\x00\x1f\x00'
        )
        
        # Get auto power off (0x1b) -> ACK
        self.add_response(
            expected_opcode=0x1b,
            marker=b'\x05\x30',
            payload=b'\x01\x00\x20\x00\x1e\x00'  # 30 minutes
        )
    
    def add_response(self, expected_opcode: int, marker: bytes, payload: bytes):
        """Add an expected response for a given opcode."""
        self._responses[expected_opcode] = (marker, payload)
    
    def write(self, data: bytes) -> int:
        """
        Simulate HID write (output report).
        
        Returns the number of bytes written.
        """
        if not self._connected:
            raise IOError("Device not connected")
        
        report = HIDReport.from_bytes(data)
        self._output_reports.append(report)
        self._last_output = report
        
        # Parse the command and generate response
        self._handle_command(report)
        
        return len(data)
    
    def _handle_command(self, report: HIDReport):
        """Handle incoming command and queue response."""
        if len(report.data) < 12:
            return
        
        # Parse SECOM frame (report.data starts at byte 1 of the full frame)
        # Full frame: [0]=report_id, [1..4]=sync, [5..6]=marker, [7..8]=opcode, [9..10]=length
        # So in report.data: [0..3]=sync, [4..5]=marker, [6..7]=opcode, [8..9]=length
        opcode = int.from_bytes(report.data[6:8], 'little')
        
        if opcode in self._responses:
            marker, payload = self._responses[opcode]
            
            # Build response frame
            response = HIDReport(
                report_id=0x01,
                data=b'\xeb\xfe\x01\x00' + marker + struct.pack('<H', opcode) + struct.pack('<H', len(payload)) + b'\x00' + payload
            )
            self._input_reports.append(response)
    
    def read(self, timeout_ms: int = 0) -> Optional[bytes]:
        """
        Simulate HID read (input report).
        
        Returns a report bytes or None if no data available.
        """
        if not self._connected:
            raise IOError("Device not connected")
        
        if self._input_reports:
            return self._input_reports.pop(0).to_bytes()
        return None
    
    def get_last_output(self) -> Optional[HIDReport]:
        """Get the last output report sent."""
        return self._last_output
    
    def get_output_count(self) -> int:
        """Get number of output reports sent."""
        return len(self._output_reports)
    
    def connect(self):
        """Simulate device connection."""
        self._connected = True
    
    def disconnect(self):
        """Simulate device disconnection."""
        self._connected = False
    
    def is_connected(self) -> bool:
        """Check if device is connected."""
        return self._connected


class MockHIDContext:
    """
    Context manager for mock HID device.
    
    Usage:
        with MockHIDContext() as mock:
            device = GSA70Device(mock=True)
            device.open()
            # ... test code ...
    """
    
    def __init__(self):
        self.device = MockHIDDevice()
    
    def __enter__(self):
        return self.device
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.device.disconnect()
        return False
