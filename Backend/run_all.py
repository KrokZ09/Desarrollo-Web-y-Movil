"""Inicia los 7 servicios en esta terminal. Detener: Ctrl+C.

Uso (desde la carpeta Backend, con el .venv activo):
    python run_all.py
Los logs de cada servicio quedan en Backend/logs/ (no se suben a Git).
Todos escuchan solo en 127.0.0.1; el único punto de entrada es el gateway (puerto 8000).
"""
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).parent
SERVICES = [
    ("auth", 8001),
    ("clients", 8002),
    ("inventory", 8003),
    ("orders", 8004),
    ("payments", 8005),
    ("graphql", 8006),
    ("gateway", 8000),
]


def wait_ready(port: int, seconds: int = 20) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False


def main():
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    procs = []
    try:
        for name, port in SERVICES:
            log = open(logs / f"{name}.log", "w", encoding="utf-8")
            cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)]
            procs.append((name, port, subprocess.Popen(cmd, cwd=ROOT / name, stdout=log, stderr=subprocess.STDOUT), log))

        failed = []
        for name, port, proc, _ in procs:
            ok = wait_ready(port)
            print(f"  {'OK   ' if ok else 'FALLA'} {name:<10} puerto {port}")
            if not ok:
                failed.append(name)
        if failed:
            print(f"\nNo arrancaron: {', '.join(failed)}. Revisa Backend/logs/<servicio>.log")
        else:
            print("\nTodo listo. Entrada pública: http://127.0.0.1:8000  (Ctrl+C para detener)")

        while True:
            time.sleep(1)
            for name, port, proc, _ in procs:
                if proc.poll() is not None and name not in failed:
                    print(f"  El servicio {name} se detuvo (código {proc.returncode}). Ver logs/{name}.log")
                    failed.append(name)
    except KeyboardInterrupt:
        print("\nDeteniendo servicios...")
    finally:
        for _, _, proc, log in procs:
            if proc.poll() is None:
                proc.terminate()
        for _, _, proc, log in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            log.close()


if __name__ == "__main__":
    main()
