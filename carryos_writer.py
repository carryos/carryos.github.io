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
import secrets
import shlex
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

APP_TITLE = "CarryOS Writer"
# After publishing latest.json, replace this with your own address
# (or set the DISTRO_MANIFEST environment variable):
MANIFEST_URL = os.environ.get(
    "DISTRO_MANIFEST", "https://carryos.github.io/latest.json"
)
APP_VERSION = "1.1.2"
UA = "CarryOSWriter/" + APP_VERSION
BLOCK = 4 * 1024 * 1024
ALIGN = 4096  # safe alignment for 512-byte and 4Kn disks
IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
NO_WINDOW = 0x08000000 if IS_WIN else 0


class Cancelled(Exception):
    pass


# ------------------------------------------------------------- network safety
# Only https is accepted, also for redirects. (http://127.0.0.1 is allowed only
# when DISTRO_ALLOW_HTTP=1 is set, which is meant for local tests.)
ALLOW_HTTP = os.environ.get("DISTRO_ALLOW_HTTP") == "1"


def check_url(u):
    u = str(u)
    if u.startswith("https://") or (ALLOW_HTTP and u.startswith("http://127.0.0.1")):
        return u
    raise ValueError("Only https:// addresses are accepted.")


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _ssl_context():
    """System certificates + the bundled certifi list. On Windows the system store can
    miss roots such as Let's Encrypt, which silently breaks https for some PCs."""
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(cafile=certifi.where())
    except Exception:
        pass
    return ctx


_OPENER = urllib.request.build_opener(_HttpsOnly, urllib.request.HTTPSHandler(context=_ssl_context()))


def urlopen(req, timeout):
    check_url(req.full_url)
    return _OPENER.open(req, timeout=timeout)


def load_manifest():
    """Downloads and validates latest.json. The SHA256 is mandatory."""
    req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": UA})
    with urlopen(req, timeout=15) as r:
        m = json.loads(r.read(1 << 20).decode("utf-8"))
    check_url(m.get("url", ""))
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(m.get("sha256") or "")):
        raise ValueError("latest.json does not contain a valid sha256 value")
    if m.get("size") is not None and int(m["size"]) <= 0:
        raise ValueError("latest.json contains an invalid size value")
    return m


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

    # Linux does not restart the whole program as root any more; only the small
    # write helper is elevated (see write_via_helper).
    return False


def self_args():
    """Command that starts this same program (used for the elevated write helper)."""
    appimage = os.environ.get("APPIMAGE")
    if appimage:  # the FUSE mount is private to the user: run the .AppImage file itself
        return [appimage]
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, os.path.abspath(__file__)]


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
                with urlopen(req, timeout=30) as r:
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


MAX_OUT = 8 * 1024 * 1024        # largest piece the decompressor may hand us at once
CACHE_EVERY = 64 * 1024 * 1024   # Linux: flush + drop the disk cache this often


def decode_chunk(dec, chunk):
    """Yields the decompressed data in pieces of at most MAX_OUT bytes.
    A zero-filled disk image compresses ~1000:1, so decompressing one 1 MB chunk in one go
    could suddenly need ~1 GB of RAM (and the OS memory protection then closes the program)."""
    if dec is None:
        yield chunk
        return
    if isinstance(dec, lzma.LZMADecompressor):
        out = dec.decompress(chunk, MAX_OUT)
        while True:
            if out:
                yield out
            if dec.eof or dec.needs_input:
                break
            out = dec.decompress(b"", MAX_OUT)
    else:  # zlib / gzip
        data = chunk
        while data:
            out = dec.decompress(data, MAX_OUT)
            if out:
                yield out
            data = dec.unconsumed_tail


def drop_cache(f, flush):
    """Linux: keep the kernel's disk cache small, so a 15 GB image never fills the RAM."""
    if not IS_LINUX:
        return
    try:
        if flush:
            os.fsync(f.fileno())
        os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
    except (OSError, AttributeError):
        pass


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

    # The drive list may be stale (drive swapped or removed): check again that this
    # is still the same USB drive, and never touch anything that is not USB.
    fresh = {d["path"]: d for d in list_usb_disks()}
    if dev not in fresh or fresh[dev]["size"] != disk["size"]:
        raise RuntimeError("The selected USB drive changed or was removed. Please select it again.")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(manifest.get("sha256") or "")):
        raise RuntimeError("Refusing to write: the image has no SHA256 to verify against.")
    check_url(url)

    emit("status", "Preparing the disk...")
    prepare_disk(disk)

    dl, dec, sha = Downloader(url, cancel), make_decoder(url), hashlib.sha256()
    buf, out_bytes = bytearray(), 0
    t0, last = time.time(), 0.0

    since_flush = 0
    with open_device(disk, True) as f:
        for chunk in dl.chunks():
            for data in decode_chunk(dec, chunk):
                sha.update(data)
                out_bytes += len(data)
                if out_bytes > disk["size"]:
                    raise RuntimeError("The image turned out larger than the USB drive.")
                buf += data
                while len(buf) >= BLOCK:
                    f.write(bytes(buf[:BLOCK]))
                    del buf[:BLOCK]
                    since_flush += BLOCK
                    if since_flush >= CACHE_EVERY:
                        since_flush = 0
                        drop_cache(f, True)
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
        run(["blockdev", "--flushbufs", dev])  # flushes AND invalidates this device's cache
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
            if done % CACHE_EVERY < BLOCK:
                drop_cache(f, False)
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


