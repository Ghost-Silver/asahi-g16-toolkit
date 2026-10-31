# Asahi Linux G16 Reverse Engineering Toolkit & Bring-Up

[![Platform: Apple Silicon M3 / M3 Pro](https://img.shields.io/badge/Hardware-Apple%20Silicon%20G16%20(M3)-blue.svg)](#)
[![Mesa upstream compatible](https://img.shields.io/badge/Mesa-AGX%20Disassembler%20Compatible-green.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#)

A reverse engineering toolchain, automated ISA scanner, and Mesa bring-up test suite for **Apple Silicon G16 GPU microarchitecture** (powering the M3, M3 Pro, and M3 Max series Macs, such as MacBook Pro `Mac15,6`).

Developed as part of the initiative to bring full Linux support (including Arch Linux ARM + Wayland/Niri desktop) to Apple Silicon M3 hardware.

---

## 🌟 Highlights & Key Breakthroughs

1. **G16 Register Hint Encoding Discovery**:
   - In G13/G14 (Apple M1/M2), standard unhinted register operands were strictly encoded with `hint = 1`.
   - In G16 (Apple M3), Apple's compiler shifted the unhinted default to `hint = 0`. Fixing this assertion in Mesa's disassembler immediately unlocked thousands of previously failing G16 shader instructions.
2. **Indirect Jump Trio Completion (`jmp_reg`)**:
   - Discovered and defined opcode `0x54` (`1010100`), completing the indirect control flow family:
     - `call_reg` (`0x04` / `0000100`)
     - `ret` (`0x14` / `0010100`)
     - `jmp_reg` (`0x54` / `1010100`)
   - Mapped `mode` (bit 7) and `link` (bit 8) modifiers, eliminating all unexpected bitfield warnings across indirect jumps.
3. **Hardware Raytracing Accelerator (RIA2) Domain Mapping**:
   - Mapped the previously unpopulated Domain `0b011` (`0x03`), exclusive to M3 hardware:
     - `ria_bbox_test` (`0x0003`): Bounding-box BVH traversal test.
     - `ria_curve_test` (`0x1403`): Coarse curve intersection test.
     - `ria_commit` (`0x1c03`): Parallel intersection commit and BVH state update.
4. **Clean Decoding Rate Doubled**:
   - Across multi-source real-world macOS G16 driver binaries (`Archive_release.metallib`, `ds.binary.metallib.g16s-b0`), cleanly decoded instructions doubled from **10.05% to 20.18%**, and unexpected bitfield anomalies dropped by over **60%** (16.36% -> 6.23%).
5. **250 Real-World Test Vectors**:
   - Mined from native macOS G16 driver slices, 100% compliant with Mesa's upstream disassembler verification harness (`test-disasm.py`).

---

## 📂 Repository Structure

```text
asahi-g16-toolkit/
├── tools/
│   ├── extract_g16_metallib.py   # Extracts raw AGX shader code from Universal Fat / Thin Mach-O metallibs
│   └── scan_g16_opcodes.py       # Sliding-window disassembler scanner & opcode clustering engine
├── proposals/
│   └── AGX2_G16_draft.xml        # Structural XML proposal for G16 instructions in Mesa AGX2.xml
├── test/
│   └── g16_cases.txt             # 250 verified real-world G16 test cases for Mesa test-disasm.py
├── patches/
│   ├── 0001-asahi-isa-Initial-Apple-G16-bring-up-support.patch
│   └── 0002-asahi-isa-Add-G16-indirect-jump-modifiers-RIA2-raytr.patch
└── docs/
    └── G16_REVERSE_ENGINEERING_REPORT.md  # Detailed reverse engineering analysis report
```

---

## 🚀 Quick Start

### 1. Requirements
* Python 3.10+
* `mako` (for Mesa code generator)
* macOS with Apple Silicon (tested on M3 Pro `Mac15,6`) or Linux environment

```bash
pip install mako construct pyserial
```

### 2. Extract Shaders from macOS G16 Driver Bundles
```bash
python3 tools/extract_g16_metallib.py
```
This extracts all GPU slices and machine code objects from `/System/Library/Extensions/AGXMetalG16X.bundle/` into `./extracted_shaders/`.

### 3. Run the Automated ISA Scanner
```bash
python3 tools/scan_g16_opcodes.py --analyze --limit 30
```
Scans the extracted code segments, tracks recognized vs unexpected bits, and outputs domain clustering stats.

### 4. Verify against Mesa Disassembler
If Mesa is cloned nearby:
```bash
cd /path/to/mesa/src/asahi/isa
python3 test-disasm.py /path/to/asahi-g16-toolkit/test/g16_cases.txt
```
Output:
```text
Pass.
```

---

## 🛠 Applying Patches to Upstream Mesa

The `patches/` directory contains standard git format patches that apply directly to Mesa `main`:

```bash
cd /path/to/mesa
git am /path/to/asahi-g16-toolkit/patches/*.patch
```

---

## 📜 License & Clean-Room Compliance

This project strictly adheres to **clean-room reverse engineering principles**:
- Analysis is performed via black-box observation of hardware register states, bitfield frequency clustering, and ISA disassembler test vectors.
- No proprietary source code or decompiled function logic is copied or distributed.
- Released under the MIT License.
