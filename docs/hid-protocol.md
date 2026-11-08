# EPOS Gaming Suite - HID Protocol Documentation

**Version:** 1.12.2.1185
**Analysis Date:** 2026-10-11

---

## 1. Device Identification

### 1.1 USB HID Devices

| Device | VID (hex) | VID (dec) | PID (hex) | PID (dec) | Adapter |
|--------|-----------|-----------|-----------|-----------|---------|
| Sennheiser GSP 670 | 0x1395 | 5013 | 0x0300 | 768 | Capricorn |
| GSX 300 | 0x1395 | 5013 | 0x0152 | 338 | Boston |
| GSX 1000 II | 0x1395 | 5013 | 0x00B1 | 177 | Boston |
| EPOS S6 | 0x1395 | 5013 | 0x0601 | 1537 | CVideo |
| EPOS GTW 270 | 0x1395 | 5013 | 0x009E | 158 | Capricorn |
| GSA 70 | 0x1395 | 5013 | 0x0080 | 128 | Capricorn |

**Note:** All EPOS gaming devices share VID 0x1395 (Sennheiser).

### 1.2 Device Types

| Type | Description |
|------|-------------|
| WiredUSB | Direct USB connection |
| Wireless BT | Bluetooth connection |

---

## 2. CxAudioHidDll32.dll Analysis

### 2.1 DLL Information

- **File:** CxAudioHidDll32.dll
- **Size:** 1,692,672 bytes
- **Build:** Visual Studio 2010, August 9, 2017
- **Purpose:** HID interface to Conexant CX20805 audio processor

### 2.2 Exported Functions

#### Device Connection (14 functions)

| Function | Ordinal | Description |
|----------|---------|-------------|
| CxAudioHidCloseConnection | 5 | Close HID connection |
| CxAudioHidConnectedDevice | 6 | Get connected device info |
| CxAudioHidDevConnect | 7 | Connect to device |
| CxAudioHidDevConnectByPatchFile | 8 | Connect using patch file |
| CxAudioHidDevConnectByPnpId | 9 | Connect by PnP ID |
| CxAudioHidDevConnectToDevice | 10 | Connect directly |
| CxAudioHidDevDisconnect | 11 | Disconnect device |
| CxAudioHidEnumerate | 12 | Enumerate HID devices |
| CxAudioHidGetInputReport | 13 | Get input report |
| CxAudioHidGetLibVersionStringAscii | 14 | Get library version |
| CxAudioHidGetMutexNameAscii | 15 | Get mutex name (ASCII) |
| CxAudioHidGetMutexNameUnicode | 16 | Get mutex name (Unicode) |
| CxAudioHidIsDeviceConnected | 19 | Check if device connected |
| CxAudioHidOpenConnection | 20 | Open HID connection |

#### ICxAudioHidDev Interface (35 functions)

| Category | Functions |
|----------|-----------|
| Device Info | GetChipCode, GetChipVersion, GetDescriptionString, GetDevicePath, GetEepromCustomInfo, GetFirmwareVersion, GetIndexedString, GetInfo, GetManufacturerString, GetPatchVersion, GetProductString, GetSerialNumberString, DeviceReset |
| EEPROM | ContentsOperation, GetSize, Patch, PrepareForPatch, Read, ReadAsciiString, ReadPointer, ReadSerialNumber, ReadUnicodeString, Write, WriteSerialNumber, WriteUnicodeStringViaPointer |
| Memory | MemoryFill, MemoryOperation, MemoryPatch, MemoryPatchCheckFile, MemoryRead, MemoryWrite, IsMemoryWritable |
| Registers | RegisterBitFieldOperation, RegisterClearBit, RegisterReadBit, RegisterReadBitFieldInByte, RegisterReadByte, RegisterReadWord, RegisterSetBit, RegisterWriteBit, RegisterWriteBitFieldInByte, RegisterWriteByte, RegisterWriteWord, RegistersRead, RegistersWrite |
| I/O | GetInputReport, ReadInputReport, WriteOutputReport, SetIOCallbackRoutine, SetPatchCallbackRoutine |
| Property | PropertyGet |

---

## 3. HID Report Format

### 3.1 HID.DLL Functions Used

| Function | Purpose |
|---------|---------|
| HidD_GetSerialNumberString | Get device serial number |
| HidD_GetProductString | Get product name |
| HidD_GetManufacturerString | Get manufacturer (EPOS) |
| HidD_GetAttributes | Get HID attributes (VID/PID) |
| HidD_GetPreparsedData | Get preparsed data |
| HidP_GetCaps | Get HID capability codes |
| HidD_GetInputReport | Read input report |
| HidD_GetFeature | Get feature report |
| HidD_SetFeature | Set feature report |

### 3.2 Report Types

Based on CxAudioHidDll32.dll exports, the following HID reports are used:

#### Input Reports (Device → Host)
- **Audio Status:** Volume, mute state, battery level
- **Microphone Levels:** Mic FFT levels, input volume
- **Device Status:** Connection state, firmware version
- **EQ Data:** Current EQ band values

#### Output Reports (Host → Device)
- **Volume Control:** Set speaker volume, mute
- **Microphone Control:** Mic mute, gain
- **EQ Settings:** All 9 EQ band values
- **Device Commands:** Reset, enter bootloader mode

### 3.3 Feature Reports
- **Device Configuration:** Read/write device settings
- **EEPROM Access:** Read/write calibration data
- **Register Access:** Read/write chip registers

---

## 4. HID Report Structure (Inferred)

### 4.1 Report IDs

Based on standard HID audio device practices:

