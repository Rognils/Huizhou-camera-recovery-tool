#!/usr/bin/env python3
"""
Extract multiple still frames with enhancement from a camera data file.

This script processes binary camera log files containing JPEG frames,
extracts them, applies image enhancement techniques, adds timestamps,
and generates MP4 videos.
"""

import os
import sys
import glob
import mmap
import argparse
import bisect
import subprocess
import io
from datetime import datetime, timezone
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
import cv2
import numpy as np
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

SOI = b"\xff\xd8"
EOI = b"\xff\xd9"

# Font cache to avoid reloading fonts
_FONT_CACHE = {}

def find_pairs(input_dir: str) -> List[Tuple[str, str]]:
    """Find all (data_file, index_file) pairs in the input directory."""
    pairs = []
    for idx_path in glob.glob(os.path.join(input_dir, "*.txt")):
        base = os.path.basename(idx_path)[:-4]
        data_path = os.path.join(input_dir, base)
        if os.path.exists(data_path) and os.path.getsize(data_path) > 0:
            pairs.append((data_path, idx_path))
    pairs.sort(key=lambda x: x[0])
    return pairs

def read_index(idx_path: str) -> List[Tuple[int, int, int]]:
    """Read index file containing timestamp, offset, and length information."""
    rows = []
    try:
        with open(idx_path) as f:
            for line in f:
                p = line.split()
                if len(p) == 3:
                    ts, off, ln = map(int, p)
                    rows.append((ts, off, ln))
        rows.sort(key=lambda x: x[1])
        return rows
    except Exception as e:
        log.error(f"Error reading index file {idx_path}: {e}")
        return []

def all_sois(mm: mmap.mmap) -> List[int]:
    """Find all SOI (Start of Image) markers in memory-mapped file."""
    res = []
    i = 0
    N = mm.size()
    while True:
        j = mm.find(SOI, i)
        if j == -1:
            break
        res.append(j)
        i = j + 2
        if i >= N:
            break
    return res

def load_font(size: int) -> ImageFont.FreeTypeFont:
    """Load a font with caching to avoid repeated file access."""
    key = size
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    ]

    for p in font_paths:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, size=size)
                _FONT_CACHE[key] = font
                return font
            except Exception as e:
                log.warning(f"Could not load font from {p}: {e}")
                continue

    # Fallback to default font
    font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font

def text_size(draw, text: str, font) -> Tuple[int, int]:
    """Get text size using modern PIL method with fallback."""
    try:
        x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
        return x1 - x0, y1 - y0
    except Exception:
        # Fallback for older PIL versions
        return draw.textsize(text, font=font)

def enhance_cv(img_bgr: np.ndarray, denoise: bool = True, sharpen: bool = True, 
              clahe: bool = True, up: int = 1, crop: Optional[Tuple[int, int, int, int]] = None) -> np.ndarray:
    """
    Apply image enhancement techniques to a BGR image.
    
    Args:
        img_bgr: Input image in BGR format
        denoise: Enable noise reduction
        sharpen: Enable unsharp mask sharpening
        clahe: Enable CLAHE (local contrast enhancement)
        up: Upscaling factor
        crop: Crop area as (x, y, w, h) or None
        
    Returns:
        Enhanced image in BGR format
    """
    # Optional crop
    if crop:
        x, y, w, h = crop
        img_bgr = img_bgr[y:y+h, x:x+w].copy()
    
    # Scale up
    if up > 1:
        img_bgr = cv2.resize(img_bgr, None, fx=up, fy=up, interpolation=cv2.INTER_LANCZOS4)
    
    # Mild denoise
    if denoise:
        img_bgr = cv2.fastNlMeansDenoisingColored(img_bgr, None, 3, 3, 7, 21)
    
    # Contrast/brightness via CLAHE
    if clahe:
        lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        cl = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
        lab = cv2.merge((cl, a, b))
        img_bgr = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    # Unsharp mask
    if sharpen:
        g = cv2.GaussianBlur(img_bgr, (0, 0), 1.0)
        img_bgr = cv2.addWeighted(img_bgr, 1.5, g, -0.5, 0)
    
    return img_bgr

