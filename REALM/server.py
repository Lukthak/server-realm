"""
Servidor REALM — correr con: python server.py
Escucha UDP, reenvía posiciones de todos los clientes entre sí.
Escribí HELP para ver los comandos disponibles.
"""
import hashlib
import json
import os
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from config import SERVER_PORT

AUTH_PORT = 5556

# ── Base de datos de usuarios ────────────────────────────────────────────────
_DB_PATH = Path(__file__).parent / "users.json"
_db_lock = threading.Lock()


def _load_db() -> dict:
    if _DB_PATH.exists():
        try:
            return json.loads(_DB_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_db(db: dict) -> None:
    _DB_PATH.write_text(json.dumps(db, indent=2), encoding="utf-8")


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


class _AuthHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length))
        except Exception:
            self._respond({"ok": False, "msg": "bad request"})
            return
        path = self.path.strip("/")

        with _db_lock:
            db = _load_db()

            if path == "exists":
                self._respond({"exists": body["user"] in db})

            elif path == "register":
                user = body["user"]
                if user in db:
                    self._respond({"ok": False, "msg": "Usuario ya existe"})
                else:
                    salt = os.urandom(16).hex()
                    db[user] = {"salt": salt, "hash": _hash_pw(body["password"], salt)}
                    _save_db(db)
                    self._respond({"ok": True})

            elif path == "login":
                user = body["user"]
                entry = db.get(user)
                if entry and _hash_pw(body["password"], entry["salt"]) == entry["hash"]:
                    self._respond({"ok": True})
                else:
                    self._respond({"ok": False})

            elif path == "get_pos":
                entry = db.get(body["user"], {})
                self._respond({
                    "x": entry.get("pos_x"),
                    "y": entry.get("pos_y"),
                })

            elif path == "save_pos":
                user = body["user"]
                if user in db:
                    db[user]["pos_x"] = body["x"]
                    db[user]["pos_y"] = body["y"]
                    _save_db(db)
                self._respond({"ok": True})

            elif path == "get_bio":
                entry = db.get(body.get("user", ""), {})
                self._respond({"bio": entry.get("bio", "")})

            elif path == "save_bio":
                user = body.get("user", "")
                if user in db:
                    db[user]["bio"] = str(body.get("bio", ""))[:200]
                    _save_db(db)
                self._respond({"ok": True})

            elif path == "get_dist":
                entry = db.get(body.get("user", ""), {})
                self._respond({"dist": entry.get("max_chunks", 0)})

            elif path == "save_dist":
                user = body.get("user", "")
                val = int(body.get("dist", 0))
                if user in db and val > db[user].get("max_chunks", 0):
                    db[user]["max_chunks"] = val
                    _save_db(db)
                self._respond({"ok": True})

            elif path == "get_skin":
                entry = db.get(body.get("user", ""), {})
                self._respond({"skin": entry.get("skin", 0)})

            elif path == "save_skin":
                user = body.get("user", "")
                if user in db:
                    db[user]["skin"] = int(body.get("skin", 0))
                    _save_db(db)
                self._respond({"ok": True})

    def _respond(self, data: dict) -> None:
        b = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(b))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):  # silenciar logs de acceso
        pass

TIMEOUT = 5.0
PACKET_IN_LEG = 80   # float x + float y + uint32 skin + uint32 chunks + 16s nick + 48s chat
PACKET_IN_EXT = 84   # float x + float y + float angle + uint32 skin + uint32 chunks + 16s nick + 48s chat
PACKET_PLAYER_LEG = 84   # uint32 id + float x + float y + uint32 skin + uint32 chunks + 16s nick + 48s chat
PACKET_PLAYER_EXT = 88   # uint32 id + float x + float y + float angle + uint32 skin + uint32 chunks + 16s nick + 48s chat
FORCE_EXT_PROTOCOL = False

clients = {}
next_id = 1
lock = threading.Lock()
running = True
kicked_addrs: dict = {}   # addr -> timestamp del kick
_KICK_TIMEOUT = 30.0      # segundos que el kicked no puede reconectarse


def _ts():
    t = time.localtime()
    return f"{t.tm_hour:02d}:{t.tm_min:02d}"


def _cleanup(now):
    stale = [a for a, c in clients.items() if now - c["last_seen"] > TIMEOUT]
    for a in stale:
        print(f"{clients[a]['nick']} se desconecto.")
        del clients[a]


