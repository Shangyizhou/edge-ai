"""旧Zipformer的真实流式校准捕获及独立RKNN量化构建。依赖置于外部venv。"""

import argparse
import hashlib
import json
import wave
from pathlib import Path

COMPONENTS = ("encoder", "decoder", "joiner")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    )


def sessions(model):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    return {
        name: ort.InferenceSession(
            str(model / f"{name}-epoch-99-avg-1.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        for name in COMPONENTS
    }


def capture(args):
    """运行float ONNX，捕获真实状态；公开转写样本不用于校准。"""
    import kaldi_native_fbank as knf
    import numpy as np

    models = sessions(args.model)
    metadata = models["encoder"].get_modelmeta().custom_metadata_map
    segment, step = int(metadata["T"]), int(metadata["decode_chunk_len"])
    context = int(
        models["decoder"].get_modelmeta().custom_metadata_map["context_size"]
    )
    rows = json.loads(args.fixtures.read_text())["fixtures"]
    selected = [row for row in rows if row["id"] in args.fixture_ids]
    if {r["id"] for r in selected} != set(args.fixture_ids):
        raise ValueError("unknown fixture selection")
    args.output.mkdir(parents=True)
    samples = {name: [] for name in COMPONENTS}
    identities = {name: [] for name in COMPONENTS}

    def save(name, feed, origin):
        same_fixture = sum(
            row["origin"]["fixture_id"] == origin["fixture_id"]
            for row in identities[name]
        )
        quota = max(1, args.max_samples // len(selected))
        if len(samples[name]) >= args.max_samples or same_fixture >= quota:
            return
        paths, entries = [], []
        index = len(samples[name])
        for i, node in enumerate(models[name].get_inputs()):
            tensor = feed[node.name]
            target = args.output / f"{name}-{index:03d}-{i:02d}.npy"
            if " " in str(target):
                raise ValueError("RKNN dataset paths cannot contain spaces")
            np.save(target, tensor, allow_pickle=False)
            paths.append(str(target.resolve()))
            entries.append(
                dict(
                    name=node.name,
                    path=str(target.resolve()),
                    shape=list(tensor.shape),
                    dtype=str(tensor.dtype),
                    sha256=sha256(target),
                    nonzero=int(np.count_nonzero(tensor)),
                )
            )
        samples[name].append(" ".join(paths))
        identities[name].append(dict(origin=origin, inputs=entries))

    transcripts = []
    for fixture in selected:
        path = Path(fixture["path"])
        if sha256(path) != fixture["sha256"]:
            raise ValueError("fixture SHA mismatch")
        with wave.open(str(path)) as audio:
            if (
                audio.getframerate(),
                audio.getsampwidth(),
                audio.getnchannels(),
            ) != (16000, 2, 1):
                raise ValueError("expected mono16k PCM16")
            waveform = (
                np.frombuffer(
                    audio.readframes(audio.getnframes()), dtype="<i2"
                ).astype(np.float32)
                / 32768
            )
        opts = knf.FbankOptions()
        opts.frame_opts.dither = 0
        opts.frame_opts.snip_edges = False
        opts.frame_opts.samp_freq = 16000
        opts.mel_opts.num_bins = 80
        opts.mel_opts.high_freq = -400
        computer = knf.OnlineFbank(opts)
        computer.accept_waveform(
            16000,
            np.concatenate([waveform, np.zeros(32000, dtype=np.float32)]),
        )
        computer.input_finished()
        features = np.stack(
            [computer.get_frame(i) for i in range(computer.num_frames_ready)]
        )
        states = {}
        for node in models["encoder"].get_inputs()[1:]:
            if not all(isinstance(d, int) and d > 0 for d in node.shape):
                raise ValueError("calibration requires fixed export shapes")
            dtype = {"tensor(float)": np.float32, "tensor(int64)": np.int64}[
                node.type
            ]
            states[node.name] = np.zeros(node.shape, dtype=dtype)
        hypothesis = [0] * context
        decoder_feed = {
            models["decoder"].get_inputs()[0].name: np.array(
                [hypothesis], dtype=np.int64
            )
        }
        save("decoder", decoder_feed, dict(fixture_id=fixture["id"], chunk=0))
        decoder_out = models["decoder"].run(None, decoder_feed)[0]
        for chunk, start in enumerate(
            range(0, len(features) - segment + 1, step)
        ):
            origin = dict(
                fixture_id=fixture["id"], chunk=chunk, feature_start=start
            )
            feed = dict(states, x=features[start : start + segment][None])
            # 每段最多固定块数，防止首条长语料耗尽全部校准预算。
            if chunk < args.chunks_per_fixture:
                save("encoder", feed, origin)
            outputs = models["encoder"].run(None, feed)
            state_outputs = {
                node.name: value
                for node, value in zip(
                    models["encoder"].get_outputs(), outputs
                )
            }
            states = {name: state_outputs["new_" + name] for name in states}
            for frame_index, frame in enumerate(outputs[0][0]):
                joiner_inputs = models["joiner"].get_inputs()
                joiner_feed = {
                    joiner_inputs[0].name: frame[None],
                    joiner_inputs[1].name: decoder_out,
                }
                # 间隔采集，让两个素材都进入较小的joiner校准集。
                if chunk < args.chunks_per_fixture and frame_index == 0:
                    save("joiner", joiner_feed, origin)
                token = int(
                    models["joiner"].run(None, joiner_feed)[0].argmax()
                )
                if token:
                    hypothesis.append(token)
                    decoder_feed = {
                        models["decoder"].get_inputs()[0].name: np.array(
                            [hypothesis[-context:]], dtype=np.int64
                        )
                    }
                    save("decoder", decoder_feed, origin)
                    decoder_out = models["decoder"].run(None, decoder_feed)[0]
        transcripts.append(
            dict(fixture_id=fixture["id"], token_ids=hypothesis[context:])
        )
    for name in COMPONENTS:
        (args.output / f"{name}.txt").write_text(
            "\n".join(samples[name]) + "\n"
        )
    write(
        args.output / "manifest.json",
        dict(
            kind="float-onnx-stateful-calibration-v1",
            model_metadata=metadata,
            model_hashes={
                n: sha256(args.model / f"{n}-epoch-99-avg-1.onnx")
                for n in COMPONENTS
            },
            fixtures=selected,
            input_samples=identities,
            float_token_outputs=transcripts,
            max_samples=args.max_samples,
            chunks_per_fixture=args.chunks_per_fixture,
        ),
    )
    print({name: len(rows) for name, rows in samples.items()}, flush=True)


def build(args):
    """每次只编译一个组件；保留float控制与INT8原始编译日志。"""
    from rknn.api import RKNN

    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / f"{args.component}-build.json").exists() or (
        args.output / f"{args.component}.rknn"
    ).exists():
        raise FileExistsError("refusing to overwrite component evidence")
    model = args.model / f"{args.component}-epoch-99-avg-1.onnx"
    custom = None
    if args.component == "encoder":
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        metadata = (
            ort.InferenceSession(
                str(model),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
            .get_modelmeta()
            .custom_metadata_map
        )
        keys = (
            "model_type",
            "attention_dims",
            "encoder_dims",
            "T",
            "left_context_len",
            "decode_chunk_len",
            "cnn_module_kernels",
            "num_encoder_layers",
        )
        custom = (
            ";".join(f"{key}={metadata[key]}" for key in keys)
            + ";context_size=2"
        )
    toolkit = RKNN(verbose=True)
    state = dict(
        component=args.component,
        quantized=args.int8,
        source_model=str(model),
        source_sha256=sha256(model),
        target="rk3566",
        custom_string=custom,
        calibration_manifest_sha256=sha256(args.calibration / "manifest.json")
        if args.int8
        else None,
        stages={},
    )
    try:
        result = toolkit.config(target_platform="rk3566", custom_string=custom)
        state["stages"]["config"] = result
        if result not in (0, None):
            raise RuntimeError("config failed")
        result = toolkit.load_onnx(model=str(model))
        state["stages"]["load_onnx"] = result
        if result != 0:
            raise RuntimeError("ONNX load failed")
        result = toolkit.build(
            do_quantization=args.int8,
            dataset=str((args.calibration / f"{args.component}.txt").resolve())
            if args.int8
            else None,
        )
        state["stages"]["build"] = result
        if result != 0:
            raise RuntimeError("RKNN build failed")
        target = args.output / f"{args.component}.rknn"
        result = toolkit.export_rknn(str(target))
        state["stages"]["export_rknn"] = result
        if result != 0:
            raise RuntimeError("RKNN export failed")
        state.update(
            status="ok",
            output_sha256=sha256(target),
            output_bytes=target.stat().st_size,
        )
    except Exception as error:
        state.update(status="error", error=str(error))
        raise
    finally:
        try:
            toolkit.release()
        finally:
            write(args.output / f"{args.component}-build.json", state)


def main():
    parser = argparse.ArgumentParser()
    operations = parser.add_subparsers(dest="operation", required=True)
    for operation in ("capture", "build"):
        command = operations.add_parser(operation)
        command.add_argument("--model", required=True, type=Path)
        command.add_argument("--output", required=True, type=Path)
        if operation == "capture":
            command.add_argument("--fixtures", required=True, type=Path)
            command.add_argument("--fixture-ids", required=True, nargs="+")
            command.add_argument("--max-samples", default=16, type=int)
            command.add_argument("--chunks-per-fixture", default=8, type=int)
        else:
            command.add_argument(
                "--component", required=True, choices=COMPONENTS
            )
            command.add_argument("--calibration", type=Path)
            command.add_argument("--int8", action="store_true")
    args = parser.parse_args()
    if args.operation == "build" and args.int8 and args.calibration is None:
        parser.error("INT8 requires calibration")
    globals()[args.operation](args)


if __name__ == "__main__":
    main()
