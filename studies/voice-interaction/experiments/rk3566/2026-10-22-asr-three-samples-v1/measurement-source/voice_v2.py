"""SOP v2 CPU adapters; no robot actions, recording, or playback."""

import hashlib
import json
import signal
import time
import wave
from pathlib import Path


def event(output, event_type, **fields):
    """Flush each event on the same monotonic clock as resource sampling."""
    with (output / "events.jsonl").open("a") as f:
        f.write(
            json.dumps(
                dict(
                    event=event_type,
                    monotonic_seconds=time.monotonic(),
                    **fields,
                ),
                ensure_ascii=False,
            )
            + "\n"
        )


def phase(output, name, state):
    event(output, "phase", name=name, state=state)


def input_timeout(signum, frame):
    """Abort an input when Python regains control; parent also caps process time."""
    raise TimeoutError("input exceeds 90s")


def pcm(filename):
    import numpy as np

    with wave.open(str(filename)) as f:
        if (f.getframerate(), f.getnchannels(), f.getsampwidth()) != (
            16000,
            1,
            2,
        ):
            raise ValueError("expected 16kHz mono PCM16")
        return (
            np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(
                np.float32
            )
            / 32768
        )


def asr(config, output):
    import numpy as np
    import sherpa_onnx

    fixtures = json.loads(Path(config["fixtures"]).read_text())["fixtures"]
    for row in fixtures:
        if (
            hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest()
            != row["sha256"]
        ):
            raise ValueError("fixture hash mismatch: " + row["id"])
    phase(output, "loading", "start")
    r = sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens=config["tokens"],
        encoder=config["encoder"],
        decoder=config["decoder"],
        joiner=config["joiner"],
        num_threads=config["threads"],
        provider="cpu",
        decoding_method="greedy_search",
        enable_endpoint_detection=True,
        rule1_min_trailing_silence=2.4,
        rule2_min_trailing_silence=1.2,
        rule3_min_utterance_length=20,
        model_type="zipformer",
    )
    phase(output, "loading", "end")
    event(output, "loaded", engine_version=sherpa_onnx.__version__)

    def decode(row, label):
        signal.signal(signal.SIGALRM, input_timeout)
        signal.alarm(90)
        audio = pcm(row["path"])
        duration = len(audio) / 16000
        padded = np.concatenate(
            [audio, np.zeros(int(config["tail_seconds"] * 16000), np.float32)]
        )
        stream = r.create_stream()
        start = time.monotonic()
        compute = 0.0
        first = None
        finals = []
        previous = ""
        phase(output, label, "start")
        for cursor in range(0, len(padded), 1600):
            if config["realtime"]:
                time.sleep(max(0, start + cursor / 16000 - time.monotonic()))
            arrived = time.monotonic()
            t = time.monotonic()
            stream.accept_waveform(16000, padded[cursor : cursor + 1600])
            while r.is_ready(stream):
                r.decode_stream(stream)
            text = r.get_result(stream)
            endpoint = r.is_endpoint(stream)
            compute += time.monotonic() - t
            if text and first is None:
                first = time.monotonic() - start
            if text != previous:
                event(
                    output,
                    "partial",
                    fixture=row["id"],
                    text=text,
                    elapsed_s=time.monotonic() - start,
                )
                previous = text
            event(
                output,
                "audio_block",
                fixture=row["id"],
                audio_offset_s=cursor / 16000,
                submission_lag_s=(
                    arrived - (start + cursor / 16000)
                    if config["realtime"]
                    else None
                ),
            )
            if endpoint:
                final = dict(
                    text=text,
                    kind="endpoint",
                    elapsed_s=time.monotonic() - start,
                )
                finals.append(final)
                event(output, "final", fixture=row["id"], **final)
                t = time.monotonic()
                r.reset(stream)
                compute += time.monotonic() - t
                previous = ""
        t = time.monotonic()
        stream.input_finished()
        while r.is_ready(stream):
            r.decode_stream(stream)
        text = r.get_result(stream)
        compute += time.monotonic() - t
        if text:
            final = dict(
                text=text,
                kind="eof_forced",
                elapsed_s=time.monotonic() - start,
            )
            finals.append(final)
            event(output, "final", fixture=row["id"], **final)
        phase(output, label, "end")
        signal.alarm(0)
        event(
            output,
            "sample",
            fixture=row["id"],
            stage=label,
            first_partial_seconds=first,
            compute_seconds=compute,
            compute_rtf=compute / duration,
            original_audio_seconds=duration,
            tail_seconds=config["tail_seconds"],
            final_from_file_end_s=(
                finals[-1]["elapsed_s"] - duration
                if finals and config["realtime"]
                else None
            ),
            final_from_energy_anchor_s=(
                finals[-1]["elapsed_s"] - row["energy_end_s"]
                if finals
                and config["realtime"]
                and row.get("energy_end_s") is not None
                else None
            ),
            final_text="".join(x["text"] for x in finals),
            finals=finals,
            reference=row.get("reference"),
        )

    warm = next(x for x in fixtures if x["id"] == "official0")
    decode(warm, "first_request")
    decode(warm, "warmup")
    phase(output, "idle", "start")
    time.sleep(3)
    phase(output, "idle", "end")
    for row in fixtures:
        if row["id"] in config["fixture_ids"]:
            decode(row, "inference")
    from evaluation_metrics import quality

    rows = [
        json.loads(line)
        for line in (output / "events.jsonl").read_text().splitlines()
    ]
    scored = [
        dict(
            case_id=row["fixture"],
            reference=row["reference"],
            transcript=row["final_text"],
            output_status="complete",
        )
        for row in rows
        if row["event"] == "sample" and row.get("stage") == "inference"
    ]
    summary = quality(scored)
    (output / "quality.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )


def tts(config, output):
    import numpy as np
    import sherpa_onnx

    phase(output, "loading", "start")
    model = sherpa_onnx.OfflineTtsModelConfig(
        vits=sherpa_onnx.OfflineTtsVitsModelConfig(**config["vits"]),
        num_threads=2,
        provider="cpu",
    )
    synth = sherpa_onnx.OfflineTts(
        sherpa_onnx.OfflineTtsConfig(model=model, **config["tts_config"])
    )
    phase(output, "loading", "end")
    event(output, "loaded", engine_version=sherpa_onnx.__version__)
    for stage in ("first_request", "warmup"):
        phase(output, stage, "start")
        synth.generate("你好", sid=0, speed=1)
        phase(output, stage, "end")
    phase(output, "idle", "start")
    time.sleep(3)
    phase(output, "idle", "end")
    for i, text in enumerate(config["texts"]):
        phase(output, "inference", "start")
        start = time.monotonic()
        signal.signal(signal.SIGALRM, input_timeout)
        signal.alarm(90)
        audio = synth.generate(text, sid=0, speed=1)
        signal.alarm(0)
        generated = time.monotonic() - start
        samples = (np.clip(audio.samples, -1, 1) * 32767).astype(np.int16)
        ready = time.monotonic() - start
        phase(output, "inference", "end")
        with wave.open(str(output / (str(i) + ".wav")), "wb") as f:
            f.setparams((1, 2, audio.sample_rate, 0, "NONE", ""))
            f.writeframes(samples.tobytes())
        duration = len(samples) / audio.sample_rate
        event(
            output,
            "sample",
            index=i,
            input=text,
            seconds=generated,
            first_pcm_seconds=ready,
            pcm_boundary="whole utterance return then PCM16 conversion; not incremental",
            sample_rate=audio.sample_rate,
            samples=len(samples),
            rtf=generated / duration if duration else None,
            listening_review=None,
            speaker_first_sound_seconds=None,
        )


def run(config, output):
    """Select only the explicitly requested CPU module."""
    {"voice_v2_asr": asr, "voice_v2_tts": tts}[config["kind"]](config, output)
