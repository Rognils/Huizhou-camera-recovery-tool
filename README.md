- [Changelog](CHANGELOG.md)


# Camera Raw File Frame Extractor & Rebuilder

A forensic-grade Python tool for recovering JPEG frames from proprietary camera data files, reconstructing timestamps, enhancing clarity, and exporting image sequences and playable MP4 video.

## 🔧 Camera Information (Manufacturer & Model)

- **Camera Model:** HX-K0004A-S7 (Could work on other models as well from Huizhou) 
- **Manufacturer:** Huizhou Huaxinwei Technology Co., Ltd. (China)  
- **Note:** This device saves footage in a **proprietary raw format** (not MP4/AVI), accompanied by a `.txt` index file. Standard players like VLC cannot open these files directly, which is why a custom extraction process is required.

## 🔍 Features

- Extracts JPEG frames from raw binary camera files (unreadable in VLC/MP4 players)
- Restores correct timestamps using accompanying `.txt` index files
- Optional image enhancement (denoise, local contrast/CLAHE, sharpening, upscale)
- Generates both chronological image folders and MP4 video
- Suitable for investigation, evidence recovery, and CCTV analysis

## 🗂 Required Folder Structure

Place the python script the folder containing the raw files:

```
1710765741314        ← Raw camera data (no extension)
1710765741314.txt    ← Timestamp/offset index file
cam_unpack_focus.py  ← The extraction script
```

## 🛠 Installation

Install dependencies:

```bash
sudo apt install ffmpeg python3-opencv
python3 -m pip install pillow
```

## 🚀 Usage Examples

### Recommended (timestamped, enhanced, video 25 FPS)

```bash
python3 cam_unpack_focus.py --input . --fps 25 --up 2
```

### Maximum raw frames (no enhancement)

```bash
python3 cam_unpack_focus.py --input . --fps 25 --up 1 --no-denoise --no-sharpen --no-clahe
```

### Extract images only (no timestamps, no video)

```bash
python3 cam_unpack_focus.py --input . --no-stamp --up 1
```

### Crop around subject (x,y,width,height)

```bash
python3 cam_unpack_focus.py --input . --fps 25 --up 2 --crop 200,100,600,400
```

## ⚙️ Command-Line Flags

| Flag | Description |
|------|-------------|
| `--input PATH` | Folder containing the raw data file and its matching `.txt` index file (default: `.`) |
| `--fps N` | Frames per second for the output video (default: `25`) |
| `--no-stamp` | Skip timestamp overlay on frames |
| `--utc` | Use UTC timestamps instead of local time |
| `--up N` | Upscaling factor: `1 = none`, `2 = 2×`, `3 = 3×` |
| `--crop x,y,w,h` | Crop a specific region before export (e.g. `--crop 200,100,600,400`) |
| `--no-denoise` | Disable noise reduction |
| `--no-sharpen` | Disable sharpening filter |
| `--no-clahe` | Disable CLAHE (local contrast enhancement) |

## 📁 Output Structure

```
output/
 └── 1710765741314/
     ├── frames_by_soi/        ← Extracted / enhanced frames
     ├── frames_stamped/       ← Timestamped frames
     └── out_stamped_25fps.mp4 ← Reconstructed video
```

## 🛡 Evidence Integrity

- No scenes manipulated (no objects added or removed)
- Enhancements are only visual (brightness/clarity)
- Timestamps sourced from original index data
- Suitable for investigative/legal use

## ⚠ Common Messages

| Message | Meaning |
|---------|---------|
| `Corrupt JPEG data` | Normal – extra bytes from camera, image still valid |
| `0 frames extracted` | Unsupported format or missing index file |
| `ffmpeg not found` | Install via `sudo apt install ffmpeg` |

## 🧪 Tested On

| OS | Status |
|----|--------|
| Ubuntu / Linux Mint | ✅ Stable |
| Windows (WSL) | ⚠ Requires ffmpeg & opencv |
| macOS | ✅ Works with Homebrew dependencies |

## 📜 License

Free to use for forensic, research, and security work. Attribution appreciated. No warranty on recovery success.

---

For improvements such as face tracking, evidence PDF creation, or auto-cropping of subjects, contributions or requests are welcome.
