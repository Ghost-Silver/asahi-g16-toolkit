#!/usr/bin/env python3
"""
extract_g16_metallib.py - Extract raw AGX machine code sections from macOS G16 driver binaries.

Supports:
- Mach-O Fat binaries (Archive_release.metallib, Archive_release_gen2.metallib)
- Mach-O 64-bit GPU binaries (ds.binary.metallib.g16s-b0, etc.)
- Embedded Mach-O object containers (__builtin, __compute sections)
- Symbol parsing for shader entrypoints (_agc.main, constant_program)
"""

import os
import sys
import struct
import argparse
import json
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple, Dict, Any

MH_MAGIC_64 = 0xfeedfacf
FAT_MAGIC = 0xcafebabe
CPU_TYPE_APPLE_GPU = 0x01000013  # 16777235
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x2

@dataclass
class ShaderSymbol:
    name: str
    section_index: int
    offset: int

@dataclass
class ExtractedShader:
    source_file: str
    container_section: str
    object_index: int
    offset_in_container: int
    code_size: int
    symbols: List[Dict[str, Any]]
    code_bytes: bytes

def parse_macho_object(data: bytes, base_offset: int = 0) -> Optional[Tuple[bytes, List[ShaderSymbol], int]]:
    """
    Parse a single MH_OBJECT Mach-O binary.
    Returns: (code_bytes, symbols, total_object_size) or None if invalid.
    """
    if len(data) - base_offset < 32:
        return None
    
    magic = struct.unpack('<I', data[base_offset:base_offset+4])[0]
    if magic != MH_MAGIC_64:
        return None
    
    cputype, cpusubtype, filetype, ncmds, sizeofcmds = struct.unpack('<IIIII', data[base_offset+4:base_offset+24])
    if cputype != CPU_TYPE_APPLE_GPU:
        return None

    cmd_offset = base_offset + 32
    text_section = None
    symtab_info = None
    max_offset = 32 + sizeofcmds

    for _ in range(ncmds):
        if cmd_offset + 8 > len(data):
            break
        cmd, cmdsize = struct.unpack('<II', data[cmd_offset:cmd_offset+8])
        if cmd == LC_SEGMENT_64:
            if cmd_offset + 72 <= len(data):
                nsects = struct.unpack('<I', data[cmd_offset+64:cmd_offset+68])[0]
                sect_offset = cmd_offset + 72
                for s_idx in range(nsects):
                    if sect_offset + 80 > len(data):
                        break
                    sectname = data[sect_offset:sect_offset+16].rstrip(b'\x00').decode('ascii', errors='replace')
                    ssegname = data[sect_offset+16:sect_offset+32].rstrip(b'\x00').decode('ascii', errors='replace')
                    addr, size, offset = struct.unpack('<QQI', data[sect_offset+32:sect_offset+52])
                    if ssegname == '__TEXT' and sectname in ['__text', '__compute']:
                        text_section = (s_idx + 1, offset, size)
                    if offset + size > max_offset:
                        max_offset = offset + size
                    sect_offset += 80
        elif cmd == LC_SYMTAB:
            if cmd_offset + 24 <= len(data):
                symoff, nsyms, stroff, strsize = struct.unpack('<IIII', data[cmd_offset+8:cmd_offset+24])
                symtab_info = (symoff, nsyms, stroff, strsize)
                if stroff + strsize > max_offset:
                    max_offset = stroff + strsize
        cmd_offset += cmdsize

    if not text_section:
        return None

    sec_idx, sec_off, sec_size = text_section
    code_start = base_offset + sec_off
    code_end = code_start + sec_size
    if code_end > len(data):
        return None

    code_bytes = data[code_start:code_end]

    # Parse symbols if available
    symbols = []
    if symtab_info:
        symoff, nsyms, stroff, strsize = symtab_info
        sym_start = base_offset + symoff
        str_start = base_offset + stroff
        strtab = data[str_start:str_start+strsize] if str_start + strsize <= len(data) else b''

        for i in range(nsyms):
            curr_sym = sym_start + i * 16
            if curr_sym + 16 <= len(data):
                n_strx, n_type, n_sect, n_desc, n_value = struct.unpack('<IBBHQ', data[curr_sym:curr_sym+16])
                if n_sect == sec_idx and n_strx < len(strtab):
                    null_pos = strtab.find(b'\x00', n_strx)
                    if null_pos != -1:
                        sname = strtab[n_strx:null_pos].decode('ascii', errors='replace')
                        symbols.append(ShaderSymbol(name=sname, section_index=n_sect, offset=n_value))

    # Align max_offset to 16 bytes
    aligned_obj_size = (max_offset + 15) & ~15
    return code_bytes, symbols, aligned_obj_size

