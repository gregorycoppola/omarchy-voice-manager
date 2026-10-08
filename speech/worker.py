"""Isolated resident ONNX worker. stdout is a JSON-lines protocol, never logs."""
import json
import os
import sys
import time
import wave


def main():
    os.environ['HF_HUB_OFFLINE'] = '1'
    import numpy as np
    import onnx_asr
    import onnxruntime as ort
    from importlib.metadata import version
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1
    started = time.perf_counter()
    model = onnx_asr.load_model('nemo-parakeet-tdt-0.6b-v3', sys.argv[1],
        quantization='int8', providers=['CPUExecutionProvider'], sess_options=options)
    print(json.dumps({'ready': True, 'model_load_seconds': time.perf_counter() - started,
        'runtime': {'onnx_asr': version('onnx-asr'), 'onnxruntime': ort.__version__,
                    'provider': 'CPUExecutionProvider', 'threads': 4},
        'preprocessing': {'trailing_synthetic_silence_ms': 400, 'empty_retry_silence_ms':1000}}), flush=True)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            with wave.open(request['audio'], 'rb') as audio:
                if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
                    raise ValueError('Requires mono PCM16 16 kHz WAV.')
                if not 0 < audio.getnframes() <= 120 * 16000:
                    raise ValueError('Requires 0–120 seconds of audio.')
                samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(np.float32) / 32768
            # Release closes the microphone immediately. Supply deterministic
            # digital silence to the decoder, without recording or waiting longer.
            original_samples = samples
            samples = np.pad(samples, (0, 6400))
            # Timer covers inference on recorded audio plus synthetic tail.
            started = time.perf_counter()
            text = model.recognize(samples, sample_rate=16000)
            tail_ms=400;retried=False
            if isinstance(text,str) and not text.strip():
                text=model.recognize(np.pad(original_samples,(0,16000)),sample_rate=16000)
                tail_ms=1000;retried=True
            elapsed = time.perf_counter() - started
            if not isinstance(text, str):
                raise ValueError('Invalid transcript from ONNX runtime.')
            print(json.dumps({'ok': True, 'text': text, 'inference_seconds': elapsed, 'trailing_synthetic_silence_ms': tail_ms, 'empty_transcript_retry':retried}), flush=True)
        except Exception as exc:
            print(json.dumps({'ok': False, 'error': str(exc)}), flush=True)


if __name__ == '__main__':
    main()
