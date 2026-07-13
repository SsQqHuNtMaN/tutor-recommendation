from __future__ import annotations

import argparse
import socket


def port_is_available(host: str, port: int) -> bool:
    """Return whether a TCP port can be bound exclusively on the requested host."""
    if not 1 <= port <= 65535:
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
            if exclusive is not None:
                probe.setsockopt(socket.SOL_SOCKET, exclusive, 1)
            probe.bind((host, port))
    except OSError:
        return False
    return True


def find_available_port(host: str, start_port: int, search_size: int = 100) -> int:
    """Find the first bindable port, starting with the user's preferred port."""
    if not 1 <= start_port <= 65535:
        raise ValueError("start_port must be between 1 and 65535")
    if search_size < 1:
        raise ValueError("search_size must be positive")
    stop_port = min(start_port + search_size, 65536)
    for port in range(start_port, stop_port):
        if port_is_available(host, port):
            return port
    raise OSError(f"no available port found between {start_port} and {stop_port - 1}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Find an available loopback port for the local Viewer.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--start-port", type=int, default=8765)
    parser.add_argument("--search-size", type=int, default=100)
    args = parser.parse_args()
    try:
        port = find_available_port(args.host, args.start_port, args.search_size)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
