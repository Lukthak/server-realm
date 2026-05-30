import json
import socket
import sys
import queue
import tkinter as tk
import tkinter.messagebox as mb
import urllib.request
from pathlib import Path

from config import SERVER_IP

_LOCAL_IPS = {"127.0.0.1", "localhost", "::1"}
_IS_LOCAL = SERVER_IP in _LOCAL_IPS

ICONO_PATH = str(Path(__file__).parent / "ICONO.ico")
_AUTH_URL = f"http://{SERVER_IP}:5556"


# ── Cliente HTTP (solo remoto) ───────────────────────────────────────────────

def _server_available() -> bool:
    try:
        with socket.create_connection((SERVER_IP, 5556), timeout=2):
            return True
    except Exception:
        return False


def _show_no_server_and_exit() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        _set_icon(root)
    except Exception:
        pass
    mb.showerror(
        "REALM — Sin conexión",
        f"No se puede conectar al servidor:\n{SERVER_IP}\n\nVerificá tu conexión o intentá más tarde.",
    )
    root.destroy()
    sys.exit()


def check_server_or_exit() -> None:
    if _IS_LOCAL:
        return
    if not _server_available():
        _show_no_server_and_exit()


def _auth_request(action: str, payload: dict) -> dict:
    if _IS_LOCAL:
        return {}
    try:
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{_AUTH_URL}/{action}", data=body,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=5)
        return json.loads(resp.read())
    except Exception:
        return {}  # falla silenciosamente — LOST en net.py maneja el cierre


def get_user_position(username: str, default_x: float, default_y: float) -> tuple:
    resp = _auth_request("get_pos", {"user": username})
    x = resp.get("x") if resp.get("x") is not None else default_x
    y = resp.get("y") if resp.get("y") is not None else default_y
    return float(x), float(y)


def save_user_position(username: str, x: float, y: float) -> None:
    _auth_request("save_pos", {"user": username, "x": x, "y": y})


def get_user_bio(username: str) -> str:
    return _auth_request("get_bio", {"user": username}).get("bio", "")


def save_user_bio(username: str, bio: str) -> None:
    _auth_request("save_bio", {"user": username, "bio": bio[:200]})


def get_user_max_chunks(username: str) -> int:
    return int(_auth_request("get_dist", {"user": username}).get("dist", 0))


def save_user_max_chunks(username: str, chunks: int) -> None:
    _auth_request("save_dist", {"user": username, "dist": chunks})


def get_user_skin(username: str) -> int:
    return int(_auth_request("get_skin", {"user": username}).get("skin", 0))


def save_user_skin(username: str, skin: int) -> None:
    _auth_request("save_skin", {"user": username, "skin": skin})


def open_bio_dialog(result_q: queue.Queue, done_event, current_bio: str) -> None:
    root = tk.Tk()
    root.title("Editar descripción")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    _center_window(root, 260, 110)
    _set_icon(root)

    var = tk.StringVar(value=current_bio)
    tk.Label(root, text="Descripción:").pack(pady=(10, 3))
    entry = tk.Entry(root, textvariable=var, width=32)
    entry.pack()
    entry.focus_set()
    entry.select_range(0, tk.END)

    def confirm(e=None):
        result_q.put(var.get()[:200])
        root.quit()

    def cancel(e=None):
        result_q.put(None)
        root.quit()

    entry.bind("<Return>", confirm)
    entry.bind("<Escape>", cancel)
    root.protocol("WM_DELETE_WINDOW", cancel)

    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=8)
    tk.Button(btn_frame, text="Guardar", width=8, command=confirm).pack(side="left", padx=4)
    tk.Button(btn_frame, text="Cancelar", width=8, command=cancel).pack(side="left", padx=4)

    root.mainloop()
    root.destroy()
    done_event.clear()


def _set_icon(root: tk.Tk) -> None:
    try:
        from PIL import Image, ImageTk
        pil_img = Image.open(ICONO_PATH).resize((32, 32))
        tk_icon = ImageTk.PhotoImage(pil_img)
        root.iconphoto(True, tk_icon)
    except Exception:
        pass


