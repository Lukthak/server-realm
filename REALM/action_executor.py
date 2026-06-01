import sys
import time
from pathlib import Path


def _append_line(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")


def _read_new_lines(path: Path, pos: int) -> tuple[list[str], int]:
    if not path.exists():
        path.write_text("", encoding="utf-8")
    size = path.stat().st_size
    if pos > size:
        pos = 0
    with path.open("r", encoding="utf-8") as f:
        f.seek(pos)
        lines = [ln.rstrip("\n") for ln in f.readlines()]
        return lines, f.tell()


def main() -> int:
    if len(sys.argv) < 3:
        print("Uso: action_executor.py <in_path> <out_path>")
        return 1

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    in_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not in_path.exists():
        in_path.write_text("", encoding="utf-8")
    if not out_path.exists():
        out_path.write_text("", encoding="utf-8")

    out_pos = out_path.stat().st_size

    print("=== REALM Action Executor ===")
    print("Comandos iniciales: help, get pos, get speed, get chunks, get nick, tp X Y, set speed V")
    print("Escribe exit para cerrar esta consola")

    while True:
        try:
            cmd = input("realm-cmd> ").strip()
        except EOFError:
            break
        except KeyboardInterrupt:
            print()
            break

        if not cmd:
            continue
        if cmd.lower() in {"exit", "quit"}:
            break

        _append_line(in_path, cmd)

        deadline = time.time() + 1.5
        got_any = False
        while time.time() < deadline:
            lines, out_pos = _read_new_lines(out_path, out_pos)
            if lines:
                got_any = True
                for line in lines:
                    print(line)
                break
            time.sleep(0.05)

        if not got_any:
            print("(sin respuesta del juego)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
