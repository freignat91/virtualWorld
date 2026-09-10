"""Rapporte les versions et verifie CUDA sans entrainement ni sauvegarde."""

from importlib.metadata import version
import json
import multiprocessing
import platform

import torch


def main() -> None:
    report = {
        "python": platform.python_version(),
        "dependencies": {name: version(name) for name in (
            "torch", "stable-baselines3", "sb3-contrib", "gymnasium", "numpy")},
        "cuda_runtime": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "start_methods": multiprocessing.get_all_start_methods(),
        "torch_threads": torch.get_num_threads(),
    }
    if report["cuda_available"]:
        report["cuda_device"] = torch.cuda.get_device_name(0)
        try:
            result = torch.ones((8, 8), device="cuda") @ torch.ones((8, 8), device="cuda")
            torch.cuda.synchronize()
            report["cuda_compute_ok"] = bool(torch.all(result == 8).item())
        except RuntimeError as error:
            report["cuda_compute_ok"] = False
            report["cuda_error"] = str(error)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
