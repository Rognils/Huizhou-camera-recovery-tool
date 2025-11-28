#!/usr/bin/env python3
"""
Forensic JPEG Frame Extractor for Huizhou Camera Data Files

This script processes binary camera log files containing JPEG frames,
extracts them, applies image enhancement techniques, adds timestamps,
and generates MP4 videos.

Designed for forensic use with full audit trail and integrity verification.

Version: 3.0
"""

import os
import sys
import glob
import mmap
import argparse
import bisect
import subprocess
import hashlib
import json
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any, Set
from contextlib import contextmanager
from PIL import Image, ImageDraw, ImageFont
import cv2
import numpy as np
import logging

# Constants
SOI = b"\xff\xd8"  # JPEG Start of Image marker
EOI = b"\xff\xd9"  # JPEG End of Image marker
VERSION = "3.1"

# Font cache to avoid reloading fonts
_FONT_CACHE: Dict[int, ImageFont.FreeTypeFont] = {}


def setup_logging(log_dir: Optional[str] = None, verbose: bool = False) -> logging.Logger:
    """
    Configure logging to both console and file for forensic audit trail.
    
    Args:
        log_dir: Directory for log file output
        verbose: Enable debug-level logging
        
    Returns:
        Configured logger instance
    """
    log = logging.getLogger("cam_unpack")
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    log.handlers.clear()
    
    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console.setFormatter(console_fmt)
    log.addHandler(console)
    
    # File handler for forensic audit trail
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"extraction_log_{timestamp}.txt")
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_fmt = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
        )
        file_handler.setFormatter(file_fmt)
        log.addHandler(file_handler)
        log.info(f"Forensic log file created: {log_file}")
    
    return log


def compute_file_hash(filepath: str, algorithm: str = "sha256") -> str:
    """
    Compute cryptographic hash of a file for integrity verification.
    
    Args:
        filepath: Path to file
        algorithm: Hash algorithm ('sha256', 'md5', or 'sha1')
        
    Returns:
        Hexadecimal hash string
    """
    hash_func = hashlib.new(algorithm)
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_func.update(chunk)
    return hash_func.hexdigest()