def extract_from_macho_container(data: bytes, source_name: str, container_name: str) -> List[ExtractedShader]:
    """Scan container data for embedded Mach-O object files."""
    shaders = []
    pos = 0
    obj_idx = 0

    while pos <= len(data) - 32:
        magic = struct.unpack('<I', data[pos:pos+4])[0]
        if magic == MH_MAGIC_64:
            res = parse_macho_object(data, pos)
            if res:
                code_bytes, symbols, obj_size = res
                shader = ExtractedShader(
                    source_file=source_name,
                    container_section=container_name,
                    object_index=obj_idx,
                    offset_in_container=pos,
                    code_size=len(code_bytes),
                    symbols=[asdict(s) for s in symbols],
                    code_bytes=code_bytes
                )
                shaders.append(shader)
                obj_idx += 1
                pos += max(obj_size, 16)
                continue
        pos += 4

    return shaders

def extract_from_file(file_path: str) -> List[ExtractedShader]:
    """Extract all shaders from a given metallib or driver file."""
    if not os.path.exists(file_path) or os.path.islink(file_path):
        return []

    with open(file_path, 'rb') as f:
        data = f.read()

    if len(data) < 32:
        return []

    source_name = os.path.basename(file_path)
    magic_le = struct.unpack('<I', data[:4])[0]
    magic_be = struct.unpack('>I', data[:4])[0]
    sub_slices = []

    if magic_be == FAT_MAGIC or magic_le == FAT_MAGIC:
        # Mach-O Fat universal binary (FAT_MAGIC is big-endian 0xcafebabe)
        nfat_arch = struct.unpack('>I', data[4:8])[0]
        for i in range(nfat_arch):
            off = 8 + i * 20
            cputype, cpusubtype, offset, size, align = struct.unpack('>IIIII', data[off:off+20])
            if cputype == CPU_TYPE_APPLE_GPU:
                sub_slices.append((f'{source_name}:gpu_slice_{i}', data[offset:offset+size]))
    elif magic_le == MH_MAGIC_64:
        sub_slices.append((source_name, data))

    all_shaders = []
    for s_name, s_data in sub_slices:
        # Check top-level segments for container sections (__builtin, __compute)
        cputype, cpusubtype, filetype, ncmds, sizeofcmds = struct.unpack('<IIIII', s_data[4:24])
        cmd_offset = 32
        container_sections = []
        for _ in range(ncmds):
            if cmd_offset + 8 > len(s_data):
                break
            cmd, cmdsize = struct.unpack('<II', s_data[cmd_offset:cmd_offset+8])
            if cmd == LC_SEGMENT_64:
                nsects = struct.unpack('<I', s_data[cmd_offset+64:cmd_offset+68])[0]
                sect_offset = cmd_offset + 72
                for _ in range(nsects):
                    if sect_offset + 80 > len(s_data):
                        break
                    sectname = s_data[sect_offset:sect_offset+16].rstrip(b'\x00').decode('ascii', errors='replace')
                    ssegname = s_data[sect_offset+16:sect_offset+32].rstrip(b'\x00').decode('ascii', errors='replace')
                    addr, size, offset = struct.unpack('<QQI', s_data[sect_offset+32:sect_offset+52])
                    if sectname in ['__builtin', '__compute', '__text'] and size > 0:
                        container_sections.append((f'{ssegname}.{sectname}', offset, size))
                    sect_offset += 80
            cmd_offset += cmdsize

        for c_name, c_offset, c_size in container_sections:
            c_data = s_data[c_offset:c_offset+c_size]
            # Try parsing embedded objects inside this section
            extracted = extract_from_macho_container(c_data, s_name, c_name)
            if extracted:
                all_shaders.extend(extracted)
            elif c_name.endswith('.__text') or c_name.endswith('.__compute'):
                # Single standalone shader section without nested Mach-O
                all_shaders.append(ExtractedShader(
                    source_file=s_name,
                    container_section=c_name,
                    object_index=0,
                    offset_in_container=c_offset,
                    code_size=len(c_data),
                    symbols=[],
                    code_bytes=c_data
                ))

    return all_shaders