# ------------------------------------------------------ anonymous statistics
# Sends a few anonymous COUNTERS to the same GoatCounter that the website uses
# (cookie-free, no account, no IP stored). What is sent is exactly this and nothing else:
#   - the event:   opened / started / done / cancelled / failed (+ a failure category)
#   - the OS:      windows / linux / macos
#   - USB size:    a range such as "32gb" (never the name, brand, serial or path)
# No user name, computer name, file path, IP address or error text is ever sent.
# Turn off: untick the box in the first window, start with --no-stats, or set
# CARRYOS_NO_STATS=1.
STATS_URL = "https://carry.goatcounter.com/count"
STATS_OFF = ("--no-stats" in sys.argv) or os.environ.get("CARRYOS_NO_STATS") == "1"
OS_NAME = "windows" if IS_WIN else "macos" if IS_MAC else "linux"


def usb_bucket(size):
    gb = size / 1e9
    for limit, name in ((24, "16gb"), (48, "32gb"), (96, "64gb"), (192, "128gb")):
        if gb < limit:
            return name
    return "256gb-plus"


def fail_category(err):
    m = str(err).lower()
    for key, cat in (("permission", "permission"), ("changed or was removed", "usb-changed"),
                     ("not large enough", "usb-too-small"), ("larger than the usb", "usb-too-small"),
                     ("sha256 of the downloaded", "hash-mismatch"), ("verification failed", "verify"),
                     ("could not read the usb", "verify"), ("download", "download"),
                     ("server error", "download"), ("compressed file", "download"),
                     ("pkexec", "permission"), ("unexpectedly", "other")):
        if key in m:
            return cat
    return "other"


# GoatCounter silently drops requests whose User-Agent does not look like a browser
# (it treats them as bots), so the app identifies itself in a browser-style string.
_STATS_UA = {
    "windows": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "macos": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "linux": "Mozilla/5.0 (X11; Linux x86_64)",
}[OS_NAME] + " CarryOSWriter/" + APP_VERSION
STATS_DEBUG = os.environ.get("CARRYOS_STATS_DEBUG") == "1"


_STATS_LOG = os.path.join(tempfile.gettempdir(), "carryos-writer-stats.log")


