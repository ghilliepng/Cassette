# Third-party software

The Cassette app (the Windows installer) includes these components. Each keeps its own licence,
which this notice doesn't change, and all of them may be distributed as part of Cassette.
Cassette's own code is all rights reserved (see LICENSE).

| Component | What it's for | Licence |
|---|---|---|
| [Python](https://www.python.org/) 3.12, with Tcl/Tk | runs the app | Python Software Foundation License; Tcl/Tk licence (BSD-style) |
| [Pillow](https://python-pillow.org/) | draws the pictures the addon shows | MIT-CMU (HPND) |
| [pystray](https://github.com/moses-palmer/pystray) | the system tray icon | GNU LGPL v3.0 |
| [six](https://github.com/benjaminp/six) | used by pystray | MIT |
| [pycaw](https://github.com/AndreMiras/pycaw) | Spotify's volume in the Windows mixer | MIT |
| [comtypes](https://github.com/enthought/comtypes) | used by pycaw | MIT |
| [psutil](https://github.com/giampaolo/psutil) | used by pycaw | BSD 3-Clause |
| [winrt (PyWinRT)](https://github.com/pywinrt/pywinrt) | reads what's playing from Windows' media controls | MIT |
| [PyInstaller](https://pyinstaller.org/) bootloader | starts the packaged app | GNU GPL v2.0 with an exception that allows distributing apps built with it |

The installer is made with [Inno Setup](https://jrsoftware.org/isinfo.php), whose licence allows
distributing installers built with it.

The source code of every component is available from the links above. Cassette's own source,
with the scripts that build the app and installer, is in this repository, so you can rebuild it
with your own changes to any of these components.

Fonts: when the World of Warcraft font is used for song names, the app reads it from your own
game installation; it isn't included with Cassette.
