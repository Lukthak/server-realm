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
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from config import SERVER_PORT, MAP_WIDTH, MAP_HEIGHT

AUTH_PORT = 5556

# ── Base de datos local (todos los usuarios en local.json) ──────────────────
_USERS_DIR = Path(__file__).parent / "users"
_USERS_DB_PATH = _USERS_DIR / "local.json"
_db_lock = threading.Lock()


def _safe_user_id(user: str) -> str:
    return str(user or "").strip()


def _normalize_db(data: dict) -> dict:
    users = {}
    if isinstance(data, dict):
        if isinstance(data.get("users"), dict):
            users = dict(data["users"])
        elif data.get("id"):
            # Legacy: local.json guardaba un unico perfil.
            users[str(data.get("id"))] = data
    return {
        "schema": 1,
        "users": users,
    }


def _load_db() -> dict:
    _USERS_DIR.mkdir(parents=True, exist_ok=True)
    db = {"schema": 1, "users": {}}

    if _USERS_DB_PATH.exists():
        try:
            db = _normalize_db(json.loads(_USERS_DB_PATH.read_text(encoding="utf-8")))
        except Exception:
            db = {"schema": 1, "users": {}}

    # Migracion suave desde archivos por usuario heredados (*.json, excepto local.json).
    for p in _USERS_DIR.glob("*.json"):
        if p.name.lower() == "local.json":
            continue
        try:
            entry = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(entry, dict):
            continue
        uid = _safe_user_id(entry.get("id") or p.stem)
        if not uid:
            continue
        db["users"].setdefault(uid, entry)

    return db


def _save_db(db: dict) -> None:
    _USERS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": 1,
        "users": db.get("users", {}),
    }
    _USERS_DB_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_user(user: str) -> dict:
    uid = _safe_user_id(user)
    if not uid:
        return {}
    return dict(_load_db().get("users", {}).get(uid, {}))


def _save_user(user: str, entry: dict) -> None:
    uid = _safe_user_id(user)
    if not uid:
        return
    db = _load_db()
    row = dict(entry)
    row["id"] = uid
    db.setdefault("users", {})[uid] = row
    _save_db(db)


def _user_exists(user: str) -> bool:
    uid = _safe_user_id(user)
    if not uid:
        return False
    return uid in _load_db().get("users", {})


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


def _default_inventory() -> dict:
    return {
        "schema": 1,
        "capacity": 24,
        "slots": [],
        "currencies": {
            "credits": 0,
        },
        "version": 1,
        "updated_at": int(time.time()),
    }