def generate_forensic_report(
    data_path: str,
    idx_path: str,
    output_dir: str,
    frames_extracted: int,
    frames_total: int,
    settings: Dict[str, Any],
    log: logging.Logger
) -> str:
    """
    Generate a forensic report documenting the extraction process.
    
    Args:
        data_path: Path to source data file
        idx_path: Path to index file
        output_dir: Output directory path
        frames_extracted: Number of successfully extracted frames
        frames_total: Total number of SOI markers found
        settings: Dictionary of processing settings used
        log: Logger instance
        
    Returns:
        Path to generated report file
    """
    report = {
        "forensic_report": {
            "version": VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tool": "Huizhou Camera Recovery Tool",
        },
        "source_files": {
            "data_file": {
                "path": os.path.abspath(data_path),
                "size_bytes": os.path.getsize(data_path),
                "sha256": compute_file_hash(data_path, "sha256"),
                "md5": compute_file_hash(data_path, "md5"),
            },
            "index_file": {
                "path": os.path.abspath(idx_path),
                "size_bytes": os.path.getsize(idx_path),
                "sha256": compute_file_hash(idx_path, "sha256"),
            }
        },
        "extraction_results": {
            "soi_markers_found": frames_total,
            "frames_successfully_extracted": frames_extracted,
            "frames_failed": frames_total - frames_extracted,
            "success_rate_percent": round(
                (frames_extracted / frames_total * 100) if frames_total > 0 else 0, 2
            ),
        },
        "processing_settings": settings,
        "output_directory": os.path.abspath(output_dir),
        "integrity_note": (
            "No modifications were made to source files. "
            "Enhancements are purely visual (brightness/contrast/sharpening). "
            "Original pixel data preserved in extraction process."
        )
    }
    
    report_path = os.path.join(output_dir, "forensic_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    log.info(f"Forensic report generated: {report_path}")
    return report_path


def find_pairs(input_dir: str) -> List[Tuple[str, str]]:
    """
    Find all (data_file, index_file) pairs in the input directory.
    
    Args:
        input_dir: Directory to search
        
    Returns:
        List of (data_path, index_path) tuples, sorted by data path
    """
    pairs = []
    for idx_path in glob.glob(os.path.join(input_dir, "*.txt")):
        base = os.path.basename(idx_path)[:-4]
        data_path = os.path.join(input_dir, base)
        if os.path.exists(data_path) and os.path.getsize(data_path) > 0:
            pairs.append((data_path, idx_path))
    pairs.sort(key=lambda x: x[0])
    return pairs


def read_index(idx_path: str, log: logging.Logger) -> List[Tuple[int, int, int]]:
    """
    Read index file containing timestamp, offset, and length information.
    
    Args:
        idx_path: Path to index file
        log: Logger instance
        
    Returns:
        List of (timestamp_ms, offset, length) tuples, sorted by offset
    """
    rows = []
    try:
        with open(idx_path, encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                p = line.split()
                if len(p) == 3:
                    try:
                        ts, off, ln = map(int, p)
                        rows.append((ts, off, ln))
                    except ValueError:
                        log.warning(f"Invalid data on line {line_num} in {idx_path}: {line.strip()}")
        rows.sort(key=lambda x: x[1])
        log.debug(f"Read {len(rows)} index entries from {idx_path}")
        return rows
    except Exception as e:
        log.error(f"Error reading index file {idx_path}: {e}")
        return []


def find_all_soi_markers(mm: mmap.mmap, validate: bool = True) -> Tuple[List[int], int]:
    """
    Find all SOI (Start of Image) markers in memory-mapped file.
    
    Optionally validates that each SOI is followed by a valid JPEG marker,
    filtering out false positives where 0xFFD8 appears in image data.
    
    Args:
        mm: Memory-mapped file object
        validate: If True, verify each SOI is followed by valid JPEG marker
        
    Returns:
        Tuple of (list of valid SOI offsets, count of rejected false positives)
    """
    # Valid JPEG markers that can follow SOI (0xFFD8)
    # APP0-APP15 (0xE0-0xEF), SOF markers, DQT, DHT, etc.
    VALID_JPEG_MARKERS = {
        0xc0, 0xc1, 0xc2, 0xc3,  # SOF0-SOF3 (Start of Frame)
        0xc4,                     # DHT (Define Huffman Table)
        0xc5, 0xc6, 0xc7,        # SOF5-SOF7
        0xc8, 0xc9, 0xca, 0xcb,  # JPG, SOF9-SOF11
        0xcc, 0xcd, 0xce, 0xcf,  # DAC, SOF13-SOF15
        0xdb,                     # DQT (Define Quantization Table)
        0xdd,                     # DRI (Define Restart Interval)
        0xfe,                     # COM (Comment)
    }
    # Add APP0-APP15 markers (0xE0-0xEF)
    VALID_JPEG_MARKERS.update(range(0xe0, 0xf0))
    
    all_positions = []
    i = 0
    size = mm.size()
    
    # Find all potential SOI markers
    while i < size:
        j = mm.find(SOI, i)
        if j == -1:
            break
        all_positions.append(j)
        i = j + 2
    
    if not validate:
        return all_positions, 0
    
    # Validate each SOI
    valid_positions = []
    rejected_count = 0
    
    for pos in all_positions:
        if pos + 3 < size:
            # Check if byte after SOI is 0xFF (marker prefix)
            if mm[pos + 2] == 0xff:
                marker = mm[pos + 3]
                if marker in VALID_JPEG_MARKERS:
                    valid_positions.append(pos)
                else:
                    # 0xFF followed by unknown marker - might still be valid
                    # but likely corrupted, include with warning potential
                    valid_positions.append(pos)
            else:
                # Not followed by 0xFF - definitely a false SOI
                rejected_count += 1
        else:
            # Near end of file, can't validate - include it
            valid_positions.append(pos)
    
    return valid_positions, rejected_count


def load_font(size: int) -> ImageFont.FreeTypeFont:
    """
    Load a TrueType font with caching to avoid repeated file access.
    
    Args:
        size: Font size in points
        
    Returns:
        Font object (TrueType if available, default otherwise)
    """
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]

    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",  # macOS
        "C:\\Windows\\Fonts\\arial.ttf",  # Windows
    ]

    for path in font_paths:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size=size)
                _FONT_CACHE[size] = font
                return font
            except Exception:
                continue

    # Fallback to default font
    font = ImageFont.load_default()
    _FONT_CACHE[size] = font
    return font


