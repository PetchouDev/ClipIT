# ClipIT - Clipboard manager

ClipIT is a pretty and simple cross-platform clipboard manager.  
It consists of 2 components:
- A service that runs in the background and listens to clipboard changes (writen in GoLang)
- A GUI that shows the clipboard history and allows you to select and paste any item (written in Python)

The GUI is powered by the Qt6 framework and the PySide6 bindings.

## Features
### Already implemented
Data types supported:
- [x] text (copy and paste done)
    - [x] as raw text
    - [x] as email (add a mailto:// button to send an email quickly)
    - [x] as URL (add a button to open the URL in the default browser)
    - [x] as a color (show the color in background - support hex, rgb and rgba)
- [ ] image (copy done, paste needs to be implemented for each platform)


### TODO:
- [ ] tray icon/menu
- [ ] Implement the different ways to show text items (email, URL, color, raw text)
- [ ] Implement quick actions for email and URL
- [ ] Implement Image support for the GUI
- [ ] Implement Image pasting
    - [ ] Windows
    - [ ] Linux
    - [ ] MacOS
- [ ] Implement file support for the GUI (might not be possible)
- [ ] Add a settings dialog
    - [ ] Add a way to change the number of items in the history
    - [ ] Add a way to change the time to keep the items in the history
    - [ ] Add a way to change the font size
- [ ] Add a way to clear the history (in progress - button exists but not implemented)
- [ ] Add a way to search the history (not started - likely not for the first version)
- [ ] Add a way to filter the history by data type (not started - likely not for the first version)
