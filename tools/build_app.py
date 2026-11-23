"""Build the Cassette app (the companion) and its installer.

    companion\\.venv\\Scripts\\python.exe tools\\build_app.py [--no-installer]

1. Stages a clean copy of the addon (without the companion's files in live\\). The app carries
   it and puts it into the game when it's missing or older (cassette.install_addon).
2. PyInstaller builds build\\dist\\Cassette\\Cassette.exe (one folder, no console window).
3. Inno Setup turns that folder into build\\Cassette-Setup-<version>.exe: a per-user install (no
   admin prompt) with a Start-menu entry, an optional start-with-Windows, and an uninstaller.

Needs PyInstaller in the companion's environment, and Inno Setup 7 (ISCC.exe on PATH, in the
ISCC environment variable, or in the usual folders).
"""
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPANION = os.path.join(ROOT, "companion")
ADDON = os.path.join(ROOT, "addon")
BUILD = os.path.join(ROOT, "build")
INSTALLER = os.path.join(ROOT, "installer", "setup.iss")
MAIN = os.path.join(COMPANION, "cassette.py")


def _setting(name):
    src = open(MAIN, encoding="utf-8").read()
    return re.search(rf'^{name} = "([^"]+)"', src, re.M).group(1)


def make_icon(path):
    """The app's icon: Cassette's logo (tools/make_logo.py), at the sizes Windows uses."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import make_logo
    make_logo.icon_file(path)


def stage_addon(stage):
    """A clean copy of the addon for the app to carry."""
    name = _setting("ADDON")
    shutil.rmtree(os.path.join(stage, "addon"), ignore_errors=True)
    shutil.copytree(os.path.join(ADDON, name), os.path.join(stage, "addon", name),
                    ignore=shutil.ignore_patterns("live", "*.tmp"))
    return os.path.join(stage, "addon")


def pyinstaller(name, icon, addon_stage):
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
                    "--name", name, "--icon", icon,
                    "--distpath", os.path.join(BUILD, "dist"), "--workpath", os.path.join(BUILD, "work"),
                    "--specpath", BUILD, "--paths", COMPANION,
                    "--add-data", f"{addon_stage}{os.pathsep}addon",
                    "--add-data", f"{os.path.join(COMPANION, 'logo.png')}{os.pathsep}.",
                    "--collect-submodules", "winrt", "--collect-submodules", "pycaw",
                    "--hidden-import", "pystray._win32",
                    MAIN], check=True, cwd=ROOT)
    return os.path.join(BUILD, "dist", name)


def find_iscc():
    home = os.path.expanduser("~")
    for candidate in (os.environ.get("ISCC"), shutil.which("ISCC"),
                      os.path.join(home, "Tools", "Inno Setup 7", "ISCC.exe"),
                      os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 7", "ISCC.exe"),
                      r"C:\Program Files (x86)\Inno Setup 7\ISCC.exe", r"C:\Program Files\Inno Setup 7\ISCC.exe"):
        if candidate and os.path.isfile(candidate):
            return candidate
    raise SystemExit("Inno Setup's ISCC.exe wasn't found (set ISCC to its path)")


def installer(name, version, app_dir, icon):
    subprocess.run([find_iscc(), f"/DAppName={name}", f"/DAppVersion={version}", f"/DSourceDir={app_dir}",
                    f"/DIconFile={icon}", f"/O{BUILD}", INSTALLER], check=True, cwd=ROOT)
    return os.path.join(BUILD, f"{name}-Setup-{version}.exe")


def release_notes(name, version, setup):
    """The installer's SHA-256 (in a .sha256 file beside it) and the text for the GitHub
    release, from docs/release-notes.md with the version and checksum filled in."""
    import hashlib
    digest = hashlib.sha256(open(setup, "rb").read()).hexdigest().upper()
    with open(setup + ".sha256", "w", encoding="utf-8") as f:
        f.write(f"{digest}  {os.path.basename(setup)}\n")
    template = open(os.path.join(ROOT, "docs", "release-notes.md"), encoding="utf-8").read()
    text = (template.replace("{name}", name).replace("{version}", version)
            .replace("{setup}", os.path.basename(setup)).replace("{sha256}", digest))
    out = os.path.join(BUILD, f"{name}-{version}-release-notes.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    return out


def main():
    name, version = _setting("ADDON"), _setting("VERSION")
    os.makedirs(BUILD, exist_ok=True)
    icon = os.path.join(BUILD, f"{name}.ico")
    make_icon(icon)
    app_dir = pyinstaller(name, icon, stage_addon(os.path.join(BUILD, "stage")))
    print(f"app: {app_dir}")
    if "--no-installer" not in sys.argv:
        setup = installer(name, version, app_dir, icon)
        print(f"installer: {setup}")
        print(f"release notes: {release_notes(name, version, setup)}")


if __name__ == "__main__":
    main()