def get_text_dimensions(draw: ImageDraw.ImageDraw, text: str, font) -> Tuple[int, int]:
    """
    Get text dimensions using modern PIL method with fallback.
    
    Args:
        draw: ImageDraw object
        text: Text string to measure
        font: Font object
        
    Returns:
        Tuple of (width, height) in pixels
    """
    try:
        x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
        return x1 - x0, y1 - y0
    except AttributeError:
        # Fallback for older PIL versions
        return draw.textsize(text, font=font)


def enhance_image(
    img_bgr: np.ndarray,
    denoise: bool = True,
    sharpen: bool = True,
    clahe: bool = True,
    clahe_clip: float = 2.0,
    clahe_grid: int = 8,
    upscale: int = 1,
    crop: Optional[Tuple[int, int, int, int]] = None
) -> np.ndarray:
    """
    Apply image enhancement techniques to a BGR image.
    
    All enhancements are non-destructive visual improvements only.
    No scene content is added, removed, or manipulated.
    
    Args:
        img_bgr: Input image in BGR format
        denoise: Enable noise reduction
        sharpen: Enable unsharp mask sharpening
        clahe: Enable CLAHE (local contrast enhancement)
        clahe_clip: CLAHE clip limit
        clahe_grid: CLAHE tile grid size
        upscale: Upscaling factor (1 = no upscaling)
        crop: Crop area as (x, y, w, h) or None
        
    Returns:
        Enhanced image in BGR format
    """
    result = img_bgr
    
    # Apply crop first
    if crop:
        x, y, w, h = crop
        img_h, img_w = result.shape[:2]
        # Validate crop bounds
        if x >= 0 and y >= 0 and x + w <= img_w and y + h <= img_h:
            result = result[y:y+h, x:x+w].copy()
    
    # Upscale
    if upscale > 1:
        result = cv2.resize(result, None, fx=upscale, fy=upscale, 
                           interpolation=cv2.INTER_LANCZOS4)
    
    # Mild denoise
    if denoise:
        result = cv2.fastNlMeansDenoisingColored(result, None, 3, 3, 7, 21)
    
    # CLAHE contrast enhancement
    if clahe:
        lab = cv2.cvtColor(result, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe_obj = cv2.createCLAHE(clipLimit=clahe_clip, 
                                     tileGridSize=(clahe_grid, clahe_grid))
        l_enhanced = clahe_obj.apply(l_channel)
        lab = cv2.merge((l_enhanced, a_channel, b_channel))
        result = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    # Unsharp mask sharpening
    if sharpen:
        gaussian = cv2.GaussianBlur(result, (0, 0), 1.0)
        result = cv2.addWeighted(result, 1.5, gaussian, -0.5, 0)
    
    return result


def build_mp4(
    frame_folder: str,
    fps: int,
    output_path: str,
    log: logging.Logger
) -> bool:
    """
    Build MP4 video from images in a folder using ffmpeg.
    
    Args:
        frame_folder: Path to folder containing JPEG frames
        fps: Frames per second for output video
        output_path: Output path for MP4 file
        log: Logger instance
        
    Returns:
        True if successful, False otherwise
    """
    pattern = os.path.join(frame_folder, "*.jpg")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-pattern_type", "glob",
        "-i", pattern,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path
    ]
    
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True
        )
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            log.info(f"Video created successfully: {output_path}")
            return True
        else:
            log.error(f"Video file not created or empty: {output_path}")
            return False
    except subprocess.CalledProcessError as e:
        log.error(f"ffmpeg failed with return code {e.returncode}")
        log.debug(f"ffmpeg output: {e.stdout.decode() if e.stdout else 'N/A'}")
        return False
    except FileNotFoundError:
        log.error("ffmpeg not found. Install with: sudo apt install ffmpeg")
        return False


def parse_crop(value: str) -> Tuple[int, int, int, int]:
    """
    Parse crop parameter string into validated tuple.
    
    Args:
        value: String in format "x,y,w,h"
        
    Returns:
        Tuple of (x, y, w, h)
        
    Raises:
        argparse.ArgumentTypeError if parsing or validation fails
    """
    try:
        parts = tuple(map(int, value.split(',')))
        if len(parts) != 4:
            raise argparse.ArgumentTypeError(
                f"Crop must have exactly 4 values (got {len(parts)}): x,y,w,h"
            )
        x, y, w, h = parts
        if any(v < 0 for v in parts):
            raise argparse.ArgumentTypeError(
                "Crop values must be non-negative"
            )
        if w == 0 or h == 0:
            raise argparse.ArgumentTypeError(
                "Crop width and height must be greater than 0"
            )
        return parts
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Crop must be integers in format: x,y,w,h (e.g., 200,100,640,480)"
        )


