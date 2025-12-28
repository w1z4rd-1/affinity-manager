# Affinity Manager

A Windows GUI tool for managing CPU core affinity across multiple processes. Designed to optimize performance by intelligently distributing processes across P-cores and E-cores on hybrid CPUs.

## Features

- **Visual Core Selection**: Intuitive drag-to-select interface with P-core/E-core visualization
- **Batch Process Management**: Set affinity for Minecraft, Discord, OBS, and other processes at once
- **Hybrid CPU Awareness**: Automatically detects and displays P-cores vs E-cores
- **Physical Core Grouping**: Shows which logical cores share the same physical hardware (HT/SMT siblings)
- **Custom Process Support**: Add your own programs to manage
- **Smart Defaults**: Recommends optimal core allocations based on your CPU architecture
- **Protected System Processes**: Automatically excludes critical OS processes to prevent instability

## Requirements

- Windows 10/11
- Python 3.8+ (for running from source)
- Administrator privileges (required for setting process affinity)

## Installation

### Pre-built Executable
Download the latest `AffinityManager.exe` from the releases page.

### From Source
```bash
git clone https://github.com/w1z4rd-1/affinity-manager.git
cd affinity-manager
pip install -r requirements.txt
python affinity_manager.py
```

## Usage

1. Launch with administrator privileges (UAC prompt will appear)
2. Detected processes are shown in the "Detected Processes" section
3. Click "Recommended" for optimal defaults, or drag to select custom core ranges
4. Click "Apply" to set affinities
5. Use "Refresh" to update process list

## Building

```bash
pip install pyinstaller
pyinstaller affinity_manager.spec
```

## Safety Notes

- The tool automatically skips critical system processes (csrss.exe, lsass.exe, dwm.exe, etc.)
- Affinities do not persist across reboots
- Setting affinity on explorer.exe is safe but keep at least one P-core available for responsiveness

## License

MIT License - see LICENSE file

## Author

Created by wizard1

