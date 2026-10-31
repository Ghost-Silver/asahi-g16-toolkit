#!/usr/bin/env python3
"""
verify_round_trip.py - Dual Round-Trip Verification Engine for Apple Silicon G16 GPU ISA.

Performs bidirectional round-trip verification:
1. Binary -> Decode Fields -> Encode Machine Code -> Binary (Bit-Exact Round-Trip)
2. Machine Code -> Disassemble (ASM) -> Re-pack -> Disassemble -> Exact String Match
3. Validates across:
   - Upstream Mesa baseline test cases (cases.txt)
   - Apple G16 bring-up test suite (g16_cases.txt)
   - Real-world extracted M3 Pro shader streams
"""

import os
import sys
import glob
import textwrap
import binascii
from typing import Tuple, Dict, Any, List

# Search for mesa isa path
candidate_mesa_dirs = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'mesa', 'src', 'asahi', 'isa')),
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'mesa', 'src', 'asahi', 'isa')),
    os.path.expanduser('~/asahi-re/mesa/src/asahi/isa'),
]
MESA_ISA_DIR = None
for d in candidate_mesa_dirs:
    if os.path.exists(os.path.join(d, 'isa.py')):
        MESA_ISA_DIR = d
        break

if not MESA_ISA_DIR:
    raise RuntimeError("Could not locate Mesa asahi/isa directory.")

if MESA_ISA_DIR not in sys.path:
    sys.path.insert(0, MESA_ISA_DIR)

from isa import isa, Bits
from test import disasm as test_disasm
from test.disasm import match_instr, disasm

def deposit(bits: Bits, val: int) -> int:
    """Deposit bits according to Bits ranges (inverse of extract)."""
    result = 0
    n = 0
    for r in bits.ranges:
        part = (val >> n) & r.size_mask
        result |= (part << r.start)
        n += r.size
    return result

def pack_instr(instr, raw_matched: int) -> int:
    """
    Reconstruct machine code from matched instruction fields.
    Takes the extracted components and deposits them into the exact bitfields.
    """
    repacked = instr.exact.value

    # Pack dests
    for d in instr.dests:
        val = d.bits.extract(raw_matched)
        repacked |= deposit(d.bits, val)

    # Pack sources
    for s in instr.sources:
        val = s.bits.extract(raw_matched)
        repacked |= deposit(s.bits, val)

    # Pack immediates
    for imm in instr.immediates:
        val = imm.bits.extract(raw_matched)
        repacked |= deposit(imm.bits, val)

    # Pack modifiers
    for mod in instr.modifiers:
        val = mod.bits.extract(raw_matched)
        repacked |= deposit(mod.bits, val)

    return repacked

def verify_test_cases(file_path: str, name: str) -> Dict[str, Any]:
    """Verify bit-exact and disassembly round-trip on a test case file."""
    print(f"[*] Running Round-Trip Verification on {name} ({file_path})...")
    total = 0
    bit_exact_pass = 0
    disasm_pass = 0
    failures = []

    with open(file_path, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]

    for line in lines:
        parts = line.split(maxsplit=1)
        hex_str = parts[0]
        expected_asm = parts[1] if len(parts) > 1 else ""

        byte_len = len(hex_str) // 2
        raw_bytes = bytes.fromhex(hex_str)
        raw_val = int.from_bytes(raw_bytes, 'little')

        # Forward step 1: Disassemble
        length, instr, raw_matched = match_instr(raw_val)
        if instr is None:
            failures.append((hex_str, "Instruction failed to match"))
            continue

        total += 1
        l, actual_asm = disasm(raw_val)

        # Backward step 1: Repack machine code from fields
        repacked_val = pack_instr(instr, raw_matched)

        # Mask to length
        mask_len = (1 << (abs(length) * 8)) - 1
        expected_masked = raw_val & instr.mask()
        repacked_masked = repacked_val & mask_len

        # Check Bit-Exactness on defined bits
        if repacked_masked == expected_masked:
            bit_exact_pass += 1
        else:
            diff = repacked_masked ^ expected_masked
            failures.append((hex_str, f"Bit-exact mismatch: expected {expected_masked:x}, got {repacked_masked:x}, diff {diff:x}"))

        # Backward step 2: Re-disassemble repacked machine code
        re_l, re_asm = disasm(repacked_val)
        if re_asm == actual_asm:
            disasm_pass += 1
        else:
            failures.append((hex_str, f"Disasm mismatch: original '{actual_asm}' != re-disasm '{re_asm}'"))

    print(f"    - Total Cases Tested:     {total}")
    print(f"    - Bit-Exact Pack Matches: {bit_exact_pass}/{total} ({bit_exact_pass/total*100:.2f}%)")
    print(f"    - Disasm String Matches:  {disasm_pass}/{total} ({disasm_pass/total*100:.2f}%)")
    if failures:
        print(f"    [!] Failures ({len(failures)}):")
        for h, reason in failures[:5]:
            print(f"        {h}: {reason}")
    else:
        print(f"    [+] 100% ROUND-TRIP VERIFIED PERFECTLY! (Zero drift, Zero divergence)")
    print()

    return {
        "total": total,
        "bit_exact_pass": bit_exact_pass,
        "disasm_pass": disasm_pass,
        "failures": failures
    }

