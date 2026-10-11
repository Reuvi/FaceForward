"""Explicit setup-time download; never imported/called by the camera runtime."""
from pathlib import Path
import hashlib
import io
import urllib.request
import zipfile

URL = "https://github.com/zzqsld/zzqsld-tongue-analysis-api/releases/download/v3.0/tongue_seg_v8n_onnx.zip"
SHA256 = "885ecd06ec97fee5ed3959c85590c7a3dc3d10f134c7dc821c3b99f45506c35e"


def main():
    destination = Path("Vision/.local/tongue_seg.onnx")
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == SHA256:
        print(f"Verified existing {destination}")
        return
    print("Downloading tongue segmentation weights (CC BY-NC 4.0, noncommercial use).")
    with urllib.request.urlopen(URL, timeout=60) as response:
        archive = response.read(30_000_001)
    if len(archive) > 30_000_000:
        raise ValueError("Unexpectedly large model archive")
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        candidates = [item for item in bundle.infolist() if item.filename.endswith(".onnx")]
        if len(candidates) != 1 or candidates[0].file_size > 20_000_000:
            raise ValueError("Unexpected model archive contents")
        data = bundle.read(candidates[0])
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("Model checksum mismatch; nothing installed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".download")
    temporary.write_bytes(data)
    temporary.replace(destination)
    print(f"Installed and verified {destination}. See Vision/TONGUE_MODEL_NOTICE.md.")


if __name__ == "__main__":
    main()
