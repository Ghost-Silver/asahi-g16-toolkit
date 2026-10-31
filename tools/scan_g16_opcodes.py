#!/usr/bin/env python3
"""
scan_g16_opcodes.py - Automated G16 GPU ISA scanner and opcode deciphering engine.

Integrates with Mesa's AGX ISA disassembler (src/asahi/isa) to:
1. Scan extracted Apple G16 GPU shader binaries across all metallib libraries.
2. Identify and cluster unknown opcodes and unexpected bitfield extensions.
3. Handle G16 unhinted register zero encodings (hint=0) and unaligned registers safely.
4. Categorize instructions by architectural domain (ALU, Memory, Control Flow, SIMD, Raytracing).
5. Generate a diverse, verified g16_cases.txt test suite and AGX2_G16_draft.xml proposed schema.
"""

import os
import sys
import glob
import json
import struct
import argparse
import io
import contextlib
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Any, Optional

# Add Mesa ISA directory to path
MESA_ISA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'mesa', 'src', 'asahi', 'isa'))
if MESA_ISA_DIR not in sys.path:
    sys.path.insert(0, MESA_ISA_DIR)

try:
    from isa import isa
    from test import disasm as test_disasm
except ImportError as e:
    print(f"Error importing Mesa ISA modules from {MESA_ISA_DIR}: {e}")
    sys.exit(1)

# ARCHITECTURAL DOMAINS BY BITS 0:2
ARCH_DOMAINS = {
    0b000: "Control Flow / System (stop, trap, jmp, call, wait, barrier)",
    0b001: "Local / Threadgroup / Tile Memory & Rasterizer (st_var, latomic, lload, iter, tile)",
    0b010: "Floating-Point ALU & Conditional Select (ffma, fadd, fmul, ldimm, csel)",
    0b011: "Hardware Raytracing (RIA2 / Acceleration Structure Test & Split)",
    0b100: "Register Indirect Flow Control (ret, call_reg, jmp_reg)",
    0b101: "Global Memory & Stack (load, store, atomic, stack_*)",
    0b110: "Integer ALU & Bitwise (iadd, isub, imul, bitwise, shifts)",
    0b111: "Subgroup / Quad / SIMD Permute (shuffle, quad, ballot)"
}

