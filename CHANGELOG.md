# Changelog

All notable changes to this project will be documented in this file.

## [3.1] - 2025

### Fixed - Critical SOI Validation
- **False SOI Detection**: Added validation to filter out false `0xFFD8` byte sequences that appear in image data but are not actual JPEG starts
- This fixes the issue where some "frames" would fail to decode because they were not real JPEG images
- SOI markers are now validated by checking if they're followed by a valid JPEG marker (`0xFF` + APP0-APP15, SOF, DQT, etc.)
- Improves extraction success rate from ~91% to 100% on test files

### Changed
- `find_all_soi_markers()` now returns a tuple: `(valid_positions, rejected_count)`
- Log output now shows "Found X valid JPEG frames" instead of "Found X SOI markers"
- Added log message showing count of filtered false positives

---

## [3.0] - 2025

### Added - Forensic Enhancements
- **Forensic Report Generation**: Automatic JSON report with SHA256/MD5 hashes of source files, extraction statistics, and processing settings
- **Audit Trail Logging**: All operations logged to timestamped file (`extraction_log_YYYYMMDD_HHMMSS.txt`) for legal/evidence purposes
- **Source File Integrity**: SHA256 hashes computed and logged before any processing begins
- **Verbose Mode**: `--verbose` / `-v` flag for detailed debug output

### Added - New Configuration Options
- `--jpeg-quality`: Configurable JPEG output quality (1-100, default: 95)
- `--clahe-clip`: Adjustable CLAHE clip limit (default: 2.0)
- `--clahe-grid`: Adjustable CLAHE grid size (default: 8)
- `--version`: Display version information

### Fixed
- **Memory Safety**: Proper resource cleanup using context managers - memory-mapped files now guaranteed to close even on errors
- **Crop Validation**: Full validation of crop parameters (must have 4 values, all non-negative, width/height > 0)
- **Timestamp Mapping**: Added warning when SOI position falls before first index offset (potential timestamp inaccuracy)
- **Duplicate SOI Search**: SOI positions now cached and reused between extraction and timestamp passes (performance improvement)

### Improved
- **Type Hints**: Complete type annotations on all functions
- **Error Handling**: More granular exception handling with informative log messages
- **Code Organization**: Renamed functions for clarity (`enhance_cv` → `enhance_image`, `text_size` → `get_text_dimensions`)
- **Cross-Platform Fonts**: Added font paths for macOS and Windows
- **Consistent Language**: All log messages now in English
- **Progress Reporting**: Frame-by-frame progress logged every 100 frames

### Removed
- Unused `import io`

### Security
- All enhancements are documented as non-destructive visual improvements
- Integrity notes included in forensic report

---

## [2.0] - Previous Version

### Features
- JPEG frame extraction from proprietary binary format
- Timestamp reconstruction from index files
- Image enhancement (denoise, CLAHE, sharpening)
- MP4 video generation
- Upscaling support
- Crop support

---

## Forensic Compliance Notes

Version 3.0 is designed for forensic/legal use:

1. **Chain of Custody**: Source file hashes logged before processing
2. **Non-Destructive**: Original files never modified
3. **Audit Trail**: Complete operation log with timestamps
4. **Reproducibility**: All settings documented in JSON report
5. **Transparency**: Enhancement operations are purely visual (brightness/contrast/sharpening)
