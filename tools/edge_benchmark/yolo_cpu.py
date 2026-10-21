"""用 ONNX Runtime CPU 与真实 YOLOv6 后处理测量旧权重导出候选。"""

import ctypes
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from workers import await_gate, emit


def run(config: dict, output: Path) -> None:
    """固定图像回放；显式保留 CPU 候选身份与输入丢帧。"""
    cv2.setNumThreads(1)
    image = cv2.imread(config["image"])
    if image is None:
        raise ValueError("unreadable YOLO image")
    image = cv2.resize(image, (config["width"], config["height"]))
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    options = ort.SessionOptions()
    options.intra_op_num_threads = config["threads"]
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    started = time.monotonic()
    session = ort.InferenceSession(
        config["model"], options, providers=["CPUExecutionProvider"]
    )
    input_name = session.get_inputs()[0].name
    expected = [[1, 85, 44, 80], [1, 85, 22, 40], [1, 85, 11, 20]]
    heads = sorted(session.get_outputs(), key=lambda h: -np.prod(h.shape))
    if [h.shape for h in heads] != expected:
        raise ValueError("CPU candidate requires 640x352 three-head graph")
    decoder = ctypes.CDLL(config["decoder"])
    pointer = ctypes.POINTER(ctypes.c_float)
    decoder.yolo_decode.argtypes = [pointer] * 3 + [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_float,
        ctypes.c_float,
        pointer,
    ]
    decoder.yolo_decode.restype = ctypes.c_int
    rows = np.empty((4620, 6), dtype=np.float32)
    emit(
        output,
        dict(
            event="loaded",
            load_seconds=time.monotonic() - started,
            engine_version=ort.__version__,
            providers=session.get_providers(),
            output_shapes=expected,
            provenance="legacy PT re-export; RKNN identity unproven",
        ),
    )

    def infer():
        """同一 RGB 拉伸与 /255 归一化，后处理复用 C++ 源码。"""
        begin = time.monotonic()
        resized = cv2.resize(image, (640, 352))
        tensor = np.ascontiguousarray(
            resized.transpose(2, 0, 1)[None], dtype=np.float32
        )
        tensor /= 255
        tensors = session.run([h.name for h in heads], {input_name: tensor})
        inferred = time.monotonic()
        count = decoder.yolo_decode(
            *(t.ctypes.data_as(pointer) for t in tensors),
            config["width"],
            config["height"],
            config.get("confidence", 0.3),
            config.get("nms", 0.3),
            rows.ctypes.data_as(pointer),
        )
        finished = time.monotonic()
        detections = [
            dict(
                **{"class": int(row[0])},
                confidence=float(row[1]),
                box=[int(v) for v in row[2:]],
            )
            for row in rows[:count]
        ]
        return begin, inferred, finished, detections

    for _ in range(3):
        infer()
    (output / "ready").write_text("ready")
    await_gate(config)
    start = time.monotonic()
    frame = processed = dropped = 0
    fps = config.get("fps", 0)
    offered = config["frames"]
    if offered <= 0 or fps < 0:
        raise ValueError("positive frame count and nonnegative fps required")
    while frame < offered:
        if fps:
            delay = start + frame / fps - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            latest = int((time.monotonic() - start) * fps)
            if latest >= offered:
                dropped += offered - frame
                break
            dropped += latest - frame
            frame = latest
        begin, inferred, finished, detections = infer()
        emit(
            output,
            dict(
                event="frame",
                frame=frame,
                start_monotonic=begin,
                end_monotonic=finished,
                seconds=finished - begin,
                infer_seconds=inferred - begin,
                post_seconds=finished - inferred,
                latency_seconds=finished - start - frame / fps
                if fps
                else finished - begin,
                detections=detections,
            ),
        )
        processed += 1
        frame += 1
    remaining = start + offered / fps - time.monotonic() if fps else 0
    if remaining > 0:
        time.sleep(remaining)
    wall = time.monotonic() - start
    emit(
        output,
        dict(
            event="sample",
            index=0,
            input=config["image"],
            seconds=wall,
            processed=processed,
            dropped=dropped,
            offered_frames=offered,
            fps=processed / wall,
            offered_fps=fps,
        ),
    )