def build_mp4(folder: str, fps: int, out_path: str) -> bool:
    """
    Build MP4 video from images in a folder using ffmpeg.
    
    Args:
        folder: Path to folder containing JPEG frames
        fps: Frames per second for output video
        out_path: Output path for MP4 file
        
    Returns:
        True if successful, False otherwise
    """
    pattern = os.path.join(folder, "*.jpg")
    cmd = [
        "ffmpeg", "-y", "-r", str(fps), "-pattern_type", "glob",
        "-i", pattern, "-c:v", "libx264", "-pix_fmt", "yuv420p", out_path
    ]
    
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
        return os.path.exists(out_path) and os.path.getsize(out_path) > 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        log.error(f"Failed to create video: {out_path}")
        return False

def parse_crop(s: str) -> Tuple[int, int, int, int]:
    """
    Parse crop parameter string into tuple.
    
    Args:
        s: String in format "x,y,w,h"
        
    Returns:
        Tuple of (x, y, w, h)
        
    Raises:
        argparse.ArgumentTypeError if parsing fails
    """
    try:
        return tuple(map(int, s.split(',')))
    except ValueError:
        raise argparse.ArgumentTypeError("Crop must be in format: x,y,w,h")

def process_event(data_path: str, idx_path: str, out_root: str, fps: int, stamp: bool,
                  use_utc: bool, denoise: bool, sharpen: bool, clahe: bool, up: int, 
                  crop: Optional[Tuple[int, int, int, int]]) -> None:
    """
    Process a single event (data file + index file).
    
    Args:
        data_path: Path to binary data file
        idx_path: Path to index file
        out_root: Root directory for output
        fps: FPS for output video
        stamp: Whether to add timestamps
        use_utc: Whether to use UTC time for timestamps
        denoise: Enable noise reduction
        sharpen: Enable sharpening
        clahe: Enable CLAHE
        up: Upscaling factor
        crop: Crop area as (x, y, w, h) or None
    """
    base = os.path.basename(data_path)
    evt_dir = os.path.join(out_root, base)
    os.makedirs(evt_dir, exist_ok=True)
    
    raw_dir = os.path.join(evt_dir, "frames_by_soi")
    os.makedirs(raw_dir, exist_ok=True)
    
    stamp_dir = os.path.join(evt_dir, "frames_stamped")
    if stamp:
        os.makedirs(stamp_dir, exist_ok=True)

    # Read index file
    rows = read_index(idx_path)
    if not rows:
        log.warning(f"[{base}] No valid index data.")
        return
        
    offsets = [off for (_, off, _) in rows]

    try:
        with open(data_path, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            
            sois = all_sois(mm)
            if not sois:
                log.warning(f"[{base}] Inga SOI.")
                return
                
            saved = 0
            for k, start in enumerate(sois):
                end = sois[k + 1] if k + 1 < len(sois) else mm.size()
                chunk = mm[start:end]
                
                pos_eoi = chunk.rfind(EOI)
                data = chunk[:pos_eoi + 2] if pos_eoi != -1 else chunk
                
                # Decode image
                arr = np.frombuffer(data, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                
                # Try again with EOI appended if first decode failed
                if img is None and pos_eoi == -1:
                    try:
                        arr = np.frombuffer(data + EOI, dtype=np.uint8)
                        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    except Exception:
                        pass
                
                # Skip invalid frames
                if img is None:
                    continue
                    
                # Apply enhancements
                img = enhance_cv(img, denoise=denoise, sharpen=sharpen, clahe=clahe, up=up, crop=crop)
                
                # Save raw frame
                out_raw = os.path.join(raw_dir, f"frame_{k:05d}.jpg")
                cv2.imwrite(out_raw, img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                saved += 1
                
            mm.close()
            
    except Exception as e:
        log.error(f"[{base}] Error processing event: {e}")
        return

    log.info(f"[{base}] Extracted {saved} enhanced pictures → {raw_dir}")
    if saved == 0:
        return

    # Add timestamps if requested
    src_dir = raw_dir
    if stamp:
        imgs = sorted(glob.glob(os.path.join(raw_dir, "*.jpg")))
        
        try:
            with open(data_path, "rb") as f:
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                sois = all_sois(mm)
                mm.close()
                
            for k, ip in enumerate(imgs):
                if k >= len(sois):
                    soi_pos = sois[-1]
                else:
                    soi_pos = sois[k]
                    
                j = bisect.bisect_right(offsets, soi_pos) - 1
                if j < 0:
                    j = 0
                    
                ts_ms = rows[j][0]
                dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc if use_utc else None)
                ts = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + ("Z" if use_utc else "")
                
                # Load and annotate image
                im = Image.open(ip).convert("RGB")
                W, H = im.size
                pad = int(max(W, H) * 0.015)
                fs = int(max(W, H) * 0.05)
                font = load_font(fs)
                draw = ImageDraw.Draw(im)
                
                tw, th = text_size(draw, ts, font)
                x0, y0 = pad, H - th - 2 * pad
                x1, y1 = x0 + tw + 2 * pad, H - pad
                
                # Create overlay
                overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                od = ImageDraw.Draw(overlay)
                od.rectangle([x0, y0, x1, y1], fill=(0, 0, 0, 160))
                im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
                
                # Draw timestamp
                draw = ImageDraw.Draw(im)
                draw.text((x0 + 1, y0 + 1), ts, font=font, fill=(0, 0, 0))
                draw.text((x0, y0), ts, font=font, fill=(255, 255, 255))
                
                # Save timestamped image
                outp = os.path.join(stamp_dir, f"frame_{k:05d}_{ts_ms}.jpg")
                im.save(outp, "JPEG", quality=95)
                
        except Exception as e:
            log.error(f"[{base}] Error adding timestamps: {e}")
            
        log.info(f"[{base}] Timestamped {len(imgs)} pictures → {stamp_dir}")
        src_dir = stamp_dir

    # Build MP4 video
    mp4 = os.path.join(evt_dir, f"out_stamped_{fps}fps.mp4" if stamp else f"out_{fps}fps.mp4")
    ok = build_mp4(src_dir, fps, mp4)
    
    if ok:
        log.info(f"[{base}] Video: {mp4}")
    else:
        log.error(f"[{base}] Could not create video.")

def main():
    """Main entry point for the script."""
    ap = argparse.ArgumentParser(
        description="Extract multiple still frames with enhancement from a camera data file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input /path/to/data
  %(prog)s --input /path/to/data --fps 30 --no-stamp --utc --up 2 --crop 100,50,640,480
        """
    )
    
    ap.add_argument("--input", default=".", help="Folder containing data file + .txt (default: .)")
    ap.add_argument("--fps", type=int, default=25, help="FPS for output video")
    ap.add_argument("--no-stamp", action="store_true", help="Skip timestamp overlay on images")
    ap.add_argument("--utc", action="store_true", help="Use UTC time for timestamps")
    ap.add_argument("--up", type=int, default=1, help="Upscale factor (1=none, 2=2x, 3=3x)")
    ap.add_argument("--crop", type=parse_crop, help="Crop area: x,y,w,h (e.g. 200,120,500,400)")
    ap.add_argument("--no-denoise", action="store_true", help="Disable noise reduction")
    ap.add_argument("--no-sharpen", action="store_true", help="Disable sharpening")
    ap.add_argument("--no-clahe", action="store_true", help="Disable CLAHE (local contrast enhancement)")
    
    args = ap.parse_args()

    input_dir = os.path.abspath(args.input)
    pairs = find_pairs(input_dir)
    
    if not pairs:
        log.error("[!] Did not find any (data, .txt)-pair.")
        sys.exit(1)

    out_root = os.path.join(input_dir, "output")
    os.makedirs(out_root, exist_ok=True)
    log.info(f"[*] Found {len(pairs)} data files. Working...")

    for data_path, idx_path in pairs:
        process_event(
            data_path, idx_path, out_root, args.fps,
            stamp=(not args.no_stamp), use_utc=args.utc,
            denoise=(not args.no_denoise), sharpen=(not args.no_sharpen),
            clahe=(not args.no_clahe), up=max(1, args.up), crop=args.crop
        )
    
    log.info("[✓] Done.")

if __name__ == "__main__":
    main()