def _stats_log(msg):
    """Tiny local log (path + result only, never leaves the computer) to diagnose problems."""
    try:
        if os.path.exists(_STATS_LOG) and os.path.getsize(_STATS_LOG) > 20000:
            os.remove(_STATS_LOG)
        with open(_STATS_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except Exception:
        pass
    if STATS_DEBUG and sys.stderr:
        print("[stats] " + msg, file=sys.stderr, flush=True)


def _send_ping(path, title):
    try:
        # GoatCounter counts one "visit" per (User-Agent + IP) and path for 8 hours. A short random
        # token makes every launch / write count separately; it identifies nobody.
        ua = _STATS_UA + " s/" + secrets.token_hex(3)
        qs = urllib.parse.urlencode({"p": path, "t": title, "e": "true",
                                     "rnd": secrets.token_hex(3)})
        req = urllib.request.Request(f"{STATS_URL}?{qs}", headers={"User-Agent": ua})
        with urlopen(req, timeout=8) as r:
            r.read(64)
            _stats_log(f"{path} -> HTTP {r.status}")
    except Exception as e:  # statistics must never disturb the user
        _stats_log(f"{path} FAILED: {type(e).__name__}: {e}")


def ping(enabled, event, *extra):
    """event: opened/started/done/cancelled/failed; extra: more breakdown paths."""
    if not enabled or STATS_OFF:
        return
    paths = [f"/writer/{event}", f"/writer/{event}-os/{OS_NAME}", *extra]
    def go():
        for pth in paths:
            _send_ping(pth, pth.strip("/").replace("/", " "))
    threading.Thread(target=go, daemon=True).start()


# ----------------------------------------------------- Linux: elevated helper
# The window runs as a normal user. Only this small helper runs as root: it has no
# GUI, no display access, and takes nothing but a device path (it re-downloads and
# re-validates the manifest itself and refuses anything that is not a USB drive).
def run_helper(dev):
    def emit(*a):
        sys.stdout.write(json.dumps(a) + "\n")
        sys.stdout.flush()

    cancel = threading.Event()

    def watch_stdin():  # the window sends "cancel" (or just closes the pipe)
        try:
            for line in sys.stdin:
                if line.strip() == "cancel":
                    break
        except Exception:
            pass
        cancel.set()

    threading.Thread(target=watch_stdin, daemon=True).start()
    try:
        if not re.fullmatch(r"/dev/[A-Za-z0-9]+", dev or ""):
            raise RuntimeError("Invalid device path.")
        manifest = load_manifest()
        disk = next((d for d in list_usb_disks() if d["path"] == dev), None)
        if disk is None:
            raise RuntimeError("The selected drive is not a USB drive or is no longer available.")
        write_image(manifest, disk, emit, cancel)
        emit("done")
    except Cancelled:
        emit("error", "cancelled")
    except Exception as e:
        emit("error", str(e))


def write_via_helper(disk, emit, cancel):
    env = [f"{k}={os.environ[k]}" for k in ("LANG",) if k in os.environ]
    if os.environ.get("APPIMAGE"):
        env.append("APPIMAGE_EXTRACT_AND_RUN=1")  # works even without FUSE for root
    cmd = ["pkexec", "/usr/bin/env", *env, *self_args(), "--helper", disk["path"]]
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, bufsize=1)
    except FileNotFoundError:
        raise RuntimeError("pkexec (polkit) was not found; it is needed to get permission to write to the USB drive.")

    def forward_cancel():
        while p.poll() is None:
            if cancel.is_set():
                try:
                    p.stdin.write("cancel\n")
                    p.stdin.flush()
                except Exception:
                    pass
                return
            time.sleep(0.2)

    threading.Thread(target=forward_cancel, daemon=True).start()
    finished = False
    for line in p.stdout:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg and msg[0] == "done":
            finished = True
        elif msg and msg[0] == "error":
            p.wait()
            if cancel.is_set():
                raise Cancelled()
            raise RuntimeError(str(msg[1]))
        elif msg:
            emit(*msg)
    rc = p.wait()
    if cancel.is_set():
        raise Cancelled()
    if not finished:
        if rc in (126, 127):
            raise RuntimeError("Administrator permission was not granted. It is required to write to the USB drive.")
        raise RuntimeError("The write process ended unexpectedly.")


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
            self.stats_on = not STATS_OFF
            self.stats_var = tk.BooleanVar(value=self.stats_on)
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
            if not STATS_OFF:
                ttk.Checkbutton(
                    self.body, variable=self.stats_var, command=self.stats_toggled,
                    text="Send anonymous usage statistics (only: started / finished / failed,\n"
                         "your OS and the USB size range - no names, no drive name or serial)",
                ).pack(anchor="w", pady=(16, 0))
            self.nav(nxt=None)
            if self.manifest:
                self.show_manifest()
            else:
                threading.Thread(target=self.fetch_manifest, daemon=True).start()
                ping(self.stats_on, "opened")

        def stats_toggled(self):
            self.stats_on = bool(self.stats_var.get())

        def fetch_manifest(self):
            try:
                self.q.put(("manifest", load_manifest()))
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
            on = self.stats_on
            ping(on, "started")
            try:
                if IS_LINUX and not is_admin():
                    write_via_helper(disk, emit, self.cancel)
                else:
                    write_image(self.manifest, disk, emit, self.cancel)
                ping(on, "done", f"/writer/done-usb/{usb_bucket(disk['size'])}")
                self.q.put(("done",))
            except Cancelled:
                ping(on, "cancelled")
                self.q.put(("error", "Cancelled. The contents of the USB drive are now corrupt; you will need to write it again."))
            except Exception as e:
                ping(on, "failed", f"/writer/failed-reason/{fail_category(e)}")
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
    if len(sys.argv) >= 3 and sys.argv[1] == "--helper":
        run_helper(sys.argv[2])
        return
    # Linux: the window runs unprivileged; only the write helper is elevated.
    if IS_LINUX or is_admin():
        run_gui()
        return
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


if __name__ == "__main__":
    main()
