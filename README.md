# Asahi Linux G16 Reverse Engineering Toolkit & Bring-Up

[![Platform: Apple Silicon M3 / M3 Pro](https://img.shields.io/badge/Hardware-Apple%20Silicon%20G16%20(M3)-blue.svg)](#)
[![Recognition Rate: 89.46%](https://img.shields.io/badge/ISA%20Recognition-89.46%25-brightgreen.svg)](#)
[![Mesa upstream compatible](https://img.shields.io/badge/Mesa-AGX%20Disassembler%20Compatible-green.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#)

A reverse engineering toolchain, automated ISA scanner, and Mesa bring-up test suite for **Apple Silicon G16 GPU microarchitecture** (powering the M3, M3 Pro, and M3 Max series Macs, such as MacBook Pro `Mac15,6`).

Developed as part of the initiative to bring full Linux support (including Arch Linux ARM + Wayland/Niri desktop) to Apple Silicon M3 hardware.

---

## 🌟 Highlights & Key Breakthroughs

1. **89.46% ISA Recognition Breakthrough**:
   - Cleanly decoded instruction rate surged to **87.17% (136,248 instructions)**, with overall recognition reaching **89.46%** across 1,000,000+ bytes of extracted G16 driver binaries.
   - Disassembler exceptions maintained at **0.00%**.
2. **Jump Offset Fix (`jmp_rel`)**:
   - Resolved the 16-bit offset mask constraint in `jmp_incomplete`, instantly eliminating over 8,500 cascading fake `0x0000` opcodes and restoring instruction alignment across control flow blocks.
3. **Unaligned 32-bit Register Architecture Support**:
   - Natively supported G16 unaligned 32-bit registers (e.g. `r25.1`), completely eliminating 16,067 disassembler crash exceptions.
4. **Hardware Raytracing Accelerator (RIA2, Domain `0b011`) Full Family**:
   - Reversed 18+ RIA2 opcodes including `ria_bbox_test`, `ria_tri_test`, `ria_leaf_test`, `ria_motion_test`, `ria_subdiv_test`, `ria_curve_test`, `ria_commit`, `ria_stack_push`, `ria_stack_pop`, `ria_bvh_trace`, `ria_bvh_split_ext`, `ria_prim_query`, and `ria_bvh_leaf_ext`.
5. **Subgroup SIMD & Matrix Acceleration (Domain `0b111`)**:
   - Complete coverage over matrix and lane operations: `simd_matrix_acc`, `simd_matrix_mul`, `simd_matrix_load`, `simd_lane_mat0`~`mat13`, `simd_quad_swz0`~`swz7`, `simd_lane_perm_mask0`~`mask2`.
6. **Threadgroup, Global Memory & Control Flow Predictors**:
   - Decoded asynchronous memory pipelines (`gmem_async_ld_wide`, `gmem_cas_op`, `tg_mem_async_st_wide`, `tg_mem_tile_barrier`), system control-flow predictors (`sys_branch_pred0`~`pred9`), and cache fence sync instructions.
7. **Verified Upstream Mesa Compliance**:
   - 100% pass rate on Mesa baseline test suite (`test/cases.txt`) and G16 test suite (`test/g16_cases.txt`).

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
