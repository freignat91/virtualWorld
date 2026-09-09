"""Isolation temporaire des generateurs aleatoires globaux du processus."""

import random
from contextlib import contextmanager
from typing import Iterator

import numpy as np


@contextmanager
def preserve_rng_state() -> Iterator[None]:
    """Restaure les RNG, sans initialiser CUDA, meme en cas d'exception."""
    import torch

    python_state = random.getstate()
    numpy_state = np.random.get_state()
    torch_state = torch.get_rng_state()
    cuda_states = torch.cuda.get_rng_state_all() if torch.cuda.is_initialized() else None
    try:
        yield
    finally:
        random.setstate(python_state)
        np.random.set_state(numpy_state)
        torch.set_rng_state(torch_state)
        if cuda_states is not None:
            torch.cuda.set_rng_state_all(cuda_states)