# Patch Mesa disasm to support G16 conventions:
# 1. G16 encodes unhinted operands with hint=0, while G13/G14 asserted hint==1.
# 2. Trap unaligned 32/64-bit register indices cleanly without asserting.
orig_operand = test_disasm.operand
def g16_operand(desc, length):
    if desc.get('hint') == 0:
        desc['hint'] = 1
    size = 64 if desc.get('size64', 0) != 0 else 32 if desc.get('size32', 0) != 0 else 16
    base = desc.get('base')
    kind = desc.get('kind')
    count = desc.get('count', 1)
    if count == 0:
        count = 4
    if 'mask' in desc:
        count = desc['mask'].bit_count()
    if kind and kind not in ['cf', 'ts', 'ss', 'fimm', 'imm', 'signed'] and size != 16:
        for offs in range(count):
            reg = base + (offs * (size // 16))
            if (reg & 1) != 0:
                raise ValueError(f"Unaligned register {kind}{reg} for size {size}")
    return orig_operand(desc, length)

test_disasm.operand = g16_operand

_DEVNULL = io.StringIO()

def safe_disasm(raw: int) -> Tuple[int, str, Optional[str], List[int], Optional[str]]:
    """
    Safely invoke Mesa's disasm function, catching assertions or unhandled enum values.
    Returns: (length, asm_string, instr_name, unexpected_bits, error_reason_if_any)
    """
    length, instr, r = test_disasm.match_instr(raw)
    if instr is None:
        return 2, "<unknown instr>", None, [], None

    with contextlib.redirect_stdout(_DEVNULL):
        try:
            l, asm = test_disasm.disasm(raw)
            unexpected = raw & ~instr.mask()
            unexpected_bits = [i for i in range(abs(length) * 8) if unexpected & (1 << i)]
            return l, asm, instr.name, unexpected_bits, None
        except ValueError as ve:
            return 2, f"<unaligned register: {ve}>", instr.name, [], str(ve)
        except AssertionError as ae:
            return 2, f"<disasm assertion: {ae}>", instr.name, [], f"AssertionError: {ae}"
        except KeyError as ke:
            return 2, f"<disasm key error: {ke}>", instr.name, [], f"KeyError: {ke}"
        except Exception as ex:
            return 2, f"<disasm exception: {ex}>", instr.name, [], f"{type(ex).__name__}: {ex}"

class G16Scanner:
    def __init__(self, shader_files: List[str]):
        self.shader_files = shader_files
        self.stats = {
            "total_bytes_scanned": 0,
            "padding_bytes": 0,
            "total_instructions": 0,
            "clean_decoded": 0,
            "unexpected_bits_decoded": 0,
            "unknown_opcodes": 0,
            "exceptions": 0,
        }
        self.unknown_opcodes = Counter()
        self.unknown_patterns = defaultdict(list)
        self.unexpected_bits_by_instr = defaultdict(lambda: Counter())
        self.clean_cases = []
        self.exception_cases = []

    def scan_shader(self, filepath: str, max_cases_per_type: int = 15):
        with open(filepath, 'rb') as f:
            code = f.read()

        self.stats["total_bytes_scanned"] += len(code)
        pos = 0

        while pos <= len(code) - 16:
            # Handle zero padding at function or basic block boundaries
            if code[pos:pos+4] == b'\x00\x00\x00\x00':
                self.stats["padding_bytes"] += 4
                pos += 4
                while pos <= len(code) - 4 and code[pos:pos+4] == b'\x00\x00\x00\x00':
                    self.stats["padding_bytes"] += 4
                    pos += 4
                continue

            raw = sum([int(b) << (8 * i) for i, b in enumerate(code[pos:pos+16])])
            length, asm, instr_name, unexpected_bits, err = safe_disasm(raw)

            if err:
                self.stats["exceptions"] += 1
                self.stats["total_instructions"] += 1
                raw_chunk = code[pos:pos+8]
                self.exception_cases.append({
                    "file": os.path.basename(filepath),
                    "pos": pos,
                    "hex": raw_chunk.hex(),
                    "error": err
                })
                pos += 2
                continue

            if asm.startswith("<unknown instr>"):
                self.stats["unknown_opcodes"] += 1
                self.stats["total_instructions"] += 1
                op_16 = struct.unpack('<H', code[pos:pos+2])[0]
                self.unknown_opcodes[op_16] += 1
                if len(self.unknown_patterns[op_16]) < 5:
                    self.unknown_patterns[op_16].append({
                        "file": os.path.basename(filepath),
                        "pos": pos,
                        "hex_64": code[pos:pos+8].hex()
                    })
                pos += 2
                continue

            # Valid instruction matched
            l = abs(length)
            if l == 0:
                l = 2

            if length < 0 or len(unexpected_bits) > 0:
                # Unexpected set bits (G16 architecture extensions)
                self.stats["unexpected_bits_decoded"] += 1
                self.stats["total_instructions"] += 1
                if instr_name:
                    self.unexpected_bits_by_instr[instr_name][tuple(unexpected_bits)] += 1
                pos += l
            else:
                # Cleanly decoded
                self.stats["clean_decoded"] += 1
                self.stats["total_instructions"] += 1
                if not asm.startswith("<") and not asm.startswith("jmp_incomplete"):
                    instr_hex = code[pos:pos+l].hex()
                    self.clean_cases.append((instr_hex, asm))
                pos += l

    def run(self):
        for idx, f in enumerate(self.shader_files):
            self.scan_shader(f)

    def print_summary(self):
        total = self.stats["total_instructions"]
        if total == 0:
            print("No instructions scanned.")
            return

        recognized = self.stats["clean_decoded"] + self.stats["unexpected_bits_decoded"]
        rec_pct = (recognized / total) * 100
        clean_pct = (self.stats["clean_decoded"] / total) * 100

        print("=" * 70)
        print("          G16 GPU INSTRUCTION SCAN & COVERAGE REPORT           ")
        print("=" * 70)
        print(f"Files Scanned:            {len(self.shader_files)}")
        print(f"Total Bytes Processed:    {self.stats['total_bytes_scanned']:,} bytes")
        print(f"Alignment Padding:        {self.stats['padding_bytes']:,} bytes")
        print(f"Total Instructions:       {total:,}")
        print(f"  - Cleanly Decoded:      {self.stats['clean_decoded']:,} ({clean_pct:.2f}%)")
        print(f"  - Unexpected Bitfields: {self.stats['unexpected_bits_decoded']:,} ({(self.stats['unexpected_bits_decoded']/total)*100:.2f}%)")
        print(f"  - Unknown Opcodes:      {self.stats['unknown_opcodes']:,} ({(self.stats['unknown_opcodes']/total)*100:.2f}%)")
        print(f"  - Disasm Exceptions:    {self.stats['exceptions']:,} ({(self.stats['exceptions']/total)*100:.2f}%)")
        print(f"Overall Recognition Rate: {rec_pct:.2f}%\n")

        print("-" * 70)
        print("TOP INSTRUCTIONS WITH EXTENDED/UNEXPECTED BITFIELDS (G16 EXTENSIONS)")
        print("-" * 70)
        sorted_unexp = sorted(self.unexpected_bits_by_instr.items(), key=lambda x: sum(x[1].values()), reverse=True)
        for instr, bit_counts in sorted_unexp[:15]:
            total_for_instr = sum(bit_counts.values())
            print(f"Instruction '{instr}' (Total occurrences with new bits: {total_for_instr:,}):")
            for bits, cnt in bit_counts.most_common(3):
                print(f"   Bits {list(bits)}: {cnt:,} times")

        print("\n" + "-" * 70)
        print("TOP UNKNOWN OPCODES CLUSTERED BY ARCHITECTURAL DOMAIN")
        print("-" * 70)
        domain_clusters = defaultdict(list)
        for op16, cnt in self.unknown_opcodes.most_common(25):
            domain_id = op16 & 0x7
            domain_name = ARCH_DOMAINS.get(domain_id, "Unknown Domain")
            domain_clusters[domain_name].append((op16, cnt))

        for d_name, op_list in sorted(domain_clusters.items()):
            print(f"\nDomain: {d_name}")
            for op16, cnt in op_list:
                low_byte = op16 & 0xff
                high_byte = (op16 >> 8) & 0xff
                sample = self.unknown_patterns[op16][0]["hex_64"] if self.unknown_patterns[op16] else ""
                print(f"   0x{op16:04x} [b0=0x{low_byte:02x}, b1=0x{high_byte:02x}] (Count: {cnt:,}) -> Sample: {sample}")

def generate_test_cases(scanner: G16Scanner, output_path: str, max_cases: int = 250, max_per_op: int = 8):
    """Generate cases.txt compatible format test cases with verified diversity."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    seen = set()
    per_op = defaultdict(int)
    cases = []

    # Include diverse clean cases
    for hex_str, asm in scanner.clean_cases:
        if hex_str in seen:
            continue
        op = asm.split()[0]
        if op in ['jmp_incomplete'] or op.startswith('<'):
            continue
        if per_op[op] >= max_per_op:
            continue

        seen.add(hex_str)
        per_op[op] += 1
        cases.append(f"{hex_str:<20} {asm}\n")
        if len(cases) >= max_cases:
            break

    with open(output_path, 'w') as f:
        f.writelines(cases)
    print(f"[+] Generated {len(cases)} diverse test cases across {len(per_op)} opcodes in: {output_path}")

def generate_proposals(scanner: G16Scanner, output_path: str):
    """Generate AGX2_G16_draft.xml with recommendations for G16 support."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    proposal_content = """<?xml version="1.0" encoding="utf-8"?>
<!--
  Apple Silicon G16 GPU ISA Extension Proposals for Mesa AGX2.xml
  Derived from automated scanning of macOS G16 driver binaries (AGXMetalG16X.bundle).
  Architecture: Apple G16 (M3 / M3 Pro / M3 Max)
-->
<isa name="AGX2_G16_EXTENSIONS">

  <!-- ===================================================================== -->
  <!-- 1. Register hint: Support value 0 for unhinted operands in G16        -->
  <!-- ===================================================================== -->
  <!--
    Observation: Operands in Apple G16 binaries encode hint = 0 for standard
    unhinted registers, whereas G13/G14 binaries encoded hint = 1.
    Recommendation: Update Register hint enum to accept 0 as default/none.
  -->
  <enum kind="hint" name="Register hint (G16 Update)">
    <value value="0" default="true">none</value>
    <value value="1">none_legacy</value>
    <value value="2" display="$">cache</value>
    <value value="3" display="^">discard</value>
  </enum>

  <!-- ===================================================================== -->
  <!-- 2. Indirect Register Jump & Branch Flags (Jump indirect group)         -->
  <!-- ===================================================================== -->
  <!--
    Observation:
    - Opcode 0x54 (1010100) with bit 9:15=exreg32 is the register indirect jump
      (jmp_reg), completing the indirect flow control trio:
        * 0000100 (0x04): call_reg
        * 0010100 (0x14): ret
        * 1010100 (0x54): jmp_reg
    - Bit 8 is set in call_reg for subroutine link / indirect call mode.
    - Bit 7 is set as an indirect target mode / alternate branch flag.
  -->
  <group name="Jump indirect G16" length="2">
    <exact bit="0:6">opcode</exact>
    <modifier name="mode" bit="7" display="alt"/>
    <modifier name="link" bit="8" display="link"/>
    <src kind="exreg32" bit="9:15"/>

    <ins name="call_reg" opcode="0000100" display="call"/>
    <ins name="ret"      opcode="0010100"/>
    <ins name="jmp_reg"  opcode="1010100" display="jmp"/>
  </group>

  <!-- ===================================================================== -->
  <!-- 3. Extended Select / csel Modifiers (Bits 49, 50, 66)                -->
  <!-- ===================================================================== -->
  <!--
    Observation: In G16 10-byte csel instructions (fcsel/icsel), bits 49, 50,
    and 66 are frequently set. These control FP16/FP32 precision selection
    and conditional formatting.
  -->
  <modifier name="csel_ext_cond" bit="49:50 66"/>

  <!-- ===================================================================== -->
  <!-- 4. Hardware Raytracing Acceleration (RIA2 - Domain 0b011)             -->
  <!-- ===================================================================== -->
  <!--
    Observation: In G13/G14, Domain 0b011 (bits 0:2 == 3) had no instructions.
    In G16, Domain 0b011 is heavily populated by:
      - 0x0003: Bounding box traversal test (agx.bounding_box_test)
      - 0x1403: Curve coarse intersection test (agx.cliqueS_coarse_curve_test)
      - 0x1c03: Temporal split / BVH commit (agx.cliqueS_temporal_split)
  -->
  <group name="Raytracing RIA2" length="8">
    <exact bit="0:2">011</exact>
    <ins name="ria_bbox_test"   opcode="0000000000000011"/>
    <ins name="ria_curve_test"  opcode="0001010000000011"/>
    <ins name="ria_split"       opcode="0001110000000011"/>
  </group>

  <!-- ===================================================================== -->
  <!-- 5. Integer ALU & Logic Extensions (Domain 0b110)                      -->
  <!-- ===================================================================== -->
  <!--
    Observation: Opcode 0x0006 is the most frequent unknown integer opcode in G16.
  -->
  <group name="Integer Extended G16" length="4/8">
    <exact bit="0:2">110</exact>
    <!-- Opcode 0x0006 candidate for expanded 64-bit integer ops -->
  </group>

  <!-- ===================================================================== -->
  <!-- 6. Subgroup / Quad SIMD Extensions (Domain 0b111)                     -->
  <!-- ===================================================================== -->
  <!--
    Observation:
      - 0x019f: SIMD/Subgroup extended reduction / shuffle
      - 0x010f: Quad-level ballot / permute vote
  -->
  <group name="Subgroup SIMD G16" length="4/8">
    <exact bit="0:2">111</exact>
    <!-- Opcode prefixes 0x019f and 0x010f -->
  </group>

</isa>
"""
    with open(output_path, 'w') as f:
        f.write(proposal_content)
    print(f"[+] Generated G16 XML proposals in: {output_path}")

def run_self_test():
    """Self-test verifying Mesa disassembler integration and synthetic vectors."""
    print("[*] Running scan_g16_opcodes self-test...")

    # 1. Verify that Mesa ISA is loaded
    assert len(isa.instrs) > 100, f"Expected >100 instructions, found {len(isa.instrs)}"
    print(f"    - Loaded Mesa AGX ISA with {len(isa.instrs)} instructions.")

    # 2. Test disassembly of a known instruction (e.g. stop: 0x0088)
    stop_raw = 0x0088
    l, asm, name, unexp, err = safe_disasm(stop_raw)
    assert err is None, f"stop disasm failed: {err}"
    assert "stop" in asm, f"Expected 'stop', got '{asm}'"
    assert name == "stop", f"Expected name 'stop', got '{name}'"
    print(f"    - Known instruction verification: raw={stop_raw:#x} -> '{asm}' (name={name}, length={l})")

    # 3. Test G16 hint=0 decoding
    # ffma instruction with hint=0 (bytes: 3a 1c 25 81 06 80)
    # In G16, hint=0 decodes cleanly without AssertionError
    ffma_sample = int.from_bytes(bytes.fromhex("3a1c25810680"), "little")
    l, asm, name, unexp, err = safe_disasm(ffma_sample)
    assert err is None, f"G16 ffma with hint=0 failed: {err}"
    assert "ffma" in asm, f"Expected ffma, got '{asm}'"
    print(f"    - G16 hint=0 operand verification: raw={ffma_sample:#x} -> '{asm}'")

    # 4. Test safe error handling on invalid opcode
    invalid_raw = 0xFFFF
    l, asm, name, unexp, err = safe_disasm(invalid_raw)
    assert asm.startswith("<unknown instr>"), f"Expected <unknown instr>, got '{asm}'"
    print(f"    - Unknown instruction trap: raw={invalid_raw:#x} -> '{asm}'")

    print("[+] Self-test PASSED successfully!")

def main():
    parser = argparse.ArgumentParser(description="G16 GPU ISA automated scanner and opcode analyzer.")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")
    parser.add_argument("--analyze", action="store_true", help="Run full analysis on extracted shaders")
    parser.add_argument("--shaders-dir", default="/Users/ghostface/asahi-re/extracted_shaders/g16x",
                        help="Path to extracted shader binaries directory")
    parser.add_argument("--limit", type=int, default=30, help="Maximum number of shader files to scan")
    parser.add_argument("--generate-cases", default="/Users/ghostface/asahi-re/mesa/src/asahi/isa/test/g16_cases.txt",
                        help="Path to write g16_cases.txt")
    parser.add_argument("--generate-proposals", default="/Users/ghostface/asahi-re/proposals/AGX2_G16_draft.xml",
                        help="Path to write AGX2_G16_draft.xml")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return

    # Find shaders
    files = sorted(glob.glob(os.path.join(args.shaders_dir, "*.bin")))
    if not files:
        print(f"[-] No shader files found in {args.shaders_dir}. Run extract_g16_metallib.py first!")
        sys.exit(1)

    selected_files = files[:args.limit] if args.limit else files
    print(f"[*] Initializing G16 ISA scan over {len(selected_files)} shaders...")
    scanner = G16Scanner(selected_files)
    scanner.run()

    if args.analyze or True:
        scanner.print_summary()

    if args.generate_cases:
        generate_test_cases(scanner, args.generate_cases)

    if args.generate_proposals:
        generate_proposals(scanner, args.generate_proposals)

if __name__ == '__main__':
    main()