def _center_window(root: tk.Tk, w: int, h: int) -> None:
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
    root.minsize(w, h)
    root.maxsize(w, h)


def ask_nickname() -> str:
    """Pide usuario y contraseña. Registra si es nuevo, verifica si existe."""

    def _make_window(h: int) -> tk.Tk:
        root = tk.Tk()
        root.title("")
        root.resizable(False, False)
        root.attributes("-topmost", True)
        _center_window(root, 220, h)
        _set_icon(root)
        return root

    # ── Paso 1: pedir usuario ────────────────────────────────────────────────
    username: list[str] = [""]

    def ask_user():
        root = _make_window(95)
        var = tk.StringVar()
        tk.Label(root, text="Usuario:").pack(pady=(12, 3))
        entry = tk.Entry(root, textvariable=var, width=26)
        entry.pack()
        entry.focus_set()

        def confirm(e=None):
            if var.get().strip():
                username[0] = var.get().strip()[:16]
                root.quit()

        entry.bind("<Return>", confirm)
        root.protocol("WM_DELETE_WINDOW", sys.exit)
        btn = tk.Frame(root)
        btn.pack(pady=7)
        tk.Button(btn, text="OK", width=8, command=confirm).pack(side="left", padx=4)
        tk.Button(btn, text="Cancelar", width=8, command=sys.exit).pack(side="left", padx=4)
        root.mainloop()
        root.destroy()

    ask_user()
    user = username[0]

    # En modo local: solo el nombre, sin tocar ninguna DB
    if _IS_LOCAL:
        return user

    if not _server_available():
        _show_no_server_and_exit()

    is_new = not _auth_request("exists", {"user": user}).get("exists", False)

    # ── Paso 2: contraseña ───────────────────────────────────────────────────
    while True:
        password: list[str] = [""]
        error_msg = "Crear contraseña:" if is_new else "Contraseña:"

        def ask_pass(label_text=error_msg):
            root = _make_window(95)
            var = tk.StringVar()
            tk.Label(root, text=label_text).pack(pady=(12, 3))
            entry = tk.Entry(root, textvariable=var, width=26, show="*")
            entry.pack()
            entry.focus_set()

            def confirm(e=None):
                if var.get():
                    password[0] = var.get()
                    root.quit()

            entry.bind("<Return>", confirm)
            root.protocol("WM_DELETE_WINDOW", sys.exit)
            btn = tk.Frame(root)
            btn.pack(pady=7)
            tk.Button(btn, text="OK", width=8, command=confirm).pack(side="left", padx=4)
            tk.Button(btn, text="Cancelar", width=8, command=sys.exit).pack(side="left", padx=4)
            root.mainloop()
            root.destroy()

        ask_pass()
        pw = password[0]

        if is_new:
            _auth_request("register", {"user": user, "password": pw})
            break
        else:
            if _auth_request("login", {"user": user, "password": pw}).get("ok", False):
                break
            # contraseña incorrecta — volver a pedir con aviso
            error_msg = "Contraseña incorrecta:"

    return user


def open_chat_dialog(result_q: queue.Queue, done_event) -> None:
    root = tk.Tk()
    root.title("")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    _center_window(root, 200, 90)
    _set_icon(root)

    result = tk.StringVar()
    tk.Label(root, text="Mensaje:").pack(pady=(14, 4))
    entry = tk.Entry(root, textvariable=result, width=24)
    entry.pack()
    entry.focus_set()

    def confirm(e=None):
        result_q.put(result.get().strip()[:48])
        root.quit()

    def cancel(e=None):
        result_q.put("")
        root.quit()

    entry.bind("<Return>", confirm)
    entry.bind("<Escape>", cancel)
    root.protocol("WM_DELETE_WINDOW", cancel)

    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=8)
    tk.Button(btn_frame, text="Enviar", width=8, command=confirm).pack(side="left", padx=4)
    tk.Button(btn_frame, text="Cancel", width=8, command=cancel).pack(side="left", padx=4)

    root.mainloop()
    root.destroy()
    done_event.clear()
