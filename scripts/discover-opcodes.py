#!/usr/bin/env python3
"""Extended opcode discovery for GSP 670 - Focused scan"""
import sys, time
sys.path.insert(0, 'src')
from gsp670.protocol import frame, classify, VID, PID_GSA70, PID_GSP670, USAGE_PAGE
import hid

def probe_device(vid, pid, name, opcode_ranges):
    """Probe device for opcode responses"""
    results = {'ack': [], 'nak': [], 'other': [], 'error': []}
    device_found = False
    
    for d in hid.enumerate(vid, pid):
        if d['usage_page'] == USAGE_PAGE:
            device_found = True
            dev = hid.device()
            dev.open_path(d['path'])
            dev.set_nonblocking(True)
            print(f"Probing {name} at {d['path'].decode()}")
            
            total_opcodes = sum(end - start + 1 for start, end in opcode_ranges)
            print(f"Probing {total_opcodes} opcodes...")
            
            for start, end in opcode_ranges:
                for opcode in range(start, end + 1):
                    try:
                        req = frame(opcode, bytes([0x01, 0x00]))
                        dev.write(req)
                        time.sleep(0.02)  # 20ms per opcode
                        r = dev.read(256, 40)
                        if r and len(r) >= 13:
                            c = classify(bytes(r))
                            kind = c.kind
                            if kind == 'ack':
                                results['ack'].append((opcode, c.payload if c.payload else b'empty'))
                            elif kind == 'nak':
                                results['nak'].append(opcode)
                            else:
                                results['other'].append((opcode, kind, c.payload))
                    except Exception as e:
                        results['error'].append((opcode, str(e)))
            
            dev.close()
            break
    
    if not device_found:
        print(f"Device {name} ({vid:04x}:{pid:04x}) not found")
    
    return results

# Focused probe ranges - limited to most likely opcode ranges
ranges = [
    (0x4000, 0x40FF),  # Main control range
    (0x4F00, 0x4F1F),  # FWU family (known)
]

print("=== GSP 670 Opcode Discovery ===")

print("\n=== Probing Headset (0x008A) ===")
headset_results = probe_device(VID, PID_GSP670, "GSP 670 Headset", ranges)

print("\n=== Probing Dongle (0x0300) ===")
dongle_results = probe_device(VID, PID_GSA70, "GSA 70 Dongle", ranges)

print("\n" + "=" * 60)
print("ACK Results (opcodes that responded with data)")
print("=" * 60)

for name, results in [("Headset", headset_results), ("Dongle", dongle_results)]:
    if results['ack']:
        print(f"\n{name}:")
        for opcode, payload in results['ack']:
            print(f"  0x{opcode:04X}: {payload.hex() if payload else 'empty'}")
    else:
        print(f"\n{name}: No ACK responses")

print("\n" + "=" * 60)
print("Summary")
print("=" * 60)
for name, results in [("Headset", headset_results), ("Dongle", dongle_results)]:
    print(f"{name}: ACK={len(results['ack'])}, NAK={len(results['nak'])}, Other={len(results['other'])}, Error={len(results['error'])}")

# Save results for analysis
import json
all_results = {
    'headset': headset_results,
    'dongle': dongle_results,
    'ranges_probed': ranges,
    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
}
with open('opcode-discovery-results.json', 'w') as f:
    serializable = {}
    for key, results in all_results.items():
        if key == 'timestamp':
            serializable[key] = results
        elif key == 'ranges_probed':
            serializable[key] = results
        else:
            serializable[key] = {
                'ack': [(op, pl.hex() if pl else 'empty') for op, pl in results['ack']],
                'nak': results['nak'],
                'other': [(op, kind, pl.hex() if pl else 'empty') for op, kind, pl in results['other']],
                'error': [(op, str(e)) for op, e in results['error']]
            }
    json.dump(serializable, f, indent=2)

print("\nResults saved to opcode-discovery-results.json")