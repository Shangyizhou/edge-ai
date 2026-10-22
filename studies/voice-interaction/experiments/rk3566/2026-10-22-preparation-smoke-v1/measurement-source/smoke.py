"""One real inference per CPU deployment; no robot, recording or playback."""
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
import wave


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def asr(c, out):
    import numpy as np
    import sherpa_onnx
    with wave.open(c['input']['path']) as f:
        assert (f.getframerate(), f.getnchannels(), f.getsampwidth()) == (16000, 1, 2)
        samples = np.frombuffer(f.readframes(f.getnframes()), np.int16).astype(np.float32) / 32768
    assert sha(c['input']['path']) == c['input']['sha256']
    r = sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens=c['tokens'], encoder=c['encoder'], decoder=c['decoder'], joiner=c['joiner'],
        num_threads=2, provider='cpu', model_type='zipformer', decoding_method='greedy_search',
        enable_endpoint_detection=True, rule1_min_trailing_silence=2.4,
        rule2_min_trailing_silence=1.2, rule3_min_utterance_length=20)
    stream = r.create_stream()
    padded = np.concatenate([samples, np.zeros(51200, np.float32)])
    partials = []
    for pos in range(0, len(padded), 1600):
        stream.accept_waveform(16000, padded[pos:pos + 1600])
        while r.is_ready(stream):
            r.decode_stream(stream)
        text = r.get_result(stream)
        if not partials or partials[-1]['text'] != text:
            partials.append(dict(audio_offset_samples=pos, text=text))
    stream.input_finished()
    while r.is_ready(stream):
        r.decode_stream(stream)
    text = r.get_result(stream)
    save(out / 'asr-output.json', dict(transcript=text, partials=partials, engine=sherpa_onnx.__version__, delivery='100ms chunks without realtime pacing, 3.2s zero tail, EOF finish'))
    return dict(passed=bool(text.strip()) and any('\u3400' <= x <= '\u9fff' for x in text), output=text,
                expected='nonempty transcript containing Chinese from fixed nonsilent audio; not a CER threshold',
                reference=c['input'].get('reference'), output_file='asr-output.json')


def tts(c, out):
    import numpy as np
    import sherpa_onnx
    model = sherpa_onnx.OfflineTtsModelConfig(vits=sherpa_onnx.OfflineTtsVitsModelConfig(**c['vits']), num_threads=2, provider='cpu')
    synth = sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=model, **c['tts_config']))
    audio = synth.generate(c['input']['text'], sid=0, speed=1)
    a = np.asarray(audio.samples)
    finite = bool(np.isfinite(a).all())
    valid = bool(a.size and finite and np.any(a != 0) and audio.sample_rate > 0)
    if valid:
        pcm = (np.clip(a, -1, 1) * 32767).astype(np.int16)
        (out / 'generated.pcm').write_bytes(pcm.tobytes())
        with wave.open(str(out / 'generated.wav'), 'wb') as f:
            f.setparams((1, 2, audio.sample_rate, 0, 'NONE', ''))
            f.writeframes(pcm.tobytes())
        with wave.open(str(out / 'generated.wav')) as f:
            valid = valid and f.getnframes() > 0 and f.getnchannels() == 1 and f.getsampwidth() == 2 and bool(np.any(pcm != 0))
    result = dict(passed=bool(valid), expected='finite nonempty nonzero PCM and readable mono PCM16 WAV; no listening quality acceptance',
                  samples=int(a.size), sample_rate=audio.sample_rate, finite=finite,
                  listening_review='NOT_EVALUATED', output_file='generated.wav',
                  output_sha256=sha(out / 'generated.wav') if valid else None)
    save(out / 'tts-output.json', result)
    return result


def llm(c, out):
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    command = [c['binary'], '-m', c['model'], '--host', '127.0.0.1', '--port', str(port),
               '-t', '2', '-tb', '2', '-c', '2048', '-b', '128', '-ub', '64',
               '-ctk', 'f16', '-ctv', 'f16', '-ngl', '0', '-fa', 'off', '--no-warmup']
    save(out / 'server-command.json', command)
    with (out / 'native.log').open('w') as log:
        server = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            origin = 'http://127.0.0.1:' + str(port)
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError('server exited during loading')
                try:
                    with urlopen(origin + '/health', timeout=2) as f:
                        if json.load(f).get('status') == 'ok':
                            break
                except URLError:
                    pass
                time.sleep(.2)
            else:
                raise TimeoutError('model load exceeded 120s')
            payload = dict(prompt='<|im_start|>system\n你是机器人语音助手。只用简短中文回答。<|im_end|>\n<|im_start|>user\n' + c['input']['text'] + '<|im_end|>\n<|im_start|>assistant\n',
                           n_predict=16, temperature=0, seed=42, stream=False, cache_prompt=False)
            save(out / 'request.json', payload)
            req = Request(origin + '/completion', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
            with urlopen(req, timeout=90) as f:
                raw = f.read()
            (out / 'response.json').write_bytes(raw)
            response = json.loads(raw)
            text = response.get('content', '')
            return dict(passed=bool(text.strip()) and any('\u3400' <= x <= '\u9fff' for x in text), output=text,
                        expected='nonempty generated Chinese content; not instruction-quality acceptance',
                        tokens_predicted=response.get('tokens_predicted'), output_file='response.json')
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


def main():
    c = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2])
    save(out / 'input.json', c['input'])
    result = {'asr': asr, 'llm': llm, 'tts': tts}[c['module']](c, out)
    result.update(candidate=c['candidate'], inference_executed=True,
                  input_sha256=sha(out / 'input.json'), scope='minimal real inference only; no benchmark acceptance')
    save(out / 'validation.json', result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