def extract_all(bundle_dir: str, max_shaders: Optional[int] = None) -> List[ExtractedShader]:
    """Scan bundle directory and extract shaders from all compatible binaries."""
    candidates = [
        'Archive_release.metallib',
        'Archive_release_gen2.metallib',
        'ds.binary.metallib.g16s-b0'
    ]
    all_shaders = []
    # If max_shaders specified, extract a fair share from each candidate
    per_file_limit = (max_shaders // len(candidates) + 10) if max_shaders else None

    for cand in candidates:
        full_path = os.path.join(bundle_dir, cand)
        if os.path.exists(full_path) and not os.path.islink(full_path):
            shaders = extract_from_file(full_path)
            if per_file_limit:
                shaders = shaders[:per_file_limit]
            all_shaders.extend(shaders)
            if max_shaders and len(all_shaders) >= max_shaders:
                return all_shaders[:max_shaders]
    return all_shaders

def main():
    parser = argparse.ArgumentParser(description="Extract G16 GPU machine code from native macOS metallibs.")
    parser.add_argument("--bundle-dir", default="/System/Library/Extensions/AGXMetalG16X.bundle/Contents/Resources",
                        help="Path to AGXMetal resources directory")
    parser.add_argument("--output-dir", default="/Users/ghostface/asahi-re/extracted_shaders/g16x",
                        help="Destination directory for extracted shader binaries")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of shaders to extract")
    parser.add_argument("--self-test", action="store_true", help="Run self-test on the extraction pipeline")
    args = parser.parse_args()

    if args.self_test:
        print("[*] Running extract_g16_metallib self-test...")
        shaders = extract_all(args.bundle_dir, max_shaders=10)
        assert len(shaders) > 0, "No shaders extracted!"
        assert all(s.code_size > 0 for s in shaders), "Zero code size shader encountered!"
        print(f"[+] Self-test PASSED: successfully extracted {len(shaders)} shaders.")
        for s in shaders[:3]:
            sym_names = [sym['name'] for sym in s.symbols]
            print(f"    - {s.source_file}:{s.container_section} obj#{s.object_index}: {s.code_size} bytes, syms={sym_names}")
        return

    os.makedirs(args.output_dir, exist_ok=True)
    shaders = extract_all(args.bundle_dir, max_shaders=args.limit)
    print(f"[*] Extracted {len(shaders)} shaders from {args.bundle_dir}")

    metadata = []
    total_bytes = 0
    for s in shaders:
        clean_src = s.source_file.replace('/', '_').replace(':', '_')
        clean_sec = s.container_section.replace('.', '_')
        filename = f"{clean_src}_{clean_sec}_obj{s.object_index:04d}.bin"
        out_path = os.path.join(args.output_dir, filename)
        with open(out_path, 'wb') as f:
            f.write(s.code_bytes)
        
        meta_entry = {
            "source_file": s.source_file,
            "container_section": s.container_section,
            "object_index": s.object_index,
            "file": filename,
            "size": s.code_size,
            "symbols": s.symbols
        }
        metadata.append(meta_entry)
        total_bytes += s.code_size

    manifest_path = os.path.join(args.output_dir, "manifest.json")
    with open(manifest_path, 'w') as f:
        json.dump({"total_shaders": len(shaders), "total_code_bytes": total_bytes, "shaders": metadata}, f, indent=2)

    print(f"[+] Saved {len(shaders)} shaders ({total_bytes} bytes code) to {args.output_dir}")
    print(f"[+] Manifest: {manifest_path}")

if __name__ == '__main__':
    main()