| Report ID | Type | Size | Description |
|-----------|------|------|-------------|
| 0x01 | Output | ~64 bytes | Volume/Mute control |
| 0x02 | Output | ~64 bytes | EQ band values |
| 0x03 | Output | ~64 bytes | Microphone settings |
| 0x04 | Input | ~64 bytes | Status response |
| 0x05 | Feature | ~64 bytes | Device info |

### 4.2 Volume/Mute Report (0x01)

```
Offset  Size  Description
0x00   1     Report ID (0x01)
0x01   1     Volume (0-100)
0x02   1     Mute (0=unmuted, 1=muted)
0x03   1     Channel (0=master, 1=left, 2=right)
0x04   60    Reserved
```

### 4.3 EQ Report (0x02)

```
Offset  Size  Description
0x00   1     Report ID (0x02)
0x01   9     EQ Band values (1 byte each, -127 to +127)
0x0A   58    Reserved
```

### 4.4 Microphone Report (0x03)

```
Offset  Size  Description
0x00   1     Report ID (0x03)
0x01   1     Mute (0=unmuted, 1=muted)
0x02   1     Gain (0-100)
0x03   9     Mic EQ bands (if supported)
0x0C   56    Reserved
```

---

## 5. Device Communication Flow

### 5.1 Connection Sequence

```
1. HID Enumeration
   └─> CxAudioHidEnumerate()
       └─> SetupDiGetClassDevs()
       └─> SetupDiEnumDeviceInterfaces()

2. Device Connection
   └─> CxAudioHidDevConnectByPnpId(VID, PID)
       └─> CreateFile() on HID device
       └─> HidD_GetAttributes() - verify VID/PID
       └─> HidD_GetPreparsedData()
       └─> HidP_GetCaps() - get report sizes

3. Get Device Info
   └─> ICxAudioHidDev_DeviceGetFirmwareVersion()
   └─> ICxAudioHidDev_DeviceGetSerialNumberString()
   └─> ICxAudioHidDev_GetChipCode()
```

### 5.2 Setting Volume

```
Host → Device:
  WriteFile(hDevice, volumeReport)
  
Report: [0x01, volume(0-100), mute(0/1), channel, ...]

Device → Host:
  ReadFile(hDevice, statusReport)
```

### 5.3 Setting EQ

```
Host → Device:
  WriteFile(hDevice, eqReport)
  
Report: [0x02, EQ1(-127 to 127), EQ2, ..., EQ9]

Device → Host:
  ReadFile(hDevice, ackReport)
```

---

## 6. Capricorn Adapter

### 6.1 Overview

The "Capricorn" is the internal codename for the Sennheiser/EPOS audio processor (Conexant CX20805 based).

### 6.2 Capricorn Features

| Feature | Description |
|---------|-------------|
| Speaker EQ | 9-band parametric EQ |
| Microphone EQ | 9-band parametric EQ |
| Reverb | Room reverb effect |
| Noise Gate | Adjustable threshold |
| Sidetone | Microphone monitoring |
| 3D Audio | Surround sound processing |

### 6.3 Device Info

| Property | Value |
|----------|-------|
| Chip | Conexant CX20805 |
| USB Class | Audio/MIDI |
| HID Protocol | Custom EPOS protocol |
| Audio Channels | 2 (stereo playback, mono mic) |
| Sample Rate | Up to 48kHz |

---

## 7. DFU (Device Firmware Update)

### 7.1 DFU Flow

```
1. Enter DFU Mode
   └─> hidDfuConnect()
       └─> Send DETACH command
       └─> Device reboots to bootloader

2. Transfer Firmware
   └─> hidDfuUpgrade(hDevice, firmwareData)
       └─> Send firmware chunks via HID
       └─> Device writes to flash

3. Verify and Reboot
   └─> hidDfuGetResult()
   └─> Device reboots to normal mode
```

### 7.2 ModiUpdater Integration

```
ModiUpdater.dll
├── ModiFwuCreate() → Creates firmware update instance
└── ModiFwuDestroy() → Destroys instance

Firmware update calls:
└─> HidDfu.dll (hidDfu_* functions)
    └─> HID reports to device
```

---

## 8. Register Map (Inferred)

### 8.1 Audio Registers

| Register | Access | Description |
|---------|--------|-------------|
| 0x00 | R/W | Master Volume |
| 0x01 | R/W | Left Channel Volume |
| 0x02 | R/W | Right Channel Volume |
| 0x03 | R/W | Microphone Gain |
| 0x04 | R/W | Mute Control |
| 0x05-0x0D | R/W | EQ Band 1-9 |
| 0x0E | R/W | Reverb Level |
| 0x0F | R/W | Noise Gate Threshold |

### 8.2 Device Registers

| Register | Access | Description |
|---------|--------|-------------|
| 0x80 | R | Firmware Version |
| 0x81 | R | Chip ID |
| 0x82 | R/W | Device Status |
| 0x83 | R/W | Configuration |

---

## 9. Implementation Reference

### 9.1 Linux HID Access

```cpp
// Linux HID example using hidapi
#include <hidapi.h>

// Open device
hid_device* dev = hid_open(0x1395, 0x0300, NULL);

// Set volume
unsigned char report[64] = {0x01, volume, mute, 0};
hid_write(dev, report, 64);

// Read status
unsigned char buf[64];
hid_read(dev, buf, 64);

// Close
hid_close(dev);
```

### 9.2 Qt HID Wrapper

```cpp
// EPOSHIDDevice class
class EPOSHIDDevice {
public:
    bool open(quint16 vid, quint16 pid);
    void close();
    bool setVolume(int volume, bool mute);
    bool setEQ(QList<int> bands);  // 9 bands
    bool setMicGain(int gain);
    QByteArray readStatus();
};
```

---

*Document Version: 1.0*
*Generated: 2026-10-11*
*Note: HID report formats are inferred based on DLL analysis and standard HID audio practices. Actual protocol may vary.*