# LibreVNA-GUI Binary Directory

This directory contains the LibreVNA-GUI executable required to run the automation scripts in this project.

## Why This Directory Exists

The LibreVNA-GUI binary is platform-specific and not included in version control due to its size. Each operating system requires its own version of the binary.

## Download Instructions

### Step 1: Visit the Releases Page

Go to the official LibreVNA releases page:
**https://github.com/jankae/LibreVNA/releases**

### Step 2: Download the Correct Binary for Your OS

#### Linux (Ubuntu/Debian)
1. Download the latest **`.AppImage`** file (e.g., `LibreVNA-v1.x.x-Linux.AppImage`)
2. Rename it to `LibreVNA-GUI` (remove the version suffix and `.AppImage` extension)
3. Place it in this directory
4. Make it executable:
   ```bash
   chmod +x LibreVNA-GUI
   ```

#### macOS
1. Download the latest **`.dmg`** file (e.g., `LibreVNA-v1.x.x-macOS.dmg`)
2. Open the `.dmg` and extract the `LibreVNA-GUI.app` bundle
3. Navigate into the app bundle to find the actual executable:
   ```bash
   # The executable is typically at:
   LibreVNA-GUI.app/Contents/MacOS/LibreVNA-GUI
   ```
4. Copy the executable to this directory and rename it to `LibreVNA-GUI`
5. Make it executable if needed:
   ```bash
   chmod +x LibreVNA-GUI
   ```

#### Windows
1. Download the latest **`.zip`** file (e.g., `LibreVNA-v1.x.x-Windows.zip`)
2. Extract the archive
3. Find `LibreVNA-GUI.exe` in the extracted files
4. Copy it to this directory and rename it to `LibreVNA-GUI.exe`

## Verification

After downloading, verify the binary works:

```bash
# Linux/macOS
./LibreVNA-GUI --help

# Windows (PowerShell)
.\LibreVNA-GUI.exe --help
```

You should see the LibreVNA-GUI help message or version information.

## Usage in Scripts

The automation scripts in `../scripts/` expect the binary to be at:
```
code/LibreVNA-dev/tools/LibreVNA-GUI
```

Scripts will launch the GUI in headless mode using:
```bash
QT_QPA_PLATFORM=offscreen ./LibreVNA-GUI --port 1234
```

## Version Compatibility

All scripts in this project have been tested with **LibreVNA v1.6.0+**. Using older versions may result in incompatible SCPI commands or missing features (especially streaming server support).

## Troubleshooting

### Linux: "Permission denied"
Make sure the binary is executable:
```bash
chmod +x LibreVNA-GUI
```

### Linux: AppImage won't run
You may need to install FUSE:
```bash
sudo apt-get install fuse libfuse2
```

### macOS: "LibreVNA-GUI is damaged and can't be opened"
macOS Gatekeeper may block unsigned binaries. Either:
1. Right-click → Open → confirm to bypass Gatekeeper
2. Or remove the quarantine flag:
   ```bash
   xattr -d com.apple.quarantine LibreVNA-GUI
   ```

### All platforms: GUI crashes on startup
Ensure you have the required Qt libraries installed. On Linux:
```bash
sudo apt-get install qt5-default libqt5widgets5 libqt5gui5 libqt5core5a
```

## Notes

- This directory is listed in `.gitignore` to avoid committing large binary files
- Each developer/environment must download their own platform-specific binary
- Check the releases page periodically for updates with bug fixes or new features