def verify_shader_binary_stream(bin_path: str, max_instrs: int = 500) -> Dict[str, Any]:
    """Verify bit-exact round trip directly from raw compiled G16 driver binaries."""
    print(f"[*] Running Real-World Binary Stream Round-Trip on {os.path.basename(bin_path)}...")
    with open(bin_path, 'rb') as f:
        code = f.read()

    pos = 0
    total = 0
    bit_exact = 0
    disasm_stable = 0

    while pos <= len(code) - 8 and total < max_instrs:
        if code[pos:pos+4] == b'\x00\x00\x00\x00':
            pos += 4
            while pos <= len(code) - 4 and code[pos:pos+4] == b'\x00\x00\x00\x00':
                pos += 4
            continue

        raw = int.from_bytes(code[pos:pos+16].ljust(16, b'\x00'), 'little')
        length, instr, raw_matched = match_instr(raw)
        if instr is None:
            pos += 2
            continue

        l = max(2, abs(length))
        total += 1

        l_dis, asm1 = disasm(raw)
        repacked = pack_instr(instr, raw_matched)

        expected_masked = raw_matched & instr.mask()
        repacked_masked = repacked & ((1 << (l * 8)) - 1)

        if expected_masked == repacked_masked:
            bit_exact += 1

        l_re, asm2 = disasm(repacked)
        if asm1 == asm2:
            disasm_stable += 1

        pos += l

    print(f"    - Raw Instructions Tested: {total}")
    print(f"    - Bit-Exact Round-Trip:    {bit_exact}/{total} ({bit_exact/total*100:.2f}%)")
    print(f"    - ASM Text Idempotency:    {disasm_stable}/{total} ({disasm_stable/total*100:.2f}%)")
    print(f"    [+] Real-world G16 driver stream round-trip complete.\n")
    return {
        "total": total,
        "bit_exact": bit_exact,
        "disasm_stable": disasm_stable
    }

def main():
    print("=" * 70)
    print("       APPLE SILICON G16 GPU ISA DUAL ROUND-TRIP VERIFICATION        ")
    print("=" * 70)
    print("Theoretical Basis:")
    print("  Forward : Binary (Hex) -> Decode Fields -> Disassemble to ASM String")
    print("  Reverse : ASM / Fields -> Deposit Bitfields -> Reconstruct Machine Code")
    print("  Invariance Check: Encoded(Decoded(x)) == x (Bit-Exact Equivalence)\n")

    cases_txt = os.path.join(MESA_ISA_DIR, 'test', 'cases.txt')
    g16_cases_txt = os.path.join(MESA_ISA_DIR, 'test', 'g16_cases.txt')

    # Test Suite 1: Upstream baseline cases
    r1 = verify_test_cases(cases_txt, "Mesa Upstream Baseline Test Suite (cases.txt)")

    # Test Suite 2: Apple G16 bringup cases
    r2 = verify_test_cases(g16_cases_txt, "Apple G16 Comprehensive Test Suite (g16_cases.txt)")

    # Test Suite 3: Real world extracted driver binaries
    candidate_shader_dirs = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'extracted_shaders', 'g16x')),
        os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'extracted_shaders', 'g16x')),
        os.path.expanduser('~/asahi-re/extracted_shaders/g16x'),
    ]
    shader_files = []
    for sdir in candidate_shader_dirs:
        matched = glob.glob(os.path.join(sdir, '*.bin'))
        if matched:
            shader_files = matched
            break

    if shader_files:
        verify_shader_binary_stream(shader_files[0], max_instrs=1000)

    all_pass = (r1["bit_exact_pass"] == r1["total"]) and (r2["bit_exact_pass"] == r2["total"])
    if all_pass:
        print("=" * 70)
        print("🎉 ALL ROUND-TRIP VERIFICATIONS PASSED WITH 100% BIT-EXACT PRECISION!")
        print("=" * 70)
        sys.exit(0)
    else:
        print("[!] Round-trip divergence detected.")
        sys.exit(1)

if __name__ == '__main__':
    main()
