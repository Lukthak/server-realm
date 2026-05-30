import socket
import select
import struct
import threading
import time

from config import SERVER_IP, SERVER_PORT

_PACKET = 84          # uint32 id + float x + float y + uint32 skin + uint32 chunks + 16s nick + 48s chat
_HANDSHAKE_TIMEOUT  = 8.0   # segundos esperando primera respuesta del servidor
_DISCONNECT_TIMEOUT = 8.0   # segundos sin respuesta para declarar conexion perdida
_KEEPALIVE_INTERVAL = 1.0   # si el game loop no envia hace tanto, el hilo de red reenvia

# Poner en True para ver logs de red por consola. Debe quedar en False:
# los print() por paquete frenan el hilo receptor y provocan que el buffer
# del socket se llene de paquetes viejos, ocultando la desconexion real.
_DEBUG = False


def _log(msg: str) -> None:
    if _DEBUG:
        print(msg)


class UDPLink:
    # Estados de conexion
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
        self._first_send = 0.0
        self._last_packet = None   # ultimo paquete de posicion, para el keepalive
        self.ping_ms: float = 0.0
        self._ping_probe: float = 0.0  # tiempo del send que estamos midiendo
        threading.Thread(target=self._recv_loop, daemon=True).start()

    def _sendto(self, packet: bytes) -> bool:
        try:
            self._sock.sendto(packet, self._server)
            return True
        except Exception:
            return False

    def send(self, x, y, skin=0, chunks=0, nick="", chat=""):
        raw_nick = nick.encode('utf-8')[:16].ljust(16, b'\x00')
        raw_chat = chat.encode('utf-8')[:48].ljust(48, b'\x00')
        packet = struct.pack("!ffII16s48s", float(x), float(y), int(skin), int(chunks), raw_nick, raw_chat)
        self._last_packet = packet
        if self._sendto(packet):
            now = time.time()
            self._last_send = now
            if self._first_send == 0.0:
                self._first_send = now
            if self._ping_probe == 0.0:  # solo registra si no hay medicion en curso
                self._ping_probe = now

    def get_others(self):
        with self._lock:
            return dict(self._others)

    def _parse_state(self, data: bytes) -> dict:
        n = len(data) // _PACKET
        others = {}
        for i in range(n):
            chunk = data[i * _PACKET:(i + 1) * _PACKET]
            pid, x, y, skin, chunks, raw_nick, raw_chat = struct.unpack("!IffII16s48s", chunk)
            nick = raw_nick.rstrip(b'\x00').decode('utf-8', errors='replace')
            chat = raw_chat.rstrip(b'\x00').decode('utf-8', errors='replace')
            others[pid] = (x, y, skin, chunks, nick, chat)
        return others

    def _recv_loop(self):
        while self._running:
            try:
                ready, _, _ = select.select([self._sock], [], [], 0.1)
                now = time.time()

                if ready:
                    # Drenar TODO el backlog del socket en cada pasada. Procesar un
                    # solo paquete por iteracion dejaba acumular cientos de paquetes
                    # viejos; al morir el servidor el cliente seguia masticandolos y
                    # refrescaba _last_recv con datos rancios -> nunca detectaba LOST.
                    got_any = False
                    latest_state = None
                    while True:
                        try:
                            data, _ = self._sock.recvfrom(8192)
                        except BlockingIOError:
                            break  # buffer vacio: terminamos de drenar
                        except ConnectionResetError:
                            # ICMP port-unreachable (Windows): el peer no contesto este envio.
                            break
                        except OSError as e:
                            if (not self._running) or getattr(e, "winerror", None) == 10038:
                                return
                            break
                        if not data:
                            continue
                        got_any = True
                        if len(data) >= _PACKET:
                            latest_state = data        # nos quedamos solo con el mas reciente
                        # data == b"\x00": heartbeat del servidor (jugador solo) -> solo "vivo"

                    if got_any:
                        was_connected = self.status == self.CONNECTED
                        if self._ping_probe > 0.0:
                            self.ping_ms = (now - self._ping_probe) * 1000
                            self._ping_probe = 0.0
                        self._last_recv = now
                        self.status = self.CONNECTED
                        if latest_state is not None:
                            others = self._parse_state(latest_state)
                            with self._lock:
                                self._others = others
                        if not was_connected:
                            _log(f"[NET] Conectado a {SERVER_IP}:{SERVER_PORT}")

            except OSError as e:
                # Cierre normal en Windows cuando el socket se cierra desde otro hilo.
                if (not self._running) or (getattr(e, "winerror", None) == 10038):
                    break
                _log(f"[NET] Excepcion en recv_loop: {type(e).__name__}: {e}")
            except Exception as e:
                if not self._running:
                    break
                _log(f"[NET] Excepcion en recv_loop: {type(e).__name__}: {e}")

            self._keepalive()
            self._check_timeout()

    def _keepalive(self) -> None:
        """Reenvia el ultimo paquete si el game loop dejo de enviar (dialogo abierto,
        guardado HTTP sincronico, arrastre de ventana en Windows, lag). El servidor
        solo responde cuando recibe algo; sin esto, cualquier pausa del hilo principal
        cortaria las respuestas y se declararia una desconexion falsa."""
        if self._last_packet is None:
            return
        now = time.time()
        if now - self._last_send > _KEEPALIVE_INTERVAL:
            if self._sendto(self._last_packet):
                self._last_send = now
                if self._first_send == 0.0:
                    self._first_send = now

    def _check_timeout(self) -> None:
        """Marca LOST si paso demasiado tiempo sin respuesta del servidor."""
        now = time.time()
        if self.status == self.CONNECTED and self._last_recv > 0:
            if now - self._last_recv > _DISCONNECT_TIMEOUT:
                _log(f"[NET] LOST - sin respuesta por {now - self._last_recv:.1f}s")
                self.status = self.LOST
                with self._lock:
                    self._others = {}
        elif self.status == self.CONNECTING and self._first_send > 0:
            if now - self._first_send > _HANDSHAKE_TIMEOUT:
                _log(f"[NET] TIMEOUT - sin respuesta del servidor tras {_HANDSHAKE_TIMEOUT:.0f}s")
                self.status = self.LOST

    def update(self):
        """Llamar cada frame desde el game loop - doble check en el hilo principal,
        por si el hilo receptor queda bloqueado."""
        self._check_timeout()

    def disconnect(self):
        """Avisa al servidor que este cliente se va (paquete de 80 bytes, skin=0xFFFFFFFF)."""
        try:
            bye = struct.pack("!ffII16s48s", 0.0, 0.0, 0xFFFFFFFF, 0, b'\x00' * 16, b'\x00' * 48)
            self._sock.sendto(bye, self._server)
        except Exception:
            pass

    def stop(self):
        self._running = False
        try:
            self._sock.close()
        except Exception:
            pass
