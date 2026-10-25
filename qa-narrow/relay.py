"""Local CONNECT relay so sandboxed Chromium can reach the internet.

Chromium in this sandbox cannot use the egress proxy directly (its proxy
connections get dropped); a raw CONNECT from curl/python succeeds. This
relay listens on 127.0.0.1:8899, forwards the CONNECT to the egress proxy
and pipes both directions. Pattern proven 2026-10-15 (Learn lab checks).

Usage: python3 relay.py   (runs forever; kill by PID when done)
"""
import socket
import threading

LISTEN = ("127.0.0.1", 8899)
EGRESS = ("hatch-egress-proxy", 3128)


def pipe(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        try:
            b.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def handle(client):
    try:
        req = b""
        while b"\r\n\r\n" not in req:
            chunk = client.recv(4096)
            if not chunk:
                return
            req += chunk
        line = req.split(b"\r\n", 1)[0].decode("latin1")
        parts = line.split(" ")
        if len(parts) < 2 or parts[0] != "CONNECT":
            client.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            return
        upstream = socket.create_connection(EGRESS, timeout=20)
        upstream.sendall(f"CONNECT {parts[1]} HTTP/1.1\r\n\r\n".encode("latin1"))
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = upstream.recv(4096)
            if not chunk:
                return
            resp += chunk
        client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        t1 = threading.Thread(target=pipe, args=(client, upstream), daemon=True)
        t2 = threading.Thread(target=pipe, args=(upstream, client), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except OSError:
        pass
    finally:
        try:
            client.close()
        except OSError:
            pass


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(LISTEN)
    srv.listen(50)
    print("relay listening on 127.0.0.1:8899", flush=True)
    while True:
        client, _ = srv.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
