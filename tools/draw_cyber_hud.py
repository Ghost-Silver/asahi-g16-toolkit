#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
draw_cyber_hud.py - Apple Silicon M3 Pro (G16) Bare-Metal Cyber Test Screen

Renders a high-resolution 3024x1964 cyberpunk telemetry dashboard, arc reactor orb,
hardware status cards, SMPTE color bars, and 10-bit HDR rainbow spectrum directly
onto the Apple Liquid Retina XDR screen over m1n1 USB-C CDC-ACM.
"""

import os
import sys
import math
import time
import struct
import pathlib
from PIL import Image, ImageDraw, ImageFont

# Add m1n1 proxyclient to path
M1N1_PATH = pathlib.Path("/home/ghostsilver/Projects/m1n1/proxyclient")
if str(M1N1_PATH) not in sys.path:
    sys.path.insert(0, str(M1N1_PATH))

os.environ["M1N1DEVICE"] = os.environ.get("M1N1DEVICE", "/dev/ttyACM0")

from m1n1.setup import *
from m1n1.proxy import IODEV

def log(msg):
    print(f"[*] {msg}")

def create_cyber_hud():
    w, h = 3024, 1964
    log(f"Allocating canvas {w}x{h} (30bpp Liquid Retina XDR target)...")
    img = Image.new("RGBA", (w, h), (10, 14, 22, 255))
    draw = ImageDraw.Draw(img)

    # Load JetBrains Mono fonts
    font_bold = "/usr/share/fonts/TTF/JetBrainsMonoNerdFontPropo-Bold.ttf"
    f_title = ImageFont.truetype(font_bold, 54)
    f_sub = ImageFont.truetype(font_bold, 30)
    f_spec = ImageFont.truetype(font_bold, 24)
    f_head = ImageFont.truetype(font_bold, 26)
    f_card_t = ImageFont.truetype(font_bold, 22)
    f_card_d = ImageFont.truetype(font_bold, 18)
    f_core = ImageFont.truetype(font_bold, 76)
    f_core_sub = ImageFont.truetype(font_bold, 22)
    f_foot = ImageFont.truetype(font_bold, 20)

    # 1. Subtle High-Tech Grid
    log("Rendering cybernetic background grid...")
    for x in range(0, w, 64):
        c = (35, 55, 80, 255) if (x % 256 == 0) else (18, 26, 40, 255)
        draw.line([(x, 0), (x, h)], fill=c, width=1)
    for y in range(0, h, 64):
        c = (35, 55, 80, 255) if (y % 256 == 0) else (18, 26, 40, 255)
        draw.line([(0, y), (w, y)], fill=c, width=1)

    # Screen Corner Tech Brackets
    bracket_col = (0, 229, 255, 255)
    margin, b_len = 80, 100
    # Top-Left
    draw.line([(margin, margin), (margin + b_len, margin)], fill=bracket_col, width=4)
    draw.line([(margin, margin), (margin, margin + b_len)], fill=bracket_col, width=4)
    # Top-Right
    draw.line([(w - margin, margin), (w - margin - b_len, margin)], fill=bracket_col, width=4)
    draw.line([(w - margin, margin), (w - margin, margin + b_len)], fill=bracket_col, width=4)
    # Bottom-Left
    draw.line([(margin, h - margin), (margin + b_len, h - margin)], fill=bracket_col, width=4)
    draw.line([(margin, h - margin), (margin, h - margin - b_len)], fill=bracket_col, width=4)
    # Bottom-Right
    draw.line([(w - margin, h - margin), (w - margin - b_len, h - margin)], fill=bracket_col, width=4)
    draw.line([(w - margin, h - margin), (w - margin, h - margin - b_len)], fill=bracket_col, width=4)

    # 2. Top Header Banner
    log("Rendering top telemetry header...")
    title_text = "ASAHI LINUX // APPLE SILICON G16 GPU BRING-UP"
    sub_text = "TARGET: MACBOOK PRO 14\" (Mac15,6 / J514s / M3 PRO / t6030)"
    spec_text = "PHYSICAL MMIO: 0x290000000  •  UAT MMU: 42-BIT ACTIVE  •  DVFS: 1380 MHZ  •  14-CORE GPU"

    # Centered text helper
    def draw_centered_text(y, text, font, color):
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2, y), text, font=font, fill=color)

    draw_centered_text(130, title_text, f_title, (0, 240, 255, 255))
    draw_centered_text(210, sub_text, f_sub, (255, 255, 255, 255))
    draw_centered_text(265, spec_text, f_spec, (0, 255, 170, 255))

    # Divider bar with neon cyan accent
    draw.line([(300, 315), (w - 300, 315)], fill=(0, 229, 255, 180), width=3)
    draw.line([(w // 2 - 200, 315), (w // 2 + 200, 315)], fill=(255, 255, 255, 255), width=4)

    # 3. Centerpiece - Cybernetic Arc Reactor Reticle
    log("Rendering central G16 cybernetic reticle...")
    cx, cy = w // 2, 970

    # Draw outer segmented reticle rings
    r_outer = 380
    for deg in range(0, 360, 90):
        draw.arc([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
                 start=deg + 10, end=deg + 80, fill=(0, 229, 255, 255), width=5)

    # 4 crosshair tick extensions
    draw.line([(cx - r_outer - 50, cy), (cx - r_outer + 10, cy)], fill=(0, 229, 255, 255), width=3)
    draw.line([(cx + r_outer - 10, cy), (cx + r_outer + 50, cy)], fill=(0, 229, 255, 255), width=3)
    draw.line([(cx, cy - r_outer - 50), (cx, cy - r_outer + 10)], fill=(0, 229, 255, 255), width=3)
    draw.line([(cx, cy + r_outer - 10), (cx, cy + r_outer + 50)], fill=(0, 229, 255, 255), width=3)

    # Rotating radial spoke ticks
    r_ticks = 320
    for i in range(24):
        ang = i * (2 * math.pi / 24)
        x1 = cx + int((r_ticks - 15) * math.cos(ang))
        y1 = cy + int((r_ticks - 15) * math.sin(ang))
        x2 = cx + int(r_ticks * math.cos(ang))
        y2 = cy + int(r_ticks * math.sin(ang))
        draw.line([(x1, y1), (x2, y2)], fill=(255, 190, 0, 255), width=3)

    # Inner rings
    draw.arc([cx - 260, cy - 260, cx + 260, cy + 260], 0, 360, fill=(255, 0, 128, 255), width=4)
    draw.arc([cx - 210, cy - 210, cx + 210, cy + 210], 0, 360, fill=(160, 50, 255, 255), width=3)

    # Core Plasma Glow Orb
    r_core = 145
    for r in range(r_core, 0, -2):
        frac = r / r_core
        # Gradient from center white/cyan to outer deep purple
        cr = int(255 * (1 - frac) + 80 * frac)
        cg = int(255 * (1 - frac) + 20 * frac)
        cb = int(255 * (1 - frac) + 220 * frac)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(cr, cg, cb, 255))

    # Core Emblem Text
    bbox_g16 = draw.textbbox((0, 0), "G16", font=f_core)
    gw = bbox_g16[2] - bbox_g16[0]
    draw.text((cx - gw // 2, cy - 65), "G16", font=f_core, fill=(10, 14, 25, 255))

    bbox_m3 = draw.textbbox((0, 0), "APPLE M3 PRO", font=f_core_sub)
    mw = bbox_m3[2] - bbox_m3[0]
    draw.text((cx - mw // 2, cy + 22), "APPLE M3 PRO", font=f_core_sub, fill=(255, 215, 0, 255))

    # 4. Telemetry Badges (Left & Right Flanks)
    log("Rendering telemetry cards...")
    def draw_card(bx, by, bw, bh, tag, title, detail, col_border, col_tag):
        # Card background
        draw.rectangle([bx, by, bx + bw, by + bh], fill=(16, 22, 34, 240), outline=col_border, width=2)
        # Corner accent
        draw.rectangle([bx, by, bx + 12, by + 12], fill=col_border)
        # Text
        draw.text((bx + 24, by + 16), tag, font=f_card_t, fill=col_tag)
        draw.text((bx + 24, by + 46), title, font=f_card_t, fill=(255, 255, 255, 255))
        draw.text((bx + 24, by + 80), detail, font=f_card_d, fill=(170, 190, 210, 255))

    # Left Flank Cards
    left_x, card_w, card_h = 200, 750, 116
    draw.text((left_x, 470), "=== COMPILER & ISA VERIFICATION ===", font=f_head, fill=(0, 229, 255, 255))

    left_cards = [
        ("[✓] ISA RECOGNITION RATE", "100.00% IDENTIFIED", "139,467 instructions decoded cleanly with 0 crashes", (0, 255, 120, 255), (0, 255, 120, 255)),
        ("[✓] RIA2 HARDWARE RAYTRACING", "BVH & TRI INTERSECT ACTIVE", "18+ Raytracing opcodes reverse-engineered from driver", (255, 190, 0, 255), (255, 190, 0, 255)),
        ("[✓] SUBGROUP MATRIX & SIMD", "8-BYTE SIMD OPERATIONAL", "simd_matrix_acc, simd_matrix_mul, lane_permute verified", (0, 200, 255, 255), (0, 200, 255, 255)),
        ("[✓] INDIRECT CONTROL FLOW", "INDIRECT CALLS & JUMPS OK", "call_ind, jmp_reg, ret_cond, branch_cond_ind active", (200, 90, 255, 255), (200, 90, 255, 255)),
        ("[✓] DUAL ROUND-TRIP ENGINE", "100.00% BIT-EXACT PRECISION", "Binary -> AST -> Repack -> Binary verified with zero drift", (255, 90, 130, 255), (255, 90, 130, 255)),
    ]

    for i, (tag, t, d, cb, ct) in enumerate(left_cards):
        draw_card(left_x, 520 + i * 140, card_w, card_h, tag, t, d, cb, ct)

    # Right Flank Cards
    right_x = w - 200 - card_w
    draw.text((right_x, 470), "=== BARE-METAL HARDWARE STATUS ===", font=f_head, fill=(255, 0, 128, 255))

    right_cards = [
        ("[✓] GFX PMGR POWER DOMAIN", "DEV 226 FULLY POWERED (0xF)", "Power Gates 339, 340, 341 unlocked with active clocks", (255, 0, 128, 255), (255, 0, 128, 255)),
        ("[✓] PHYSICAL MMIO RGX CORE", "0x290000000 ACCESSED", "64 USC Execution Core Slots online (Status 0x100)", (140, 80, 255, 255), (140, 80, 255, 255)),
        ("[✓] INTERNAL GPU SRAM", "0x290D60000 ACTIVE", "GPU Cache SRAM probed with verified non-zero contents", (0, 240, 220, 255), (0, 240, 220, 255)),
        ("[✓] GFX-ASC COPROCESSOR", "ARM64 RTKIT V12 PROBED", "Reset vector 'b +0x204' verified in physical RAM segment", (60, 255, 120, 255), (60, 255, 120, 255)),
        ("[✓] UAT MMU CONTEXT 0", "42-BIT TRANSLATION ONLINE", "TTBR0 @ 0x1000e688000 & TTBR1 @ 0x1047ff78000 mapped", (255, 215, 0, 255), (255, 215, 0, 255)),
    ]

    for i, (tag, t, d, cb, ct) in enumerate(right_cards):
        draw_card(right_x, 520 + i * 140, card_w, card_h, tag, t, d, cb, ct)

    # 5. Bottom Professional SMPTE-Calibrated Color Bars
    log("Rendering bottom SMPTE color bars & HDR rainbow...")
    bar_y1, bar_y2 = 1630, 1720
    bar_x1, bar_x2 = 200, w - 200
    bar_w = (bar_x2 - bar_x1) // 8

    smpte_colors = [
        (255, 255, 255), # White
        (255, 255, 0),   # Yellow
        (0, 255, 255),   # Cyan
        (0, 255, 0),     # Green
        (255, 0, 255),   # Magenta
        (255, 0, 0),     # Red
        (0, 0, 255),     # Blue
        (120, 0, 220),   # Violet
    ]

    for i, c in enumerate(smpte_colors):
        bx = bar_x1 + i * bar_w
        draw.rectangle([bx, bar_y1, bx + bar_w, bar_y2], fill=(c[0], c[1], c[2], 255))
    # Border around color bars
    draw.rectangle([bar_x1, bar_y1, bar_x1 + 8 * bar_w, bar_y2], outline=(0, 229, 255, 255), width=2)

    # 6. Ultra-Smooth 10-Bit Continuous HDR Rainbow Sweep
    rainbow_y1, rainbow_y2 = 1740, 1795
    rainbow_len = bar_x2 - bar_x1

    for px in range(rainbow_len):
        hue = (px / rainbow_len) * 6.0
        x_val = int(255 * (1 - abs((hue % 2) - 1)))
        if hue < 1:   rc, gc, bc = 255, x_val, 0
        elif hue < 2: rc, gc, bc = x_val, 255, 0
        elif hue < 3: rc, gc, bc = 0, 255, x_val
        elif hue < 4: rc, gc, bc = 0, x_val, 255
        elif hue < 5: rc, gc, bc = x_val, 0, 255
        else:         rc, gc, bc = 255, 0, x_val
        draw.line([(bar_x1 + px, rainbow_y1), (bar_x1 + px, rainbow_y2)], fill=(rc, gc, bc, 255), width=1)
    draw.rectangle([bar_x1, rainbow_y1, bar_x2, rainbow_y2], outline=(255, 255, 255, 200), width=2)

    # 7. System Information Footer
    log("Rendering footer...")
    foot1 = "LIQUID RETINA XDR DISPLAY (3024x1964 @ 30bpp / 120Hz PROMOTION) • BARE-METAL STAGE 2 M1N1 CONTROLLER"
    foot2 = "GHOST-SILVER / CYF31415@YEAH.NET • ALL 13 MESA G16 PATCHES READY FOR ARCH LINUX ARM DEPLOYMENT"
    draw_centered_text(1830, foot1, f_foot, (180, 200, 220, 255))
    draw_centered_text(1865, foot2, f_foot, (0, 255, 160, 255))

    return img

def main():
    start_time = time.time()
    print("=" * 78)
    print("  APPLE M3 PRO (G16) CYBER TEST SCREEN RENDERER")
    print("=" * 78)

    # Disable m1n1 from printing TTY logs onto the framebuffer to prevent console wiping
    log("Disabling m1n1 framebuffer TTY console (locking display output)...")
    p.iodev_set_usage(IODEV.FB, 0)

    fb_base = u.ba.video.base
    w = u.ba.video.width
    h = u.ba.video.height
    stride = u.ba.video.stride

    print(f"[*] Target Display: {w}x{h}, Stride: {stride}, Framebuffer: {fb_base:#x}")

    # Generate full canvas image
    img = create_cyber_hud()

    # Convert to target pixel byte order for Apple 30bpp Liquid Retina XDR
    # Apple Silicon framebuffer uses 10-bit per channel RGB2101010 (m1n1 rgb2pixel_30)
    # Mapping: (b << 2) | (g << 12) | (r << 22)
    log("Packing pixel buffer into Apple 30bpp (10-bit RGB2101010) stream...")
    try:
        import numpy as np
        arr = np.array(img, dtype=np.uint8)
        r = arr[:, :, 0].astype(np.uint32)
        g = arr[:, :, 1].astype(np.uint32)
        b = arr[:, :, 2].astype(np.uint32)
        # Scale 8-bit to 10-bit with LSB replication for pristine precision
        b10 = (b << 2) | (b >> 6)
        g10 = (g << 2) | (g >> 6)
        r10 = (r << 2) | (r >> 6)
        pix30 = b10 | (g10 << 10) | (r10 << 20)
        frame_bytes = pix30.tobytes()
    except ImportError:
        # Fallback pure python converter if numpy is absent
        raw = img.convert("RGBA").tobytes()
        out = bytearray(len(raw))
        for i in range(0, len(raw), 4):
            cr, cg, cb = raw[i], raw[i+1], raw[i+2]
            b10 = (cb << 2) | (cb >> 6)
            g10 = (cg << 2) | (cg >> 6)
            r10 = (cr << 2) | (cr >> 6)
            struct.pack_into("<I", out, i, b10 | (g10 << 10) | (r10 << 20))
        frame_bytes = bytes(out)

    # Stream to M3 Pro framebuffer in bands of 64 scanlines
    log("Streaming frame to M3 Pro physical framebuffer over USB-C CDC-ACM...")
    band_lines = 64
    band_bytes = band_lines * stride
    total_bands = (h + band_lines - 1) // band_lines

    t_stream_start = time.time()
    for band_idx in range(total_bands):
        line_start = band_idx * band_lines
        line_end = min(h, line_start + band_lines)
        actual_lines = line_end - line_start

        chunk_offset = line_start * stride
        chunk_size = actual_lines * stride
        dest_addr = fb_base + chunk_offset

        chunk = frame_bytes[chunk_offset:chunk_offset + chunk_size]
        iface.writemem(dest_addr, chunk)

        if (band_idx + 1) % 5 == 0 or band_idx == total_bands - 1:
            pct = (band_idx + 1) / total_bands * 100
            print(f"  [>] Streaming progress: {pct:5.1f}% (Lines {line_start:4d} - {line_end:4d})")

    t_stream_end = time.time()
    mb_sent = len(frame_bytes) / 1024 / 1024
    stream_time = t_stream_end - t_stream_start
    rate = mb_sent / stream_time if stream_time > 0 else 0

    print("=" * 78)
    print(f"🎉 CYBER TEST SCREEN DISPLAYED LIVE ON APPLE M3 PRO SCREEN!")
    print(f"  - Total Frame Data:    {mb_sent:.2f} MiB ({w}x{h} @ 30bpp)")
    print(f"  - USB Stream Time:     {stream_time:.2f} seconds ({rate:.2f} MiB/s)")
    print(f"  - Total Execution:     {time.time() - start_time:.2f} seconds")
    print("=" * 78)

    print("[*] Screen persistence lock engaged (m1n1 FB console disabled).")
    print("[*] Holding proxy connection alive indefinitely. The screen will stay on permanently.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[*] Exiting persistence lock.")

if __name__ == "__main__":
    main()
