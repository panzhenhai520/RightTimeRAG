#!/usr/bin/env python3
"""Download Qwen3-ASR-1.7B — tries ModelScope first (faster in CN), falls back to HuggingFace."""
import os, sys, time

TARGET = "/home/xsuper/app/newapp/models/Qwen3-ASR-1.7B"
HF_REPO = "Qwen/Qwen3-ASR-1.7B"
MS_REPO = "Qwen/Qwen3-ASR-1.7B"

os.makedirs(TARGET, exist_ok=True)

# Check if already downloaded
import glob
existing = glob.glob(os.path.join(TARGET, "*.safetensors")) + glob.glob(os.path.join(TARGET, "*.bin"))
if existing and os.path.exists(os.path.join(TARGET, "config.json")):
    print(f"Model already present at {TARGET} ({len(existing)} weight files)")
    sys.exit(0)

print(f"Downloading Qwen3-ASR-1.7B to {TARGET} ...")
t0 = time.time()

# Try ModelScope first
try:
    from modelscope import snapshot_download
    print("Trying ModelScope...")
    path = snapshot_download(MS_REPO, cache_dir=os.path.dirname(TARGET),
                             local_dir=TARGET)
    print(f"Downloaded via ModelScope in {time.time()-t0:.0f}s → {path}")
    sys.exit(0)
except Exception as e:
    print(f"ModelScope failed: {e}")

# Fall back to HuggingFace
try:
    from huggingface_hub import snapshot_download
    print("Trying HuggingFace Hub...")
    path = snapshot_download(
        repo_id=HF_REPO,
        local_dir=TARGET,
        ignore_patterns=["*.pt", "original/*"],
    )
    print(f"Downloaded via HuggingFace in {time.time()-t0:.0f}s → {path}")
    sys.exit(0)
except Exception as e:
    print(f"HuggingFace failed: {e}")
    sys.exit(1)
