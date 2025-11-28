# Huizhou Camera Recovery Tool

**Current version: v3.1**  
See changes in 👉 [CHANGELOG.md](CHANGELOG.md)

A **forensic-grade** Python tool for recovering JPEG frames from proprietary camera data files, reconstructing timestamps, enhancing clarity, and exporting image sequences and playable MP4 video.

---

## 📷 Supported Hardware

- **Camera Model**: HX-K0004A-S7 (may work on other Huizhou models)
- **Manufacturer**: Huizhou Huaxinwei Technology Co., Ltd. (China)
- **Note**: This device saves footage in a proprietary raw format (not MP4/AVI), accompanied by a `.txt` index file. Standard players like VLC cannot open these files directly.

---

## ✨ Features

### Core Functionality
- Extracts JPEG frames from raw binary camera files
- Restores correct timestamps using accompanying `.txt` index files
- Generates both chronological image folders and MP4 video

### Image Enhancement (Optional)
- Noise reduction (fastNlMeansDenoisingColored)
- Local contrast enhancement (CLAHE)
- Sharpening (Unsharp mask)
- Upscaling (1x-4x with Lanczos interpolation)
- Region cropping

### Forensic Features (v3.0)
- **SHA256/MD5 hashes** of source files computed and logged
- **JSON forensic report** generated for each extraction
- **Timestamped audit log** saved to file
- **Non-destructive processing** - source files never modified
- **Reproducible results** - all settings documented

---

## 📦 Installation

### Dependencies

```bash
# Ubuntu/Debian
sudo apt install ffmpeg python3-opencv
python3 -m pip install pillow

# macOS (Homebrew)
brew install ffmpeg opencv
pip3 install pillow

# Windows (requires Python 3.8+)
pip install opencv-python pillow
# Install ffmpeg from https://ffmpeg.org/download.html
```

---

## 🚀 Usage

### File Structure

Place the script in the folder containing the raw files:

```
1710765741314        ← Raw camera data (no extension)
1710765741314.txt    ← Timestamp/offset index file
cam_unpack_focus.py  ← The extraction script
```

### Basic Examples

```bash
# Standard extraction with enhancements and timestamps
python3 cam_unpack_focus.py --input . --fps 25

# 2x upscale with UTC timestamps
python3 cam_unpack_focus.py --input . --fps 25 --up 2 --utc

# Raw extraction (no enhancements)
python3 cam_unpack_focus.py --input . --no-denoise --no-sharpen --no-clahe

# Skip timestamp overlay
python3 cam_unpack_focus.py --input . --no-stamp

# Crop specific region
python3 cam_unpack_focus.py --input . --crop 200,100,600,400

# Custom CLAHE settings
python3 cam_unpack_focus.py --input . --clahe-clip 3.0 --clahe-grid 16

# Verbose output for debugging
python3 cam_unpack_focus.py --input . --verbose
```

---

## ⚙️ Command Reference

| Flag | Description | Default |
|------|-------------|---------|
| `--input PATH` | Folder containing data and index files | `.` |
| `--fps N` | Frames per second for output video | `25` |
| `--jpeg-quality N` | JPEG output quality (1-100) | `95` |
| `--no-stamp` | Skip timestamp overlay | Off |
| `--utc` | Use UTC timestamps | Local time |
| `--up N` | Upscale factor (1-4) | `1` |
| `--crop x,y,w,h` | Crop region before processing | None |
| `--no-denoise` | Disable noise reduction | Off |
| `--no-sharpen` | Disable sharpening | Off |
| `--no-clahe` | Disable CLAHE contrast | Off |
| `--clahe-clip N` | CLAHE clip limit | `2.0` |
| `--clahe-grid N` | CLAHE tile grid size | `8` |
| `--verbose`, `-v` | Enable debug output | Off |
| `--version` | Show version and exit | - |

---

## 📁 Output Structure

```
output/
└── 1710765741314/
    ├── frames_by_soi/           ← Extracted/enhanced frames
    ├── frames_stamped/          ← Timestamped frames
    ├── out_stamped_25fps.mp4    ← Reconstructed video
    └── forensic_report.json     ← Forensic documentation

output/
└── extraction_log_20250528_143022.txt  ← Audit trail
```

---

## 🔒 Forensic Report

Each extraction generates a `forensic_report.json` containing:

```json
{
  "forensic_report": {
    "version": "3.0",
    "generated_at": "2025-05-28T14:30:22.123456+00:00",
    "tool": "Huizhou Camera Recovery Tool"
  },
  "source_files": {
    "data_file": {
      "path": "/absolute/path/to/1710765741314",
      "size_bytes": 52428800,
      "sha256": "a1b2c3d4...",
      "md5": "e5f6g7h8..."
    },
    "index_file": {
      "path": "/absolute/path/to/1710765741314.txt",
      "size_bytes": 4096,
      "sha256": "i9j0k1l2..."
    }
  },
  "extraction_results": {
    "soi_markers_found": 1250,
    "frames_successfully_extracted": 1247,
    "frames_failed": 3,
    "success_rate_percent": 99.76
  },
  "processing_settings": {
    "fps": 25,
    "denoise": true,
    "sharpen": true,
    "clahe": true,
    "upscale_factor": 2
  },
  "integrity_note": "No modifications were made to source files..."
}
```

---

## ⚖️ Forensic Integrity Statement

This tool is designed for investigative and evidence use:

| Aspect | Guarantee |
|--------|-----------|
| **Source Preservation** | Original files are never modified |
| **Audit Trail** | All operations logged with timestamps |
| **Hash Verification** | SHA256/MD5 computed before processing |
| **Visual Enhancement Only** | No objects added/removed from scenes |
| **Reproducibility** | Settings documented for verification |

---

## 🔧 Troubleshooting

| Message | Solution |
|---------|----------|
| `No SOI markers found` | File may be corrupted or different format |
| `ffmpeg not found` | Install: `sudo apt install ffmpeg` |
| `0 frames extracted` | Check index file format matches expected |
| `Corrupt JPEG data` | Normal - camera adds extra bytes, frames still valid |
| `SOI position before first index offset` | Timestamp may be approximate for early frames |

---

## 💻 Platform Support

| OS | Status |
|----|--------|
| Ubuntu / Linux Mint | ✅ Stable |
| macOS | ✅ Works with Homebrew |
| Windows | ⚠️ Requires ffmpeg in PATH |
| Windows (WSL) | ✅ Recommended for Windows |

---

## 📜 License

Free to use for forensic, research, and security work.  
Attribution appreciated. No warranty on recovery success.

---

## 🤝 Contributing

Contributions welcome for:
- Additional camera model support
- Face detection/tracking
- Evidence PDF generation
- Auto-cropping of subjects
