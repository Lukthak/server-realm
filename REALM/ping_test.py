
"""
Monitor de conexión al servidor REALM.
Pulsa cada 15 segundos. Si el TCP cae, ejecuta el callback on_offline.
Puede usarse standalone (python ping_test.py) o importarse desde realm.py.
"""
import os
import signal
import socket
import subprocess
import sys
import threading
import time


from config import SERVER_IP, SERVER_PORT

AUTH_PORT = 5556
INTERVAL  = 15  # segundos entre pulsos


def check_tcp(host: str, port: int, timeout: float = 3.0) -> tuple[bool, float]:
    try:
        t0 = time.perf_counter()
        with socket.create_connection((host, port), timeout=timeout):
            ms = (time.perf_counter() - t0) * 1000
        return True, ms
    except Exception:
        return False, -1.0


def kill_realm() -> None:
    """Termina todos los procesos realm.py en ejecución."""
    killed = []
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True
        )
        # realm.py puede correr como python.exe — buscamos por línea de comando
        result2 = subprocess.run(
            ["wmic", "process", "where",
             "name='python.exe' or name='pythonw.exe' or name='REALM.exe'",
             "get", "ProcessId,CommandLine", "/FORMAT:CSV"],
            capture_output=True, text=True
        )
        for line in result2.stdout.splitlines():
            if "realm.py" in line.lower() or '"REALM.exe"' in line:
                parts = line.strip().split(",")
                for part in parts:
                    part = part.strip().strip('"')
                    if part.isdigit():
                        pid = int(part)
                        try:
                            os.kill(pid, signal.SIGTERM)
                            killed.append(pid)
                        except Exception:
                            pass
    except Exception as e:
        print(f"  [!] Error al buscar procesos: {e}")

    if killed:
        print(f"  [!] realm.py cerrado (PID: {', '.join(str(p) for p in killed)})")
    else:
        print("  [!] No se encontró realm.py en ejecución.")


def run_test() -> bool:
    """Retorna True si el servidor está online (TCP OK)."""
    now = time.strftime("%H:%M:%S")
    tcp_ok, tcp_ms = check_tcp(SERVER_IP, AUTH_PORT)

    if tcp_ok:
        print(f"[PING {now}] TCP:{AUTH_PORT}  CONECTADO  ({tcp_ms:.0f} ms)")
    else:
        print(f"[PING {now}] TCP:{AUTH_PORT}  SIN CONEXIÓN  >> OFFLINE")

    return tcp_ok


def start_monitor(on_offline=None) -> None:
    """
    Inicia el monitor de ping en un hilo daemon.
    on_offline: callable opcional que se llama cuando el TCP falla.
    """
    def _loop():
        print(f"[PING] Monitor iniciado — pulso cada {INTERVAL}s  |  {SERVER_IP}:{AUTH_PORT}")
        while True:
            online = run_test()
            if not online and on_offline:
                on_offline()
            time.sleep(INTERVAL)

    threading.Thread(target=_loop, daemon=True).start()


if __name__ == "__main__":
    print("=== REALM — Monitor de conexión standalone ===")
    print(f"Servidor : {SERVER_IP}  |  TCP:{AUTH_PORT}")
    print(f"Pulso    : cada {INTERVAL}s  |  Ctrl+C para salir")
    print("-" * 50)

    def _kill_realm():
        killed = []
        try:
            result2 = subprocess.run(
                ["wmic", "process", "where",
                 "name='python.exe' or name='pythonw.exe' or name='REALM.exe'",
                 "get", "ProcessId,CommandLine", "/FORMAT:CSV"],
                capture_output=True, text=True
            )
            for line in result2.stdout.splitlines():
                if "realm.py" in line.lower() or "REALM.exe" in line:
                    for part in line.strip().split(","):
                        part = part.strip().strip('"')
                        if part.isdigit():
                            try:
                                os.kill(int(part), signal.SIGTERM)
                                killed.append(part)
                            except Exception:
                                pass
        except Exception as e:
            print(f"  [!] Error: {e}")
        if killed:
            print(f"  [!] realm.py cerrado (PID: {', '.join(killed)})")
        else:
            print("  [!] No se encontró realm.py en ejecución.")

    try:
        while True:
            online = run_test()
            if not online:
                print("  [!] Servidor caído — cerrando realm.py...")
                _kill_realm()
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\nMonitor detenido.")