def _new_user_record(user: str, password: str) -> dict:
    salt = os.urandom(16).hex()
    return {
        "id": user,
        "salt": salt,
        "hash": _hash_pw(password, salt),
        "pos_x": float(MAP_WIDTH // 2),
        "pos_y": float(MAP_HEIGHT // 2),
        "bio": "",
        "max_chunks": 0,
        "skin": 0,
        "map_markers": {
            "stars": [],
            "blackholes": [],
        },
        "inventory": _default_inventory(),
    }


def _sanitize_map_markers(stars_raw, blackholes_raw) -> dict:
    stars: list[dict] = []
    blackholes: list[dict] = []

    if isinstance(stars_raw, list):
        for s in stars_raw[:5000]:
            if not isinstance(s, dict):
                continue
            try:
                x = int(s.get("x"))
                y = int(s.get("y"))
                c = s.get("color", [255, 255, 255])
                if not isinstance(c, (list, tuple)) or len(c) != 3:
                    c = [255, 255, 255]
                r = max(0, min(255, int(c[0])))
                g = max(0, min(255, int(c[1])))
                b = max(0, min(255, int(c[2])))
            except Exception:
                continue
            stars.append({"x": x, "y": y, "color": [r, g, b]})

    if isinstance(blackholes_raw, list):
        for b in blackholes_raw[:5000]:
            if not isinstance(b, dict):
                continue
            try:
                x = int(b.get("x"))
                y = int(b.get("y"))
            except Exception:
                continue
            blackholes.append({"x": x, "y": y})

    return {
        "stars": stars,
        "blackholes": blackholes,
    }


class _AuthHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length))
        except Exception:
            self._respond({"ok": False, "msg": "bad request"})
            return
        path = self.path.strip("/")

        try:
            with _db_lock:
                if path == "exists":
                    self._respond({"exists": _user_exists(body["user"])})

                elif path == "register":
                    user = body["user"]
                    if _user_exists(user):
                        self._respond({"ok": False, "msg": "Usuario ya existe"})
                    else:
                        _save_user(user, _new_user_record(user, body["password"]))
                        self._respond({"ok": True})

                elif path == "login":
                    user = body["user"]
                    entry = _load_user(user)
                    if entry and _hash_pw(body["password"], entry["salt"]) == entry["hash"]:
                        self._respond({"ok": True})
                    else:
                        self._respond({"ok": False})

                elif path == "get_pos":
                    entry = _load_user(body.get("user", ""))
                    self._respond({
                        "x": entry.get("pos_x"),
                        "y": entry.get("pos_y"),
                    })

                elif path == "save_pos":
                    user = body["user"]
                    entry = _load_user(user)
                    if not entry:
                        # En modo local, permitir persistencia sin registro previo.
                        entry = _new_user_record(user, "")
                    entry["pos_x"] = body["x"]
                    entry["pos_y"] = body["y"]
                    _save_user(user, entry)
                    self._respond({"ok": True})

                elif path == "get_bio":
                    entry = _load_user(body.get("user", ""))
                    self._respond({"bio": entry.get("bio", "")})

                elif path == "save_bio":
                    user = body.get("user", "")
                    entry = _load_user(user)
                    if not entry:
                        # En modo local, permitir persistencia sin registro previo.
                        entry = _new_user_record(user, "")
                    entry["bio"] = str(body.get("bio", ""))[:200]
                    _save_user(user, entry)
                    self._respond({"ok": True})

                elif path == "get_dist":
                    entry = _load_user(body.get("user", ""))
                    self._respond({"dist": entry.get("max_chunks", 0)})

                elif path == "save_dist":
                    user = body.get("user", "")
                    val = int(body.get("dist", 0))
                    entry = _load_user(user)
                    if not entry:
                        # En modo local, permitir persistencia sin registro previo.
                        entry = _new_user_record(user, "")
                    if val > entry.get("max_chunks", 0):
                        entry["max_chunks"] = val
                        _save_user(user, entry)
                    self._respond({"ok": True})

                elif path == "get_skin":
                    entry = _load_user(body.get("user", ""))
                    self._respond({"skin": entry.get("skin", 0)})

                elif path == "save_skin":
                    user = body.get("user", "")
                    entry = _load_user(user)
                    if not entry:
                        # En modo local, permitir persistencia sin registro previo.
                        entry = _new_user_record(user, "")
                    entry["skin"] = int(body.get("skin", 0))
                    _save_user(user, entry)
                    self._respond({"ok": True})

                elif path == "get_map":
                    entry = _load_user(body.get("user", ""))
                    mm = entry.get("map_markers", {}) if isinstance(entry, dict) else {}
                    stars = mm.get("stars", []) if isinstance(mm, dict) else []
                    blackholes = mm.get("blackholes", []) if isinstance(mm, dict) else []
                    self._respond({
                        "stars": stars if isinstance(stars, list) else [],
                        "blackholes": blackholes if isinstance(blackholes, list) else [],
                    })

                elif path == "save_map":
                    user = body.get("user", "")
                    entry = _load_user(user)
                    if not entry:
                        entry = _new_user_record(user, "")
                    entry["map_markers"] = _sanitize_map_markers(
                        body.get("stars", []),
                        body.get("blackholes", []),
                    )
                    _save_user(user, entry)
                    self._respond({"ok": True})

                elif path == "online":
                    with lock:
                        online_count = len(clients)
                    self._respond({"ok": True, "online": online_count})

                else:
                    self._respond({"ok": False, "msg": f"unknown action: {path}"})
        except Exception as ex:
            self._respond({"ok": False, "msg": f"server error: {type(ex).__name__}"})

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
_PROBE_NICK_PREFIX = "radio_probe"

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


def _find_port_owner_pid(port: int, proto: str = "tcp") -> int | None:
    """Best-effort lookup of the PID owning a local port on Windows."""
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True, errors="replace")
    except Exception:
        return None

    needle = f":{int(port)}"
    for line in out.splitlines():
        row = line.strip()
        if not row:
            continue
        up = row.upper()
        if proto.lower() == "tcp":
            if not up.startswith("TCP") or "LISTENING" not in up:
                continue
        else:
            if not up.startswith("UDP"):
                continue
        if needle not in row:
            continue
        parts = row.split()
        if not parts:
            continue
        try:
            return int(parts[-1])
        except Exception:
            continue
    return None


def _pid_cmdline(pid: int) -> str:
    try:
        # WMIC no siempre esta disponible; PowerShell CIM suele estarlo.
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-CimInstance Win32_Process -Filter \"ProcessId={int(pid)}\").CommandLine",
        ]
        out = subprocess.check_output(cmd, text=True, errors="replace").strip()
        return out or "(sin command line disponible)"
    except Exception:
        return "(no se pudo obtener command line)"


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
    try:
        sock.bind((bind_ip, SERVER_PORT))
    except OSError as e:
        if getattr(e, "winerror", None) == 10048:
            pid = _find_port_owner_pid(SERVER_PORT, proto="udp")
            if pid is not None:
                print(f"[ERROR] Puerto UDP {SERVER_PORT} en uso por PID {pid}")
                print(f"[ERROR] CMD: {_pid_cmdline(pid)}")
            else:
                print(f"[ERROR] Puerto UDP {SERVER_PORT} en uso por otro proceso")
            print("[TIP] Cerrá la otra instancia del server o liberá el puerto antes de iniciar.")
            return
        raise
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

            nick = raw_nick.rstrip(b'\x00').decode('utf-8', errors='replace')
            chat = raw_chat.rstrip(b'\x00').decode('utf-8', errors='replace')

            # Sondeo de Radio: responder snapshot sin registrarlo ni loguearlo.
            if nick.lower().startswith(_PROBE_NICK_PREFIX):
                with lock:
                    _cleanup(time.time())
                    recipient_fmt = "ext" if FORCE_EXT_PROTOCOL else fmt
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
                    sock.sendto(b"\x00", addr)
                continue

            if skin == 0xFFFFFFFF:
                with lock:
                    if addr in clients:
                        print(f"{clients[addr]['nick']} se desconecto.")
                        del clients[addr]
                continue
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
