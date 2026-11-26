#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CarryOS Writer - a wizard that streams the CarryOS image from the internet
straight onto a USB drive. Windows, Linux and macOS. No temporary file is
ever saved to your disk.

How it works:
  1. A small latest.json (MANIFEST_URL) is read: url, sha256, size ...
  2. The user picks a USB drive (only USB drives are listed - never the system disk).
  3. The image is downloaded in chunks, decompressed on the fly (.xz / .gz),
     written to the raw device, and its SHA256 is computed at the same time.
  4. When writing finishes, the USB is read back and the hash is compared.
  If the connection drops, the download resumes with HTTP Range.

latest.json fields:
  url     https:// link to the image (.img, .img.gz or .img.xz)
  sha256  SHA256 of the UNCOMPRESSED image (not of the .gz file)
  size    size of the UNCOMPRESSED image in bytes
"""
import ctypes
import hashlib
import http.client
import json
import lzma
import os
import plistlib
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib

APP_TITLE = "CarryOS Writer"
# After publishing latest.json, replace this with your own address
# (or set the DISTRO_MANIFEST environment variable):
MANIFEST_URL = os.environ.get(
    "DISTRO_MANIFEST", "https://carryos.github.io/latest.json"
)
UA = "CarryOSWriter/1.0"
BLOCK = 4 * 1024 * 1024
ALIGN = 4096  # safe alignment for 512-byte and 4Kn disks
IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
NO_WINDOW = 0x08000000 if IS_WIN else 0


class Cancelled(Exception):
    pass


# --------------------------------------------------------------------- helpers
def run(cmd):
    return subprocess.run(
        cmd, capture_output=True, text=True, creationflags=NO_WINDOW
    )


def run_plist(cmd):
    r = subprocess.run(cmd, capture_output=True)
    try:
        return plistlib.loads(r.stdout) if r.stdout else {}
    except Exception:
        return {}


def fmt_size(n):
    return f"{n / 1e9:.1f} GB"


def is_admin():
    try:
        if IS_WIN:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        return os.geteuid() == 0
    except Exception:
        return False


def relaunch_elevated():
    """Restart as administrator/root. True: another process is running, we can exit."""
    frozen = getattr(sys, "frozen", False)
    args = [sys.executable] + ([] if frozen else [os.path.abspath(__file__)]) + sys.argv[1:]

    if IS_WIN:
        params = subprocess.list2cmdline(args[1:])
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", args[0], params, None, 1)
        return rc > 32

    if IS_MAC:
        # Standard macOS password prompt. The app is started in the background
        # as root, so osascript returns as soon as the password is accepted.
        cmd = " ".join(shlex.quote(a) for a in args) + " >/dev/null 2>&1 &"
        script = 'do shell script "{}" with administrator privileges'.format(
            cmd.replace("\\", "\\\\").replace('"', '\\"')
        )
        try:
            return subprocess.call(["osascript", "-e", script]) == 0
        except FileNotFoundError:
            return False

    # Linux. Inside an AppImage the FUSE mount is private to the current user,
    # so root cannot run the binary from there: re-run the .AppImage file itself.
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        args = [appimage] + sys.argv[1:]
    keep = ("DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "LANG")
    env = [f"{k}={os.environ[k]}" for k in keep if k in os.environ]
    if appimage:
        env.append("APPIMAGE_EXTRACT_AND_RUN=1")  # works even without FUSE for root
    try:
        rc = subprocess.call(["pkexec", "/usr/bin/env", *env, *args])
    except FileNotFoundError:
        return False
    return rc not in (126, 127)


# ----------------------------------------------------------------------- disks
def list_usb_disks():
    disks = []
    if IS_WIN:
        ps = (
            "Get-Disk | Where-Object { $_.BusType -eq 'USB' -and -not $_.IsSystem "
            "-and -not $_.IsBoot -and $_.Size -gt 0 } "
            "| Select-Object Number,FriendlyName,Size | ConvertTo-Json -Compress"
        )
        txt = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps]).stdout.strip()
        if txt:
            data = json.loads(txt)
            if isinstance(data, dict):
                data = [data]
            for d in data:
                disks.append({
                    "path": rf"\\.\PhysicalDrive{d['Number']}",
                    "number": int(d["Number"]),
                    "name": (d.get("FriendlyName") or "USB disk").strip(),
                    "size": int(d["Size"]),
                })
    elif IS_MAC:
        data = run_plist(["diskutil", "list", "-plist", "external", "physical"])
        for ident in data.get("WholeDisks", []):
            info = run_plist(["diskutil", "info", "-plist", ident])
            if info.get("Internal") or info.get("BusProtocol") != "USB":
                continue
            size = int(info.get("TotalSize") or info.get("Size") or 0)
            if size <= 0:
                continue
            disks.append({
                "path": f"/dev/{ident}",
                "io_path": f"/dev/r{ident}",  # raw device: much faster, uncached
                "name": (info.get("MediaName") or "USB disk").strip(),
                "size": size,
            })
    else:
        out = run(["lsblk", "-J", "-b", "-d", "-o", "NAME,SIZE,MODEL,VENDOR,TRAN,TYPE"]).stdout
        for d in json.loads(out or "{}").get("blockdevices", []):
            if d.get("type") == "disk" and d.get("tran") == "usb" and int(d.get("size") or 0) > 0:
                name = " ".join(x for x in [(d.get("vendor") or "").strip(),
                                            (d.get("model") or "").strip()] if x) or "USB disk"
                disks.append({"path": "/dev/" + d["name"], "name": name, "size": int(d["size"])})
    return disks


def _is_partition_of(src, dev):
    if not src.startswith(dev):
        return False
    return src[len(dev):].lstrip("p").isdigit()


def prepare_disk(disk):
    """Unmounts volumes so that raw writing is not blocked."""
    if IS_WIN:
        n = disk["number"]
        run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"Clear-Disk -Number {n} -RemoveData -RemoveOEM -Confirm:$false "
             "-ErrorAction SilentlyContinue"])
    elif IS_MAC:
        run(["diskutil", "unmountDisk", "force", disk["path"]])
    else:
        dev = disk["path"]
        with open("/proc/mounts") as f:
            for line in f:
                src = line.split()[0]
                if _is_partition_of(src, dev):
                    run(["umount", src])


def open_device(disk, write):
    path = disk.get("io_path") or disk["path"]
    if IS_WIN or IS_MAC:
        return open(path, "r+b" if write else "rb", buffering=0)
    # O_EXCL: refuses to open a disk that is still mounted -> prevents accidents
    flags = (os.O_RDWR | os.O_EXCL) if write else os.O_RDONLY
    return os.fdopen(os.open(path, flags), "r+b" if write else "rb", buffering=0)


def full_sync(f):
    try:
        if IS_MAC:
            import fcntl
            fcntl.fcntl(f.fileno(), fcntl.F_FULLFSYNC)
        else:
            os.fsync(f.fileno())
    except (OSError, ImportError, AttributeError):
        pass


# -------------------------------------------------------------------- download
class Downloader:
    """Downloader that resumes where it left off using HTTP Range."""

    def __init__(self, url, cancel):
        self.url, self.cancel = url, cancel
        self.pos = 0
        self.total = None

    def chunks(self):
        fails = 0
        while True:
            headers = {"User-Agent": UA}
            if self.pos:
                headers["Range"] = f"bytes={self.pos}-"
            try:
                req = urllib.request.Request(self.url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as r:
                    if self.pos and r.status != 206:
                        raise RuntimeError("The server does not support resuming downloads (Range).")
                    if self.total is None and r.headers.get("Content-Length"):
                        self.total = int(r.headers["Content-Length"])
                    while True:
                        if self.cancel.is_set():
                            raise Cancelled()
                        b = r.read(1 << 20)
                        if not b:
                            break
                        self.pos += len(b)
                        fails = 0
                        yield b
                if self.total is None or self.pos >= self.total:
                    return
                raise OSError("Connection closed early")
            except (Cancelled, RuntimeError):
                raise
            except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
                if isinstance(e, urllib.error.HTTPError) and e.code < 500 and e.code != 429:
                    raise RuntimeError(f"Server error: HTTP {e.code}")
                fails += 1
                if fails > 10:
                    raise RuntimeError(f"Download failed: {e}")
                time.sleep(min(2 * fails, 15))


def make_decoder(url):
    path = url.split("?")[0].lower()
    if path.endswith(".xz"):
        return lzma.LZMADecompressor()
    if path.endswith(".gz"):
        return zlib.decompressobj(zlib.MAX_WBITS | 16)
    return None


# ----------------------------------------------------------------------- write
def write_image(manifest, disk, emit, cancel):
    """emit(kind, *args): ("status", text) / ("progress", fraction|-1, text)"""
    url, dev = manifest["url"], disk["path"]
    need = manifest.get("size")
    if need and disk["size"] < need:
        raise RuntimeError("The USB drive is not large enough for the image.")

    emit("status", "Preparing the disk...")
    prepare_disk(disk)

    dl, dec, sha = Downloader(url, cancel), make_decoder(url), hashlib.sha256()
    buf, out_bytes = bytearray(), 0
    t0, last = time.time(), 0.0

    with open_device(disk, True) as f:
        for chunk in dl.chunks():
            data = dec.decompress(chunk) if dec else chunk
            if not data:
                continue
            sha.update(data)
            out_bytes += len(data)
            if out_bytes > disk["size"]:
                raise RuntimeError("The image turned out larger than the USB drive.")
            buf += data
            while len(buf) >= BLOCK:
                f.write(bytes(buf[:BLOCK]))
                del buf[:BLOCK]
            now = time.time()
            if now - last > 0.5:
                last = now
                if dl.total:
                    frac = dl.pos / dl.total
                elif need:
                    frac = out_bytes / need
                else:
                    frac = -1
                speed = out_bytes / max(now - t0, 0.1) / 1e6
                emit("progress", frac, f"Downloading and writing...  {speed:.1f} MB/s")
        if dec is not None and not dec.eof:
            raise RuntimeError("The compressed file is incomplete or corrupt.")
        if buf:
            f.write(bytes(buf) + b"\0" * ((-len(buf)) % ALIGN))
        f.flush()
        full_sync(f)

    digest = sha.hexdigest()
    expected = (manifest.get("sha256") or "").lower()
    if expected and expected != digest:
        raise RuntimeError("The SHA256 of the downloaded data does not match the expected value. "
                           "Try again; if the problem persists, please report it on the website.")

    # --- read back and verify
    emit("progress", 0.0, "Verifying...")
    if IS_LINUX:
        run(["blockdev", "--flushbufs", dev])
        try:
            with open("/proc/sys/vm/drop_caches", "w") as c:
                c.write("3")
        except OSError:
            pass
    # (macOS: the raw /dev/rdisk device bypasses the cache; Windows: unbuffered handle)
    h, remaining = hashlib.sha256(), out_bytes
    with open_device(disk, False) as f:
        done = 0
        while remaining:
            if cancel.is_set():
                raise Cancelled()
            n = min(BLOCK, remaining)
            b = f.read(n + (-n) % ALIGN)
            if len(b) < n:
                raise RuntimeError("Could not read the USB drive back (the drive may be faulty).")
            h.update(b[:n])
            remaining -= n
            done += n
            emit("progress", done / out_bytes, "Verifying...")
    if h.hexdigest() != digest:
        raise RuntimeError("Verification failed: the data written to the USB drive is different. "
                           "Try a different USB drive.")

    if IS_WIN:
        run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"Update-Disk -Number {disk['number']} -ErrorAction SilentlyContinue"])
    elif IS_MAC:
        run(["diskutil", "eject", dev])
    else:
        run(["blockdev", "--rereadpt", dev])
        run(["sync"])


# ------------------------------------------------------------------------- GUI
def run_gui():
    import tkinter as tk
    from tkinter import messagebox, ttk

    class App(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title(APP_TITLE)
            self.geometry("600x440")
            self.resizable(False, False)
            self.manifest, self.disks = None, []
            self.cancel = threading.Event()
            self.q = queue.Queue()
            self.busy = False

            self.body = ttk.Frame(self, padding=20)
            self.body.pack(fill="both", expand=True)
            nav = ttk.Frame(self, padding=(20, 0, 20, 16))
            nav.pack(fill="x")
            self.btn_close = ttk.Button(nav, text="Close", command=self.on_close)
            self.btn_next = ttk.Button(nav, text="Next >")
            self.btn_back = ttk.Button(nav, text="< Back")
            self.btn_close.pack(side="left")
            self.btn_next.pack(side="right")
            self.btn_back.pack(side="right", padx=8)
            self.protocol("WM_DELETE_WINDOW", self.on_close)
            self.after(100, self.poll)
            self.step_welcome()

        # ---- helpers
        def clear(self):
            for w in self.body.winfo_children():
                w.destroy()

        def label(self, text, **kw):
            lb = ttk.Label(self.body, text=text, wraplength=555, justify="left", **kw)
            lb.pack(anchor="w", pady=(10, 0))
            return lb

        def nav(self, back=None, nxt=None, nxt_text="Next >", close_text="Close"):
            self.btn_close.config(text=close_text)
            for btn, cmd, txt in ((self.btn_back, back, None), (self.btn_next, nxt, nxt_text)):
                if txt:
                    btn.config(text=txt)
                btn.config(command=cmd or (lambda: None))
                btn.state(["!disabled"] if cmd else ["disabled"])

        # ---- step 1: welcome
        def step_welcome(self):
            self.clear()
            ttk.Label(self.body, text=APP_TITLE, font=("", 20, "bold")).pack(anchor="w")
            self.info = self.label("Fetching version information...")
            self.label("This wizard downloads the system and writes it directly to your USB drive. "
                       "No temporary files are created on your computer.")
            self.nav(nxt=None)
            if self.manifest:
                self.show_manifest()
            else:
                threading.Thread(target=self.fetch_manifest, daemon=True).start()

        def fetch_manifest(self):
            try:
                req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=15) as r:
                    m = json.loads(r.read().decode("utf-8"))
                if not str(m.get("url", "")).startswith("https://"):
                    raise ValueError("latest.json does not contain a valid https url")
                sha = str(m.get("sha256") or "")
                if sha and not re.fullmatch(r"[0-9a-fA-F]{64}", sha):
                    raise ValueError("latest.json contains an invalid sha256 value")
                self.q.put(("manifest", m))
            except Exception as e:
                self.q.put(("manifest_error", str(e)))

        def show_manifest(self):
            m = self.manifest
            size = f" - {fmt_size(m['size'])}" if m.get("size") else ""
            self.info.config(text=f"{m.get('name', 'CarryOS')} {m.get('version', '')}{size}")
            self.nav(nxt=self.step_disk)

        # ---- step 2: choose USB
        def step_disk(self):
            self.clear()
            ttk.Label(self.body, text="Select a USB drive", font=("", 15, "bold")).pack(anchor="w")
            self.lb = tk.Listbox(self.body, height=7, exportselection=False)
            self.lb.pack(fill="x", pady=(12, 6))
            self.lb.bind("<<ListboxSelect>>", lambda e: self.btn_next.state(["!disabled"]))
            ttk.Button(self.body, text="Refresh list", command=self.refresh_disks).pack(anchor="w")
            self.label("Only drives connected over USB are listed. ALL DATA on the selected drive will be erased.")
            self.nav(back=self.step_welcome, nxt=self.confirm_and_start, nxt_text="Write >")
            self.btn_next.state(["disabled"])
            self.refresh_disks()

        def refresh_disks(self):
            self.config(cursor="watch")
            self.update_idletasks()
            try:
                self.disks = list_usb_disks()
            except Exception as e:
                self.disks = []
                messagebox.showerror(APP_TITLE, f"Could not list disks:\n{e}")
            self.config(cursor="")
            self.lb.delete(0, "end")
            for d in self.disks:
                self.lb.insert("end", f"{d['name']}   ({fmt_size(d['size'])})   {d['path']}")
            if not self.disks:
                self.lb.insert("end", "No USB drive found. Plug one in and click 'Refresh list'.")
            self.btn_next.state(["disabled"])

        def confirm_and_start(self):
            sel = self.lb.curselection()
            if not sel or sel[0] >= len(self.disks):
                return
            disk = self.disks[sel[0]]
            need = self.manifest.get("size")
            if need and disk["size"] < need:
                messagebox.showerror(APP_TITLE, f"This USB drive is too small. At least {fmt_size(need)} is required.")
                return
            if not messagebox.askyesno(
                APP_TITLE,
                f"{disk['name']} ({fmt_size(disk['size'])})\n{disk['path']}\n\n"
                "ALL DATA ON THIS USB DRIVE WILL BE PERMANENTLY ERASED.\nContinue?",
                icon="warning",
            ):
                return
            self.step_write(disk)

        # ---- step 3: writing
        def step_write(self, disk):
            self.clear()
            ttk.Label(self.body, text="Writing", font=("", 15, "bold")).pack(anchor="w")
            self.status = self.label("Preparing...")
            self.bar = ttk.Progressbar(self.body, maximum=1000, length=555)
            self.bar.pack(pady=14)
            self.label("Do not unplug the USB drive or close this window until the process is finished.")
            self.nav(close_text="Cancel")
            self.cancel.clear()
            self.busy = True
            threading.Thread(target=self.worker, args=(disk,), daemon=True).start()

        def worker(self, disk):
            emit = lambda *a: self.q.put(a)
            try:
                write_image(self.manifest, disk, emit, self.cancel)
                self.q.put(("done",))
            except Cancelled:
                self.q.put(("error", "Cancelled. The contents of the USB drive are now corrupt; you will need to write it again."))
            except Exception as e:
                self.q.put(("error", str(e)))

        def poll(self):
            try:
                while True:
                    msg = self.q.get_nowait()
                    kind = msg[0]
                    if kind == "manifest":
                        self.manifest = msg[1]
                        self.show_manifest()
                    elif kind == "manifest_error":
                        self.info.config(text=f"Could not get version information:\n{msg[1]}\n\nCheck your internet connection.")
                        self.nav(nxt=self.reload_manifest, nxt_text="Retry")
                    elif kind == "status":
                        self.status.config(text=msg[1])
                    elif kind == "progress":
                        if msg[1] < 0:
                            self.bar.config(mode="indeterminate")
                            self.bar.step(5)
                        else:
                            self.bar.config(mode="determinate", value=msg[1] * 1000)
                        self.status.config(text=msg[2] + (f"  {msg[1] * 100:.0f}%" if msg[1] >= 0 else ""))
                    elif kind == "done":
                        self.busy = False
                        self.step_done()
                    elif kind == "error":
                        self.busy = False
                        messagebox.showerror(APP_TITLE, msg[1])
                        self.step_disk()
            except queue.Empty:
                pass
            self.after(100, self.poll)

        def reload_manifest(self):
            self.info.config(text="Fetching version information...")
            self.nav(nxt=None)
            threading.Thread(target=self.fetch_manifest, daemon=True).start()

        # ---- step 4: done
        def step_done(self):
            self.clear()
            ttk.Label(self.body, text="All done!", font=("", 20, "bold")).pack(anchor="w")
            if IS_MAC:
                self.label("The USB drive was written, verified and ejected. You can unplug it now.")
            else:
                self.label("The USB drive was written and verified. You can safely remove it.")
            self.label("To use it, shut down the computer and boot from the USB drive (open the boot menu "
                       "with F12, F10, F2 or Esc at startup; on a Mac, hold the Option key). "
                       "The setup wizard will greet you on first boot.")
            if IS_WIN:
                self.label("If Windows says you need to format the disk, click CANCEL.")
            if IS_MAC:
                self.label("If macOS says the disk is not readable, click 'Ignore' - do NOT click 'Initialize'.")
            self.nav(close_text="Close")

        def on_close(self):
            if self.busy:
                if not messagebox.askyesno(APP_TITLE, "Writing is in progress. If you cancel, the USB drive will be left corrupt. Cancel anyway?"):
                    return
                self.cancel.set()
            self.destroy()

    App().mainloop()


def main():
    if not is_admin():
        if relaunch_elevated():
            return
        try:
            import tkinter as tk
            from tkinter import messagebox
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror(APP_TITLE, "Administrator permission was not granted. It is required to write to the USB drive.")
        except Exception:
            print("Administrator permission is required.", file=sys.stderr)
        return
    run_gui()


if __name__ == "__main__":
    main()