def _cmd_loop():
    global running
    while running:
        try:
            cmd = input().strip()
        except EOFError:
            break
        cmd_upper = cmd.upper()
        if cmd_upper == "EXIT":
            running = False
            break
        elif cmd_upper == "ONLINE":
            with lock:
                if clients:
                    for c in clients.values():
                        print(f"  {c['nick']}")
                    print(f"  Total: {len(clients)} jugador(es)")
                else:
                    print("  No hay jugadores conectados.")
        elif cmd_upper.startswith("KICK "):
            target = cmd[5:].strip()
            with lock:
                found = [(addr, c) for addr, c in clients.items()
                         if c["nick"].lower() == target.lower()]
            if not found:
                print(f"  '{target}' no está conectado.")
            else:
                with lock:
                    for addr, c in found:
                        kicked_addrs[addr] = time.time()
                        del clients[addr]
                print(f"  {found[0][1]['nick']} fue kickeado.")
        elif cmd_upper == "HELP":
            print("  EXIT        — cerrar el servidor")
            print("  ONLINE      — ver jugadores conectados")
            print("  KICK <nick> — desconectar a un jugador")
            print("  HELP        — ver esta lista")
        elif cmd.strip():
            print(f"Comando desconocido. Escribi HELP para ver los comandos.")


def run(bind_ip="0.0.0.0"):
    global next_id
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((bind_ip, SERVER_PORT))
    sock.settimeout(0.5)
    threading.Thread(
        target=lambda: HTTPServer(("0.0.0.0", AUTH_PORT), _AuthHandler).serve_forever(),
        daemon=True,
    ).start()
    print(f"Servidor escuchando en {bind_ip}:{SERVER_PORT} — HELP para ver comandos")

    threading.Thread(target=_cmd_loop, daemon=True).start()

    while running:
        try:
            data, addr = sock.recvfrom(1024)
            if len(data) < PACKET_IN_LEG:
                continue

            # Ignorar jugadores kickeados durante _KICK_TIMEOUT segundos
            now_kick = time.time()
            if addr in kicked_addrs:
                if now_kick - kicked_addrs[addr] < _KICK_TIMEOUT:
                    continue
                else:
                    del kicked_addrs[addr]

            if len(data) >= PACKET_IN_EXT:
                x, y, angle, skin, chunks, raw_nick, raw_chat = struct.unpack("!fffII16s48s", data[:PACKET_IN_EXT])
                fmt = "ext"
            else:
                x, y, skin, chunks, raw_nick, raw_chat = struct.unpack("!ffII16s48s", data[:PACKET_IN_LEG])
                angle = 0.0
                fmt = "leg"

            if skin == 0xFFFFFFFF:
                with lock:
                    if addr in clients:
                        print(f"{clients[addr]['nick']} se desconecto.")
                        del clients[addr]
                continue

            nick = raw_nick.rstrip(b'\x00').decode('utf-8', errors='replace')
            chat = raw_chat.rstrip(b'\x00').decode('utf-8', errors='replace')
            now = time.time()

            with lock:
                if addr not in clients:
                    clients[addr] = {"id": next_id, "x": x, "y": y, "angle": angle, "skin": skin, "chunks": chunks, "nick": nick, "chat": chat, "last_seen": now, "fmt": fmt}
                    print(f"[{_ts()}] {nick} se conecto.")
                    next_id += 1
                else:
                    clients[addr]["x"] = x
                    clients[addr]["y"] = y
                    clients[addr]["angle"] = angle
                    clients[addr]["skin"] = skin
                    clients[addr]["chunks"] = chunks
                    clients[addr]["nick"] = nick
                    clients[addr]["chat"] = chat
                    clients[addr]["last_seen"] = now
                    clients[addr]["fmt"] = fmt

                _cleanup(now)

                recipient_fmt = "ext" if FORCE_EXT_PROTOCOL else clients.get(addr, {}).get("fmt", "leg")
                if recipient_fmt == "ext":
                    response = b"".join(
                        struct.pack("!IfffII16s48s", c["id"], c["x"], c["y"], c.get("angle", 0.0), c["skin"], c["chunks"],
                                    c["nick"].encode('utf-8')[:16].ljust(16, b'\x00'),
                                    c["chat"].encode('utf-8')[:48].ljust(48, b'\x00'))
                        for a, c in clients.items()
                        if a != addr
                    )
                else:
                    response = b"".join(
                        struct.pack("!IffII16s48s", c["id"], c["x"], c["y"], c["skin"], c["chunks"],
                                    c["nick"].encode('utf-8')[:16].ljust(16, b'\x00'),
                                    c["chat"].encode('utf-8')[:48].ljust(48, b'\x00'))
                        for a, c in clients.items()
                        if a != addr
                    )

            if response:
                sock.sendto(response, addr)
            else:
                # heartbeat: mantiene la conexión viva cuando el jugador está solo
                sock.sendto(b"\x00", addr)

        except socket.timeout:
            continue
        except Exception as e:
            if running:
                print(f"Error: {e}")

    sock.close()
    print("Servidor cerrado.")


if __name__ == "__main__":
    run()
