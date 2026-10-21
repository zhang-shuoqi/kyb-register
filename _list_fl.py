"""Download cor READMEs (format definitions)."""
import paramiko
from pathlib import Path

OUT = Path(__file__).parent / "data" / "sunbiz_docs"
OUT.mkdir(parents=True, exist_ok=True)

transport = paramiko.Transport(("sftp.floridados.gov", 22))
transport.connect(username="Public", password="PubAccess1845!")
sftp = paramiko.SFTPClient.from_transport(transport)

candidates = [
    "doc/cor/README.TXT",
    "doc/cor/99-README.TXT",
    "doc/gen/README.TXT",
    "doc/gen/99-README.TXT",
    "doc/WELCOME.TXT",
]
for remote in candidates:
    try:
        size = sftp.stat(remote).st_size
        local = OUT / Path(remote).name.replace("README.TXT", f"cor_README_{Path(remote).parent.name}.txt")
        sftp.get(remote, str(local))
        print(f"OK {remote} ({size} bytes) -> {local.name}")
    except Exception as e:
        print(f"-- {remote}: {e}")

sftp.close()
transport.close()
