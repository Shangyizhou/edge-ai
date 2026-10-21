"""仅通过真实ROS识别节点回放已有PCM，不连接Agent或声卡。"""

import argparse
import json
import signal
import subprocess
import threading
import time
import wave
from pathlib import Path

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from robot_interfaces.msg import AsrAudio, AsrEvent
from robot_interfaces.srv import SetAsrInput
from std_msgs.msg import String


def wait_for(predicate, timeout=5):
    """等待可观察事实，超过预算立即保留失败。"""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise TimeoutError("ROS observation deadline expired")
        time.sleep(0.01)


def main():
    """创建隔离节点，验证新流、暂停、错误恢复与连续流。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("binary")
    parser.add_argument("model")
    parser.add_argument("fixtures")
    parser.add_argument("output")
    parser.add_argument("--continuous-only", action="store_true")
    parser.add_argument("--gate-file")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    model = Path(args.model)
    fixtures = Path(args.fixtures)
    observations = []
    states = []
    requests = []
    turns = []
    rclpy.init()
    node = Node("rknn_asr_replay")
    executor = SingleThreadedExecutor()
    executor.add_node(node)

    def observe(message):
        """保留实际接收时刻和流标识，避免跨流归因。"""
        observations.append(
            {
                "received": time.monotonic(),
                "stream_id": message.stream_id,
                "utterance_id": message.utterance_id,
                "kind": message.kind,
                "text": message.text,
                "detail": message.detail,
            }
        )

    subscription = node.create_subscription(
        AsrEvent, "/inference/asr/events", observe, 100
    )
    status_subscription = node.create_subscription(
        String,
        "/inference/asr/status",
        lambda message: states.append(
            {"received": time.monotonic(), "state": message.data}
        ),
        100,
    )
    publisher = node.create_publisher(AsrAudio, "/inference/asr/audio", 10)
    client = node.create_client(SetAsrInput, "/inference/asr/set_input")
    worker = threading.Thread(target=executor.spin)
    worker.start()
    command = [
        args.binary,
        "--ros-args",
        "-p",
        "provider:=rknn",
        "-p",
        "num_threads:=1",
        "-p",
        "endpoint_speech_silence:=1.2",
    ]
    for name in ("encoder", "decoder", "joiner", "tokens"):
        filename = name + (".txt" if name == "tokens" else ".rknn")
        command += ["-p", "{}:={}".format(name, model / filename)]
    log = (output / "native.log").open("w")
    process = subprocess.Popen(command, stdout=log, stderr=log)

    def control(stream_id, enabled=True):
        """等待native确认后才允许该流输入；不自动重试。"""
        request = SetAsrInput.Request()
        request.stream_id = stream_id
        request.enabled = enabled
        request.timeout_ms = 2000
        started = time.monotonic()
        future = client.call_async(request)
        wait_for(future.done, 3)
        response = future.result()
        requests.append(
            {
                "stream_id": stream_id,
                "enabled": enabled,
                "seconds": time.monotonic() - started,
                "applied": response.applied,
                "detail": response.detail,
            }
        )
        assert response.applied, response.detail

    def publish(stream_id, sequence, pcm):
        """发送带真实到达时间的连续16kHz PCM16消息。"""
        message = AsrAudio()
        message.stream_id = stream_id
        message.sequence = sequence
        message.sample_rate = 16000
        message.captured_at_ns = time.time_ns()
        message.pcm = list(pcm)
        publisher.publish(message)

    def replay(stream_id, filename):
        """按100ms节奏发送整段及3.2秒尾静音，保存接收墙钟。"""
        control(stream_id)
        with wave.open(str(fixtures / filename), "rb") as audio:
            assert (
                audio.getnchannels(),
                audio.getframerate(),
                audio.getsampwidth(),
            ) == (1, 16000, 2)
            pcm = audio.readframes(audio.getnframes())
        pcm += bytes(102400)
        started = time.monotonic()
        lateness = []
        for sequence, offset in enumerate(range(0, len(pcm), 3200)):
            block = pcm[offset : offset + 3200]
            due = started + (offset + len(block)) / 32000
            time.sleep(max(0, due - time.monotonic()))
            lateness.append(max(0, time.monotonic() - due))
            publish(stream_id, sequence, block)
        control(stream_id, False)
        turns.append(
            {
                "stream_id": stream_id,
                "start": started,
                "filename": filename,
                "max_publish_lateness": max(lateness),
            }
        )
        assert any(
            e["kind"] == "final" and e["stream_id"] == stream_id
            for e in observations
        )

    try:
        assert client.wait_for_service(timeout_sec=20), process.poll()
        wait_for(lambda: publisher.get_subscription_count() > 0)
        (output / "ready").touch()
        if args.gate_file:
            wait_for(lambda: Path(args.gate_file).is_file(), 30)
        if not args.continuous_only:
            # 1. 每轮显式新流，验证模型常驻而encoder状态互相隔离。
            for index in range(6):
                replay("independent-{}".format(index), "command.wav")
            # 2. 暂停确认后，旧流音频不能再产生识别事件。
            count = len(observations)
            publish("independent-5", 999, bytes(3200))
            time.sleep(0.5)
            assert len(observations) == count
            # 3. 缺帧必须显式报错，再经全新流恢复。
            control("broken")
            publish("broken", 1, bytes(3200))
            wait_for(
                lambda: any(
                    e["kind"] == "error" and e["stream_id"] == "broken"
                    for e in observations
                )
            )
            replay("recovered", "command.wav")
        # 4. 同一stream保留端点reset，核查连续六轮的实际输出。
        replay("continuous", "conversation6.wav")
    finally:
        shutdown_started = time.monotonic()
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise
        finally:
            result = {
                "command": command,
                "returncode": process.returncode,
                "shutdown_seconds": time.monotonic() - shutdown_started,
                "events": observations,
                "states": states,
                "controls": requests,
                "turns": turns,
            }
            (output / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            )
            log.close()
            executor.shutdown()
            worker.join()
            node.destroy_subscription(subscription)
            node.destroy_subscription(status_subscription)
            node.destroy_node()
            rclpy.shutdown()
    assert process.returncode == 0
    print(output / "result.json")


if __name__ == "__main__":
    main()
