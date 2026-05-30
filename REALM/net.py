import socket
import select
import struct
import threading
import time

from config import SERVER_IP, SERVER_PORT

_PACKET = 84          # uint32 id + float x + float y + uint32 skin + uint32 chunks + 16s nick + 48s chat
_HANDSHAKE_TIMEOUT = 5.0   # segundos esperando primera respuesta
_DISCONNECT_TIMEOUT = 15.0 # segundos sin respuesta para declarar conexión perdida
_RETRY_INTERVAL = 3.0      # segundos entre reintentos de conexión


class UDPLink:
    # Estados de conexión
    CONNECTING = "CONECTANDO"
    CONNECTED  = "CONECTADO"
    LOST       = "CONEXIÓN PERDIDA"

    def __init__(self):
        self._server = (SERVER_IP, SERVER_PORT)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._others = {}
        self._lock = threading.Lock()
        self._running = True
        self.status = self.CONNECTING
        self._last_recv = 0.0
        self._last_send = 0.0
        threading.Thread(target=self._recv_loop, daemon=True).start()

    def send(self, x, y, skin=0, chunks=0, nick="", chat=""):
        try:
            raw_nick  = nick.encode('utf-8')[:16].ljust(16, b'\x00')
            raw_chat  = chat.encode('utf-8')[:48].ljust(48, b'\x00')
            self._sock.sendto(
                struct.pack("!ffII16s48s", float(x), float(y), int(skin), int(chunks), raw_nick, raw_chat),
                self._server)
            self._last_send = time.time()
        except Exception:
            pass

    def get_others(self):
        with self._lock:
            return dict(self._others)

    def _recv_loop(self):
        while self._running:
            try:
                ready, _, _ = select.select([self._sock], [], [], 0.1)
                now = time.time()

                if ready:
                    data, _ = self._sock.recvfrom(8192)
                    n = len(data) // _PACKET
                    others = {}
                    for i in range(n):
                        chunk = data[i * _PACKET:(i + 1) * _PACKET]
                        pid, x, y, skin, chunks, raw_nick, raw_chat = struct.unpack("!IffII16s48s", chunk)
                        nick  = raw_nick.rstrip(b'\x00').decode('utf-8', errors='replace')
                        chat  = raw_chat.rstrip(b'\x00').decode('utf-8', errors='replace')
                        others[pid] = (x, y, skin, chunks, nick, chat)
                    was_connected = self.status == self.CONNECTED
                    self._last_recv = now
                    self.status = self.CONNECTED
                    with self._lock:
                        self._others = others
                    if not was_connected:
                        print(f"Conectado a {SERVER_IP}:{SERVER_PORT}")

                else:
                    # Detectar pérdida de conexión (>15s sin respuesta, sólo si ya conectamos)
                    if self.status == self.CONNECTED and self._last_recv > 0:
                        if now - self._last_recv > _DISCONNECT_TIMEOUT:
                            self.status = self.LOST
                            with self._lock:
                                self._others = {}

            except Exception as e:
                time.sleep(0.1)

    def disconnect(self):
        """Avisa al servidor que este cliente se va."""
        try:
            bye = struct.pack("!ffI16s48s", 0.0, 0.0, 0xFFFFFFFF, b'\x00' * 16, b'\x00' * 48)
            self._sock.sendto(bye, self._server)
        except Exception:
            pass

    def stop(self):
        self._running = False
        try:
            self._sock.close()
        except Exception:
            pass
