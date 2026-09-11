# RAT-HAILAMDEV

> **Mục đích học tập và phòng thủ.**
>
> Dự án này được xây dựng để nghiên cứu lập trình socket, TLS, giao thức JSON
> và các rủi ro khi phát triển công cụ quản trị từ xa. Chỉ chạy trên máy cá nhân,
> máy ảo hoặc hệ thống mà bạn sở hữu/được cấp phép kiểm thử. Không sử dụng để
> truy cập trái phép, thu thập dữ liệu, theo dõi người dùng hoặc phát tán mã độc.

## Giới thiệu

Đây là mô hình client/server tối giản viết bằng Python. Kênh liên lạc sử dụng
TLS 1.3 và dữ liệu trao đổi theo giao thức JSON từng dòng. Phiên bản này chỉ
phục vụ mục đích học tập — không sử dụng trong môi trường production.

## Features

- **Server**: Listens for client connections over TLS 1.3, supports asynchronous command processing
- **Client**: Connects via TLS, executes remote commands, gathers system info, lists directories, downloads/uploads files
- **Secure Transport**: End-to-end TLS 1.3 encryption for all communications
- **JSON Protocol**: Each request/response ends with a newline, simple action-based command set
- **Session Persistence**: All sessions are logged to `rat_sessions.json` when the server stops
- **Thread Safety**: Lock-protected client management and session logging
- **Keylogger**: Captures keystrokes via `pynput` with configurable flush intervals
- **Screenshot**: Cross-platform screen capture via `mss` (fallback: Pillow)
- **CLI**: Full argparse-based interface with subcommands (`server`, `client`, `gen-cert`)

## Supported Actions

| Action         | Description                                           |
|----------------|-------------------------------------------------------|
| `exec`         | Run an executable with parsed arguments (`shell=False`) |
| `sysinfo`      | Gather OS/hardware information                         |
| `ls`           | List directory contents                                |
| `download`     | Fetch a file from the server                           |
| `upload`       | Upload a file to the server                            |
| `screenshot`   | Capture a screenshot (base64-encoded PNG)              |
| `keylog`       | Start keylogger / retrieve buffered keystrokes         |
| `keylog_stop`  | Stop the keylogger                                     |
| `kill`         | Stop the server                                        |

## Requirements

- Python 3.9+
- OpenSSL (for self-signed certificates)
- Lab network or localhost only

### Pip Dependencies (optional)

```bash
pip install -r requirements.txt
```

| Package  | Purpose                          | Required |
|----------|----------------------------------|----------|
| `mss`    | Cross-platform screenshots       | Optional (fallback: Pillow) |
| `pynput` | Keylogger input capture          | Optional |
| `pillow` | Fallback screenshot backend      | Optional |

TLS, socket, threading, JSON — all handled by Python stdlib.

## Setup

```bash
git clone <URL_REPOSITORY>
cd RAT-HAILAMDEV
python3 --version
pip install -r requirements.txt
```

### Generate a self-signed certificate for testing:

```bash
# Automatic (requires openssl in PATH)
python3 rat.py gen-cert

# Or manual
openssl req -x509 -newkey rsa:2048 \
  -keyout server.key \
  -out server.crt \
  -days 365 -nodes \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

⚠️ **Do not commit `server.key` to Git.** Add generated files to `.gitignore`.

## Running

### Server

```bash
# Lab default (binds 0.0.0.0:4444)
python3 rat.py server

# Custom host and port
python3 rat.py server --host 127.0.0.1 --port 8443

# With keylogger flush every 5 seconds
python3 rat.py server --host 127.0.0.1 --keylog-interval 5
```

### Client

```bash
# Standard connection
python3 rat.py client 127.0.0.1 4444

# Skip TLS verification (lab only)
python3 rat.py client 127.0.0.1 4444 --no-verify

# Use a specific CA certificate
python3 rat.py client 127.0.0.1 4444 --cert /path/to/ca.crt
```

### Client Commands (interactive REPL)

```text
help                - Show available commands
sysinfo             - Get system information
ls                  - List current directory contents
ls /tmp             - List specific directory
exec whoami         - Run a command remotely
screenshot          - Capture and save a screenshot (./screenshots/)
keylog              - Start keylogger / retrieve buffered keystrokes
keylog_stop         - Stop the keylogger
download /path      - Download a file
upload /path <b64>  - Upload a file (base64-encoded data)
exit                - Close connection
```

When stopping the server with `Ctrl+C`, all sessions are saved to `rat_sessions.json`.

## Security Notes

- Server binds to `0.0.0.0` — consider binding to `127.0.0.1` in production-like tests
- No client authentication or authorization mechanism
- Any client that reaches the port can request the exposed actions; isolate the lab and never expose it to an untrusted network
- `exec` uses `shell=False` with `shlex` argument parsing; shell pipes/redirection are not supported
- File read/write paths are not sandboxed
- Self-signed certificate only suitable for lab environments
- Keylogger and screenshot modules are **opt-in** — install `pynput` and `mss` only when needed

## Development Direction

For defensive research, run in an isolated VM, bind to `127.0.0.1`, use dummy data, and remove the certificate after the lab session.

## License

This project is released under the [MIT License](LICENSE).

---

**Author:** Nguyen Xuan Hai

- LinkedIn: [linkedin.com/in/xuanhai0913](https://www.linkedin.com/in/xuanhai0913/)
- Facebook: [facebook.com/nguyenhai0913](https://www.facebook.com/nguyenhai0913)
