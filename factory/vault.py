"""Move the sealed cases and the test author's transcript out of the project while the port agent works.

    python3 factory/vault.py lock ZCRED       before the port
    python3 factory/vault.py unlock ZCRED     before grading
"""
import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VAULT = os.path.expanduser(os.environ.get("PROOF_PORT_VAULT", "~/.proof-port-vault"))
FOLDERS = ("sealed", "work")


def lock(tcode):
    for name in FOLDERS:
        src = os.path.join(ROOT, "runs", tcode, name)
        dst = os.path.join(VAULT, tcode, name)
        if os.path.isdir(src):
            if os.path.exists(dst):
                raise SystemExit(f"{dst} already exists; unlock first")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            print(f"moved {name} to the vault")


def unlock(tcode):
    for name in FOLDERS:
        src = os.path.join(VAULT, tcode, name)
        dst = os.path.join(ROOT, "runs", tcode, name)
        if os.path.isdir(src):
            if os.path.exists(dst):
                raise SystemExit(f"{dst} already exists")
            shutil.move(src, dst)
            print(f"moved {name} back")


if __name__ == "__main__":
    {"lock": lock, "unlock": unlock}[sys.argv[1]](sys.argv[2].upper())
