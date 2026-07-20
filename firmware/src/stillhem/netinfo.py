import socket


def primary_ip() -> str:
    """Best-effort primary LAN IPv4. Uses a UDP socket's local name (no packets
    are actually sent by connect() on a datagram socket). Falls back to loopback."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 53))  # TEST-NET-1; unreachable but sets a route
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()