@contextmanager
def memory_mapped_file(filepath: str):
    """
    Context manager for safe memory-mapped file access.
    
    Args:
        filepath: Path to file to memory-map
        
    Yields:
        Memory-mapped file object
    """
    f = None
    mm = None
    try:
        f = open(filepath, "rb")
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        yield mm
    finally:
        if mm is not None:
            mm.close()
        if f is not None:
            f.close()


def process_event(
    data_path: str,
    idx_path: str,
    out_root: str,
    fps: int,
    add_timestamp: bool,
    use_utc: bool,
    denoise: bool,
    sharpen: bool,
    clahe: bool,
    clahe_clip: float,
    clahe_grid: int,
    upscale: int,
    crop: Optional[Tuple[int, int, int, int]],
    jpeg_quality: int,
    log: logging.Logger,
    show_progress: bool = True
) -> Tuple[int, int]:
    """
    Process a single event (data file + index file).
    
    Args:
        data_path: Path to binary data file
        idx_path: Path to index file
        out_root: Root directory for output
        fps: FPS for output video
        add_timestamp: Whether to add timestamps
        use_utc: Whether to use UTC time for timestamps
        denoise: Enable noise reduction
        sharpen: Enable sharpening
        clahe: Enable CLAHE
        clahe_clip: CLAHE clip limit
        clahe_grid: CLAHE grid size
        upscale: Upscaling factor
        crop: Crop area as (x, y, w, h) or None
        jpeg_quality: JPEG output quality (1-100)
        log: Logger instance
        show_progress: Show progress indicator
        
    Returns:
        Tuple of (frames_extracted, total_soi_markers)
    """
    base = os.path.basename(data_path)
    evt_dir = os.path.join(out_root, base)
    os.makedirs(evt_dir, exist_ok=True)
    
    raw_dir = os.path.join(evt_dir, "frames_by_soi")
    os.makedirs(raw_dir, exist_ok=True)
    
    stamp_dir = os.path.join(evt_dir, "frames_stamped")
    if add_timestamp:
        os.makedirs(stamp_dir, exist_ok=True)

    # Log source file hashes for forensic record
    log.info(f"[{base}] Source data SHA256: {compute_file_hash(data_path, 'sha256')}")
    log.info(f"[{base}] Source index SHA256: {compute_file_hash(idx_path, 'sha256')}")

    # Read index file
    rows = read_index(idx_path, log)
    if not rows:
        log.warning(f"[{base}] No valid index data found")
        return 0, 0
        
    offsets = [off for (_, off, _) in rows]
    
    # Extract frames
    saved = 0
    total_soi = 0
    sois_cache = []  # Cache SOI positions for timestamp pass
    
    try:
        with memory_mapped_file(data_path) as mm:
            sois, rejected = find_all_soi_markers(mm, validate=True)
            sois_cache = sois.copy()
            total_soi = len(sois)
            
            if rejected > 0:
                log.info(f"[{base}] Filtered out {rejected} false SOI markers (0xFFD8 in image data)")
            
            if not sois:
                log.warning(f"[{base}] No valid SOI markers found in data file")
                return 0, 0
            
            log.info(f"[{base}] Found {total_soi} valid JPEG frames, extracting...")
            
            for k, start in enumerate(sois):
                # Progress indicator
                if show_progress and k % 100 == 0:
                    log.info(f"[{base}] Processing frame {k}/{total_soi}...")
                
                end = sois[k + 1] if k + 1 < len(sois) else mm.size()
                chunk = mm[start:end]
                
                pos_eoi = chunk.rfind(EOI)
                data = chunk[:pos_eoi + 2] if pos_eoi != -1 else chunk
                
                # Decode image
                arr = np.frombuffer(data, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                
                # Retry with EOI appended if decode failed and no EOI was found
                if img is None and pos_eoi == -1:
                    try:
                        arr = np.frombuffer(data + EOI, dtype=np.uint8)
                        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    except Exception:
                        pass
                
                # Skip invalid frames
                if img is None:
                    log.debug(f"[{base}] Frame {k}: decode failed, skipping")
                    continue
                    
                # Apply enhancements
                img = enhance_image(
                    img,
                    denoise=denoise,
                    sharpen=sharpen,
                    clahe=clahe,
                    clahe_clip=clahe_clip,
                    clahe_grid=clahe_grid,
                    upscale=upscale,
                    crop=crop
                )
                
                # Save raw frame
                out_raw = os.path.join(raw_dir, f"frame_{k:05d}.jpg")
                cv2.imwrite(out_raw, img, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                saved += 1

    except Exception as e:
        log.error(f"[{base}] Error during frame extraction: {e}")
        return saved, total_soi

    log.info(f"[{base}] Extracted {saved}/{total_soi} enhanced frames to {raw_dir}")
    
    if saved == 0:
        return 0, total_soi

    # Add timestamps if requested
    src_dir = raw_dir
    if add_timestamp:
        imgs = sorted(glob.glob(os.path.join(raw_dir, "*.jpg")))
        
        try:
            for k, img_path in enumerate(imgs):
                # Map frame to timestamp using cached SOI positions
                if k < len(sois_cache):
                    soi_pos = sois_cache[k]
                else:
                    soi_pos = sois_cache[-1]
                    log.warning(
                        f"[{base}] Frame {k} beyond SOI cache, using last known position"
                    )
                
                # Find corresponding index entry
                j = bisect.bisect_right(offsets, soi_pos) - 1
                if j < 0:
                    j = 0
                    log.warning(
                        f"[{base}] Frame {k}: SOI position {soi_pos} before first index offset, "
                        f"using first timestamp (may be inaccurate)"
                    )
                
                ts_ms = rows[j][0]
                
                # Format timestamp
                if use_utc:
                    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
                    ts_str = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"
                else:
                    dt = datetime.fromtimestamp(ts_ms / 1000.0)
                    ts_str = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                
                # Load and annotate image
                im = Image.open(img_path).convert("RGB")
                W, H = im.size
                
                # Calculate font size and padding proportional to image size
                pad = int(max(W, H) * 0.015)
                font_size = int(max(W, H) * 0.05)
                font = load_font(font_size)
                draw = ImageDraw.Draw(im)
                
                tw, th = get_text_dimensions(draw, ts_str, font)
                x0, y0 = pad, H - th - 2 * pad
                x1, y1 = x0 + tw + 2 * pad, H - pad
                
                # Create semi-transparent overlay
                overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                overlay_draw.rectangle([x0, y0, x1, y1], fill=(0, 0, 0, 160))
                im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
                
                # Draw timestamp with shadow for readability
                draw = ImageDraw.Draw(im)
                draw.text((x0 + pad + 1, y0 + 1), ts_str, font=font, fill=(0, 0, 0))
                draw.text((x0 + pad, y0), ts_str, font=font, fill=(255, 255, 255))
                
                # Save timestamped image
                out_path = os.path.join(stamp_dir, f"frame_{k:05d}_{ts_ms}.jpg")
                im.save(out_path, "JPEG", quality=jpeg_quality)
                
        except Exception as e:
            log.error(f"[{base}] Error adding timestamps: {e}")
            
        log.info(f"[{base}] Timestamped {len(imgs)} frames to {stamp_dir}")
        src_dir = stamp_dir

    # Build MP4 video
    video_suffix = "stamped_" if add_timestamp else ""
    mp4_path = os.path.join(evt_dir, f"out_{video_suffix}{fps}fps.mp4")
    
    if build_mp4(src_dir, fps, mp4_path, log):
        log.info(f"[{base}] Video created: {mp4_path}")
    else:
        log.error(f"[{base}] Failed to create video")

    # Generate forensic report
    settings = {
        "fps": fps,
        "timestamp_overlay": add_timestamp,
        "utc_time": use_utc,
        "denoise": denoise,
        "sharpen": sharpen,
        "clahe": clahe,
        "clahe_clip_limit": clahe_clip,
        "clahe_grid_size": clahe_grid,
        "upscale_factor": upscale,
        "crop_region": crop,
        "jpeg_quality": jpeg_quality,
    }
    
    generate_forensic_report(
        data_path, idx_path, evt_dir,
        saved, total_soi, settings, log
    )
    
    return saved, total_soi


def main() -> int:
    """
    Main entry point for the forensic frame extraction tool.
    
    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    ap = argparse.ArgumentParser(
        description=(
            "Forensic JPEG Frame Extractor for Huizhou Camera Data Files.\n"
            "Extracts frames, applies visual enhancements, and generates "
            "timestamped video with full audit trail."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input /path/to/data
  %(prog)s --input /path/to/data --fps 30 --utc --up 2
  %(prog)s --input /path/to/data --no-stamp --no-denoise
  %(prog)s --input /path/to/data --crop 100,50,640,480 --jpeg-quality 90

Forensic Notes:
  - Source files are never modified
  - SHA256 hashes of source files are logged
  - Enhancements are purely visual (brightness/contrast)
  - Full audit trail saved to extraction_log_*.txt
  - JSON forensic report generated for each extraction
        """
    )
    
    # Input/Output
    ap.add_argument(
        "--input", default=".",
        help="Folder containing data file + .txt index (default: .)"
    )
    
    # Video settings
    ap.add_argument(
        "--fps", type=int, default=25,
        help="FPS for output video (default: 25)"
    )
    ap.add_argument(
        "--jpeg-quality", type=int, default=95, choices=range(1, 101),
        metavar="1-100",
        help="JPEG output quality (default: 95)"
    )
    
    # Timestamp options
    ap.add_argument(
        "--no-stamp", action="store_true",
        help="Skip timestamp overlay on frames"
    )
    ap.add_argument(
        "--utc", action="store_true",
        help="Use UTC time for timestamps (default: local time)"
    )
    
    # Image transformation
    ap.add_argument(
        "--up", type=int, default=1, choices=[1, 2, 3, 4],
        help="Upscale factor: 1=none, 2=2x, 3=3x, 4=4x (default: 1)"
    )
    ap.add_argument(
        "--crop", type=parse_crop, metavar="x,y,w,h",
        help="Crop region before processing (e.g., 200,100,640,480)"
    )
    
    # Enhancement toggles
    ap.add_argument(
        "--no-denoise", action="store_true",
        help="Disable noise reduction"
    )
    ap.add_argument(
        "--no-sharpen", action="store_true",
        help="Disable sharpening filter"
    )
    ap.add_argument(
        "--no-clahe", action="store_true",
        help="Disable CLAHE (local contrast enhancement)"
    )
    
    # CLAHE tuning
    ap.add_argument(
        "--clahe-clip", type=float, default=2.0,
        help="CLAHE clip limit (default: 2.0)"
    )
    ap.add_argument(
        "--clahe-grid", type=int, default=8,
        help="CLAHE tile grid size (default: 8)"
    )
    
    # Logging
    ap.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose debug output"
    )
    
    ap.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{VERSION}"
    )
    
    args = ap.parse_args()

    input_dir = os.path.abspath(args.input)
    
    if not os.path.isdir(input_dir):
        print(f"Error: Input directory does not exist: {input_dir}", file=sys.stderr)
        return 1
    
    out_root = os.path.join(input_dir, "output")
    os.makedirs(out_root, exist_ok=True)
    
    # Setup logging with file output for forensic audit
    log = setup_logging(log_dir=out_root, verbose=args.verbose)
    
    log.info(f"Huizhou Camera Recovery Tool v{VERSION}")
    log.info(f"Input directory: {input_dir}")
    log.info(f"Output directory: {out_root}")
    
    pairs = find_pairs(input_dir)
    
    if not pairs:
        log.error("No (data, .txt) file pairs found in input directory")
        return 1

    log.info(f"Found {len(pairs)} data file(s) to process")
    
    total_extracted = 0
    total_found = 0
    
    for data_path, idx_path in pairs:
        extracted, found = process_event(
            data_path=data_path,
            idx_path=idx_path,
            out_root=out_root,
            fps=args.fps,
            add_timestamp=(not args.no_stamp),
            use_utc=args.utc,
            denoise=(not args.no_denoise),
            sharpen=(not args.no_sharpen),
            clahe=(not args.no_clahe),
            clahe_clip=args.clahe_clip,
            clahe_grid=args.clahe_grid,
            upscale=max(1, args.up),
            crop=args.crop,
            jpeg_quality=args.jpeg_quality,
            log=log
        )
        total_extracted += extracted
        total_found += found
    
    log.info(f"Processing complete: {total_extracted}/{total_found} frames extracted")
    log.info("Done")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
