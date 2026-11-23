"""The "Connect Spotify" window: walks a player through making their own Spotify developer app
(Spotify requires one per player) and signing in. Everything that has to be typed has a Copy
button, and the Client ID is picked up from the clipboard the moment the player copies it.
"""
import queue
import re
import threading
import tkinter as tk
import webbrowser

import web

BG, PANEL, FG, DIM, GREEN, RED = "#141417", "#1d1d22", "#ececf0", "#9a9aa6", "#1ed760", "#ff6b6b"
FONT = "Segoe UI"
ID_RE = re.compile(r"^\s*([0-9a-fA-F]{32})\s*$")

_open = threading.Lock()


def open_setup(web, log, on_connected=None):
    """Show the window (on its own thread). Does nothing if it's already open."""
    if not _open.acquire(blocking=False):
        return

    def run():
        try:
            SetupWindow(web, log, on_connected).run()
        except Exception as e:
            log(f"setup window failed: {e}")
        finally:
            _open.release()
    threading.Thread(target=run, daemon=True, name="setup").start()


class SetupWindow:
    def __init__(self, web, log, on_connected):
        self.web, self.log, self.on_connected = web, log, on_connected
        self.events = queue.Queue()
        self.cancel = False
        self.busy = False
        self.root = tk.Tk()
        r = self.root
        r.title("Cassette - Connect Spotify")
        r.configure(bg=BG)
        r.resizable(False, False)
        r.attributes("-topmost", True)  # over a borderless game window
        r.protocol("WM_DELETE_WINDOW", self.close)
        self.body = tk.Frame(r, bg=BG, padx=26, pady=22)
        self.body.pack(fill="both", expand=True)
        if web.signed_in():
            self.build_connected()
        else:
            self.build_steps()
        r.update_idletasks()
        w, h = r.winfo_width(), r.winfo_height()
        r.geometry(f"+{(r.winfo_screenwidth() - w) // 2}+{(r.winfo_screenheight() - h) // 3}")
        r.lift()
        r.focus_force()
        r.after(100, self.pump)

    # -- building --
    def clear(self):
        for child in self.body.winfo_children():
            child.destroy()

    def label(self, parent, text, size=10, color=FG, bold=False, wrap=500, **kw):
        return tk.Label(parent, text=text, bg=parent["bg"], fg=color, justify="left", anchor="w",
                        font=(FONT, size, "bold" if bold else "normal"), wraplength=wrap, **kw)

    def button(self, parent, text, command, primary=False):
        b = tk.Button(parent, text=text, command=command, relief="flat", cursor="hand2", padx=12, pady=4,
                      font=(FONT, 10, "bold" if primary else "normal"),
                      bg=GREEN if primary else "#2c2c34", fg="#0c0c0e" if primary else FG,
                      activebackground="#3ae07a" if primary else "#3a3a44",
                      activeforeground="#0c0c0e" if primary else FG, disabledforeground="#55555e")
        return b

    def step(self, number, title):
        row = tk.Frame(self.body, bg=PANEL, padx=14, pady=10)
        row.pack(fill="x", pady=(0, 8))
        head = tk.Frame(row, bg=PANEL)
        head.pack(fill="x")
        tk.Label(head, text=str(number), bg=GREEN, fg="#0c0c0e", width=2, font=(FONT, 10, "bold")).pack(side="left")
        self.label(head, "  " + title, 11, bold=True).pack(side="left")
        inner = tk.Frame(row, bg=PANEL, padx=30)
        inner.pack(fill="x", pady=(6, 0))
        return inner

    def copy_line(self, parent, name, value):
        line = tk.Frame(parent, bg=PANEL)
        line.pack(fill="x", pady=2)
        self.label(line, name, 9, DIM, width=12).pack(side="left")
        field = tk.Entry(line, bg="#101013", fg=FG, relief="flat", font=("Consolas", 10), width=34,
                         readonlybackground="#101013", insertbackground=FG)
        field.insert(0, value)
        field.configure(state="readonly")
        field.pack(side="left", padx=(0, 6), ipady=3)
        btn = self.button(line, "Copy", None)

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            btn.configure(text="Copied")
            self.root.after(1500, lambda: btn.winfo_exists() and btn.configure(text="Copy"))
        btn.configure(command=copy)
        btn.pack(side="left")

    def build_steps(self):
        self.clear()
        self.label(self.body, "Connect Spotify", 16, bold=True).pack(fill="x")
        self.label(self.body, "For your playlists, liked songs and search inside WoW. Spotify only allows this "
                              "with Premium and your own free developer app. It takes about two minutes, once.",
                   10, DIM).pack(fill="x", pady=(2, 14))

        s1 = self.step(1, "Open Spotify's developer dashboard")
        line = tk.Frame(s1, bg=PANEL)
        line.pack(fill="x")
        self.label(line, "Log in with your Spotify account. First time there? Accept the developer terms.",
                   9, DIM, wrap=300).pack(side="left")
        self.button(line, "Open dashboard", lambda: webbrowser.open(web.DASHBOARD_URL)).pack(side="right")

        s2 = self.step(2, "Create an app")
        self.label(s2, "Press Create app (or open the one you made before) and fill in:", 9, DIM).pack(fill="x")
        self.copy_line(s2, "App name", "Cassette")
        self.copy_line(s2, "Description", "Spotify in World of Warcraft")
        self.copy_line(s2, "Redirect URI", web.REDIRECT_URI)
        self.label(s2, "Press Add next to the Redirect URI, tick Web API and the terms, then Save.",
                   9, DIM).pack(fill="x", pady=(4, 0))

        s3 = self.step(3, "Copy your app's Client ID")
        self.label(s3, "It's on your app's page, under Basic Information. Just copy it - Cassette will notice.",
                   9, DIM).pack(fill="x")
        line = tk.Frame(s3, bg=PANEL)
        line.pack(fill="x", pady=(4, 0))
        self.client_id = tk.StringVar(value=self.web.client_id)
        self.client_id.trace_add("write", lambda *a: self.refresh_connect())
        tk.Entry(line, textvariable=self.client_id, bg="#101013", fg=FG, relief="flat", font=("Consolas", 10),
                 width=36, insertbackground=FG).pack(side="left", ipady=3)
        self.id_note = self.label(line, "", 9, GREEN)
        self.id_note.pack(side="left", padx=8)

        s4 = self.step(4, "Connect")
        line = tk.Frame(s4, bg=PANEL)
        line.pack(fill="x")
        self.label(line, "Your browser will ask you to agree. Then come back here.", 9, DIM, wrap=300).pack(side="left")
        self.connect_btn = self.button(line, "Connect Spotify", self.connect, primary=True)
        self.connect_btn.pack(side="right")

        self.status = self.label(self.body, "", 10, DIM)
        self.status.pack(fill="x", pady=(8, 0))
        self.refresh_connect()
        self.watch_clipboard()

    def build_connected(self, just_now=False):
        self.clear()
        self.label(self.body, "Spotify is connected", 16, bold=True, color=GREEN).pack(fill="x")
        who = self.web.user or "your account"
        self.label(self.body, f"Signed in as {who}. Open the browser in game with the  =  button on the "
                              "Cassette player: your playlists, liked songs and search are there.",
                   10, FG if just_now else DIM).pack(fill="x", pady=(6, 16))
        line = tk.Frame(self.body, bg=BG)
        line.pack(fill="x")
        self.button(line, "Done", self.close, primary=True).pack(side="right")
        self.button(line, "Disconnect", self.disconnect).pack(side="right", padx=8)

    # -- behaviour --
    def valid_id(self):
        m = ID_RE.match(self.client_id.get())
        return m.group(1).lower() if m else None

    def refresh_connect(self):
        if hasattr(self, "connect_btn"):
            self.connect_btn.configure(state="normal" if self.valid_id() and not self.busy else "disabled")

    def watch_clipboard(self):
        if not self.root.winfo_exists() or not hasattr(self, "id_note"):
            return
        try:
            m = ID_RE.match(self.root.clipboard_get())
        except tk.TclError:
            m = None
        if m and m.group(1).lower() != (self.valid_id() or ""):
            self.client_id.set(m.group(1).lower())
            self.id_note.configure(text="Got it from your clipboard")
        self.root.after(600, self.watch_clipboard)

    def connect(self):
        cid = self.valid_id()
        if not cid or self.busy:
            return
        self.busy, self.cancel = True, False
        self.refresh_connect()
        self.set_status("Waiting for you to agree in your browser...", DIM)

        def work():
            try:
                user = self.web.sign_in(cid, webbrowser.open, lambda: self.cancel)
                self.events.put(("ok", user))
            except web.SpotifyError as e:
                self.events.put(("error", e))
            except Exception as e:  # anything else must still reach the window, never leave it waiting
                import traceback
                self.log("sign-in crashed: " + traceback.format_exc().replace("\n", " | "))
                self.events.put(("error", web.SpotifyError(0, "unexpected", f"{type(e).__name__}: {e}")))
        threading.Thread(target=work, daemon=True, name="sign-in").start()

    def pump(self):
        """Results from the sign-in thread, handled on the window's own thread."""
        try:
            while True:
                kind, value = self.events.get_nowait()
                self.busy = False
                if kind == "ok":
                    if self.on_connected:
                        self.on_connected()
                    self.build_connected(just_now=True)
                    self.root.lift()
                    self.root.focus_force()
                elif value.reason != "cancelled":
                    self.log(f"Spotify sign-in failed: {value}")
                    self.set_status(value.advice(), RED)
                    self.refresh_connect()
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(150, self.pump)

    def set_status(self, text, color):
        if hasattr(self, "status") and self.status.winfo_exists():
            self.status.configure(text=text, fg=color)

    def disconnect(self):
        self.web.sign_out()
        if self.on_connected:
            self.on_connected()
        self.build_steps()

    def close(self):
        self.cancel = True
        self.root.destroy()

    def run(self):
        self.root.mainloop()
