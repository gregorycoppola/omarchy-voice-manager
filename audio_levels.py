"""PCM amplitude measurement shared by the runtime and development meter."""
import math


def pcm_level(pcm):
    import numpy as np
    if not pcm:
        return 0.0, -90.0
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
    rms = float(np.sqrt(np.mean(samples * samples)))
    db = max(-90.0, 20 * math.log10(max(rms, 1e-9)))
    return min(1.0, max(0.0, (db + 60) / 60)), db

