"""Read an in-progress PCM WAV without relying on its unfinished data length."""
from pathlib import Path
import struct


def read_growing_wav(path):
    """Return complete PCM samples, or None until a supported header is written.

    PipeWire/libsndfile finalizes RIFF lengths on Stop. Until then, read only
    the data bytes actually present, with an absolute 30-second upper bound.
    """
    with Path(path).open("rb") as stream:
        header = stream.read(12)
        if len(header) < 12:
            return None
        if header[:4] != b"RIFF" or header[8:] != b"WAVE":
            raise ValueError("Live preview requires a PCM WAV recording")
        supported = False
        for _ in range(64):
            chunk = stream.read(8)
            if len(chunk) < 8:
                return None
            name, size = struct.unpack("<4sI", chunk)
            if name == b"fmt ":
                if size < 16 or size > 4096:
                    raise ValueError("Unsupported WAV format header")
                fmt = stream.read(size)
                if len(fmt) < size:
                    return None
                codec, channels, rate, _, align, bits = struct.unpack("<HHIIHH", fmt[:16])
                supported = (codec, channels, rate, align, bits) == (1, 1, 16000, 2, 16)
                if size % 2:
                    stream.read(1)
            elif name == b"data":
                if not supported:
                    raise ValueError("Live preview requires mono 16 kHz, 16-bit PCM")
                # Zero and sentinel lengths are common until the recorder closes.
                limit = min(size, 960000) if 0 < size < 0x7FFFFFFF else 960000
                pcm = stream.read(limit)
                return pcm[:len(pcm) // 2 * 2]
            else:
                if size > 1048576:
                    return None
                stream.seek(size + size % 2, 1)
    return None
