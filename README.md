# RAT-HAILAMDEV

> **Mục đích học tập và phòng thủ.**
>
> Dự án này được xây dựng để nghiên cứu lập trình socket, TLS, giao thức JSON
> và các rủi ro khi phát triển công cụ quản trị từ xa. Chỉ chạy trên máy cá nhân,
> máy ảo hoặc hệ thống mà bạn sở hữu/được cấp phép kiểm thử. Không sử dụng để
> truy cập trái phép, thu thập dữ liệu, theo dõi người dùng hoặc phát tán mã độc.

## Giới thiệu

This minimal client/server model written in Python. Communication channel is wrapped by TLS and data exchange follows a line-by-line JSON protocol. This version serves educational purposes only — do not use in production environments.

## Features

- **Server**: Listens for client connections over TLS 1.3, supports asynchronous command processing
- **Client**: Connects via TLS, executes remote commands, gathers system info, lists directories, downloads/uploads files
- **Secure Transport**: End-to-end TLS encryption for all communications
- **JSON Protocol**: Each request/response ends with a newline, simple action-based command set
- **Session Persistence**: All sessions are logged to `rat_sessions.json` when the server stops
- **Thread Safety**: Lock-protected client management and session logging

## Supported Actions

| Action | Description |
|--------|-------------|
| `exec` | Run arbitrary commands (via shell) |
| `sysinfo` | Gather OS/hardware information |
| `ls` | List directory contents |
| `download` | Fetch a file from the server |
| `upload` | Upload a file to the server |
| `kill` | Stop the server |

## Requirements

- Python 3.9+
- OpenSSL (for self-signed certificates)
- Lab network or localhost only

## Setup

```bash
git clone <URL_REPOSITORY>
cd RAT-HAILAMDEV
python3 --version
```

Generate a self-signed certificate for testing:

```bash
openssl req -x509 -newkey rsa:2048 \
  -keyout server.key \
  -out server.crt \
  -days 365 -nodes \
  -subj "/CN=localhost"
```

⚠️ **Do not commit `server.key` to Git.** Add generated files to `.gitignore`.

## Running

### Server

```bash
python3 rat.py server 4444
```

### Client

```bash
python3 rat.py client 127.0.0.1 4444
```

### Client Commands

```text
sysinfo          - Get system information
ls               - List directory contents
ls /tmp          - List specific directory
exec whoami      - Run a command remotely
download /path   - Download a file
upload /path     - Upload a file (base64 encoded)
exit             - Close connection
```

When stopping the server with `Ctrl+C`, all sessions are saved to `rat_sessions.json`.

## Security Notes

- Server binds to `0.0.0.0` — consider binding to `127.0.0.1` in production-like tests
- No client authentication or authorization mechanism
- `exec` uses `shell=True` — avoid in production (command injection risk)
- File read/write paths are not sandboxed
- Self-signed certificate only suitable for lab environments

## Development Direction

For defensive research, run in an isolated VM, bind to `127.0.0.1`, use dummy data, and remove the certificate after the lab session.

## License

This project is released under the [MIT License](LICENSE).

---

**Author:** Nguyen Xuan Hai

- LinkedIn: linkedin.com/in/xuanhai0913
- Facebook: facebook.com/nguyenhai0913
