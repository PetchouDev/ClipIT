# ClipIT - Clipboard manager

ClipIT is a pretty and simple cross-platform clipboard manager.  
It consists of 2 components:
- A service that runs in the background and listens to clipboard changes (writen in GoLang)
- A GUI that shows the clipboard history and allows you to select and paste any item (written in Python)

The GUI is powered by the Qt6 framework and the PySide6 bindings.

## Dependencies
- MacOS: pbcopy `brew install pbcopy`
- Linux: xclip 
    - Debian/Ubuntu: `sudo apt-get install xclip`
    - Fedora: `sudo dnf install xclip`
    - Arch: `sudo pacman -S xclip`
    - RedHat/CentOS: `sudo yum install xclip`

## Installation
An installer will be available soon for all platforms.
It will install the program to the default location for the OS and enable the service to start at login.

### From the releases
1. Download the latest release from the [releases page](https://github.com/PetchouDev/ClipIT/releases)
Currently, I only built the Windows amd64 version. If you need another version, please let me know.
2. Extract the archive to the desired location

Recommended locations:
- Windows: `C:\Users\<username>\AppData\Local\ClipIT`
- Linux: `~/.local/share/ClipIT`
- MacOS: `~/Library/Application Support/ClipIT`
3. Add the `ClipIT` binary to the autostart applications (optionnal - see below)
4. Run the program by executing the `ClipIT` binary


### Manual installation
1. Clone the repository `git clone https://github.com/PetchouDev/ClipIT.git`
2. Install the dependencies (see above)
3. Move to the `ClipIT` directory `cd ClipIT`
4. Compile the Python frontend 
```bash
pipx install pyinstaller # For Linux and MacOS
pip install pyinstaller # For Windows (make sure to add it to the PATH)

# Compile the frontend
pyinstaller --noconfirm --onedir --windowed --name "frontend" --hidden-import "PySide6" --hidden-import "pillow" --hidden-import "pyperclip"  "frontend.py"

# Move the compiled frontend to the correct location
mv dist/frontend/* . # Linux and MacOS
move dist\frontend\* . # Windows

# Remove the build/dist directories and the spec file
rm -rf build dist frontend.spec # Linux and MacOS
rmdir /s /q build dist && del frontend.spec # Windows
```
5. Compile the Go backend
```bash
go build -o ClipIT.exe -ldflags -H=windowsgui
```
6. Move the files to another directory (optional)
You need to move :
- The `ClipIT` binary (the Go backend)
- The `frontend` binary (the Python frontend)
- The `_internal` directory (contains the libraries for the Python frontend)
- The `assets` directory (contains the icons and the UI file for the frontend)
- The `font.ttf` file (the font used in the frontend)
- The `nircmd.exe` file (Windows only, used to push images to the clipboard)
7. Run the program at logon (optional)
    - Windows: create a shortcut to the `ClipIT` binary in the `shell:startup` folder
    - Linux: add the `ClipIT` binary to the autostart applications or create a systemd service (see your DE documentation)
    - MacOS: add the `ClipIT` binary to the login items

You can now run the program by executing the `ClipIT` binary.


## Features
### Already implemented
Data types supported:
- [x] text (copy and paste done)
    - [x] as raw text
    - [x] as email (add a mailto:// button to send an email quickly)
    - [x] as URL (add a button to open the URL in the default browser)
    - [x] as a color (show the color in background - support hex, rgb, rgba, hsl, hsla)
- [ ] image (not extensively tested)
    - [x] Windows (copy and paste done)
    - [ ] Linux (copy should work, paste not tested)
    - [ ] MacOS (not tested)
- [ ] file (not implemented, might not be possible)
- [x] Toggle the GUI with a keyboard shortcut (Ctrl+Alt+V / AltGr+V)


### TODO:
- [x] Implement the service that listens to clipboard changes
- [X] tray icon/menu (allow to quit the application and stop the service)
- [x] Implement the different ways to show text items (email, URL, color, raw text)
- [x] Implement quick actions for email and URL
- [x] Implement Image support for the GUI
- [ ] Implement Image pasting
    - [x] Windows
    - [ ] Linux
    - [ ] MacOS
- [ ] Implement file support for the GUI (might not be possible)
- [ ] Add a settings dialog
    - [ ] Add a way to change the number of items in the history
    - [ ] Add a way to change the time to keep the items in the history
    - [ ] Add a way to change the font size
- [x] Add a way to clear the history (in progress - button exists but not implemented)
- [ ] Add a way to search the history (not started - likely not for the first version)
- [ ] Add a way to filter the history by data type (not started - likely not for the first version)
