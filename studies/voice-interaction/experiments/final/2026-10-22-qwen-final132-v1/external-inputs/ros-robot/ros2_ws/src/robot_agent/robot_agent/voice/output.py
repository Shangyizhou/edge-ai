"""语音回合输出：集中合成恢复、播放与原回合产物关联。"""

import asyncio
import json
import time
import wave
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import (
    AsyncIterator,
    Awaitable,
    Dict,
    Optional,
    Protocol,
    Tuple,
    TypeVar,
)

from robot_agent.conversation.provider import (
    ModelProtocolError,
    ModelTransportError,
)
from robot_agent.diagnostics import get_logger
from robot_agent.results import (
    AudioArtifact,
    TurnResult,
    VoiceRecord,
    result_to_json,
)
from robot_agent.shutdown import finish_tasks
from robot_agent.voice._async_speech_task import SpeechTransportError
from robot_audio.pcm import PcmAudio

LOGGER = get_logger(__name__)

OutputValue = TypeVar("OutputValue")


class SpeechOutput(Protocol):
    """合成 Adapter；完整成功才返回经过格式验证的内存PCM。"""

    async def synthesize(self, text: str, timeout: float) -> PcmAudio:
        """按期限合成；失败抛出I/O异常，不返回部分音频或写文件。"""
        ...

    def stop(self) -> None:
        """同步停止合成准入。"""
        ...

    async def aclose(self, deadline: Optional[float] = None) -> None:
        """释放合成连接。"""
        ...


class Playback(Protocol):
    """可等待播放与显式资源回收的设备Seam。"""

    async def __call__(self, audio: PcmAudio) -> None:
        """播放一份完整PCM；取消和超时必须回收播放器。"""
        ...

    async def aclose(self, deadline: Optional[float] = None) -> None:
        """在同一退出期限内回收播放器。"""
        ...


class VoiceOutput:
    """拥有输出状态；普通回合与显式核对一次完成输出及记录。"""

    def __init__(
        self,
        speech_output: SpeechOutput,
        output_dir: Path,
        playback: Optional[Playback],
        speech_timeout: float,
        tts_attempts: int,
        failure_threshold: int,
        retry_delay: float,
        *,
        save_reply_audio: bool = False,
        save_turn_records: bool = True,
    ) -> None:
        """接管合成 Adapter、播放回调及输出产物目录。"""
        self._output = speech_output
        self._directory = Path(output_dir).expanduser().resolve()
        self._directory.mkdir(parents=True, exist_ok=True)
        self._playback = playback
        self._speech_timeout = speech_timeout
        self._tts_attempts = tts_attempts
        self._failure_threshold = failure_threshold
        self._retry_delay = retry_delay
        self._save_reply_audio = save_reply_audio
        self._save_turn_records = save_turn_records
        self._closed = False
        self._active: Optional[asyncio.Task] = None
        self._closing: Optional[asyncio.Task] = None
        self._failures = 0
        self._tts_enabled = True
        self._transcripts: Dict[str, str] = {}
        self._last_record: Optional[VoiceRecord] = None
        self._pending_record: Optional[VoiceRecord] = None

    @property
    def idle(self) -> bool:
        """等待结束后可复用；原生 Adapter 另持有终态事实。"""
        return self._active is None and getattr(self._output, "idle", True)

    async def complete(
        self,
        result: TurnResult,
        text: str,
        session_state: str,
        *,
        reconcile_id: Optional[str] = None,
        input_failed: bool = False,
        asr_status: Optional[str] = None,
    ) -> VoiceRecord:
        """按入口资格输出并保存；核对从原记录恢复文本，不提交动作。"""
        excluded = (
            ("busy",)
            if reconcile_id is not None
            else ("ignored", "filtered", "busy")
        )
        if reconcile_id is not None:
            text = self._transcripts.get(reconcile_id, text)
        record = VoiceRecord(
            result, text, session_state, asr_status=asr_status
        )
        if any(action.status == "unknown" for action in result.actions):
            self._transcripts[result.turn_id] = text
        else:
            self._transcripts.pop(result.turn_id, None)
        if not input_failed and result.status not in excluded:
            record = await self._speak(record)
        return self._save(record)

    @asynccontextmanager
    async def incremental(
        self, text: str, session_state: str
    ) -> AsyncIterator["_IncrementalReplyOutput"]:
        """应用持有一轮输出上下文；输出不能反向调用 Agent。"""
        delivery = _IncrementalReplyOutput(self, text, session_state)
        try:
            yield delivery
        except BaseException:
            delivery.save_failure()
            raise

    def enable_tts(self) -> None:
        """显式清除连续失败并恢复后续回合合成，不重放既有回合。"""
        self._failures = 0
        self._tts_enabled = True

    def cancel(self) -> None:
        """停止新重试与播放，取消输出正在持有的本地I/O。"""
        if self._closed:
            return
        self._closed = True
        self._output.stop()
        if self._active is not None:
            self._active.cancel()

    async def aclose(self, deadline: Optional[float] = None) -> None:
        """回收合成、播放器和延迟任务，再释放语音连接。"""
        if self._closing is None:
            self.cancel()
            self._closing = asyncio.create_task(
                self._close_resources(deadline)
            )
        await asyncio.shield(self._closing)

    async def _close_resources(self, deadline: Optional[float]) -> None:
        """清理过程独立于外部关闭等待者的取消。"""
        tasks = [asyncio.create_task(self._output.aclose(deadline))]
        if self._active is not None:
            tasks.append(self._active)
        if self._playback is not None:
            tasks.append(asyncio.create_task(self._playback.aclose(deadline)))
        await finish_tasks(tasks, deadline)

    @property
    def last_record(self) -> Optional[VoiceRecord]:
        """最近输出快照供应用判断退出是否已有当前回合记录。"""
        return self._last_record

    def has_saved_record(self, turn_id: str) -> bool:
        """按回合归属判断是否已有持久记录，不将较新的本地输出算作该回合。"""
        return (self._directory / (turn_id + ".json")).exists()

    def save_shutdown(
        self,
        result: TurnResult,
        text: str,
        state: str,
        *,
        force_record: bool = False,
    ) -> VoiceRecord:
        """退出只保存新事实，不重新合成；保留已经完成的音频和输出事实。"""
        previous = self._last_record
        if previous is None or previous.turn_id != result.turn_id:
            previous = self._pending_record
        if previous is not None and previous.turn_id == result.turn_id:
            record = replace(previous, turn=result)
        else:
            record = VoiceRecord(
                result, self._transcripts.get(result.turn_id, text), state
            )
        record = self._save(record, force_record=force_record)
        if record.record_status == "failed":
            raise OSError("退出回合记录保存失败：" + result.turn_id)
        return record

    async def _wait(
        self,
        operation: Awaitable[OutputValue],
        timeout: Optional[float] = None,
    ) -> OutputValue:
        """保留原始本地操作，取消等待必须等待其资源清理。"""
        active = asyncio.ensure_future(operation)
        self._active = active
        try:
            if timeout is None:
                return await active
            return await asyncio.wait_for(active, timeout)
        finally:
            self._active = None

    async def _speak(
        self, record: VoiceRecord, *, archive_name: Optional[str] = None
    ) -> VoiceRecord:
        """完整PCM合成后播放；归档开关只决定是否额外保存WAV。"""
        if not self._tts_enabled or self._closed:
            return replace(record, tts_status="disabled")
        started = time.monotonic()
        LOGGER.info("[TTS] 开始合成；budget=%.2fs", self._speech_timeout)
        deadline = started + self._speech_timeout
        record = replace(record, tts_status="failed")
        try:
            for attempt in range(self._tts_attempts):
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self._closed:
                    break
                LOGGER.info(
                    "[TTS] 尝试 %s/%s remaining=%.2fs",
                    attempt + 1,
                    self._tts_attempts,
                    remaining,
                )
                try:
                    audio = await self._wait(
                        self._output.synthesize(record.reply, remaining),
                        remaining,
                    )
                except (OSError, asyncio.TimeoutError) as error:
                    if (
                        not isinstance(error, SpeechTransportError)
                        or attempt + 1 == self._tts_attempts
                    ):
                        break
                    delay = min(
                        self._retry_delay, max(0, deadline - time.monotonic())
                    )
                    if delay:
                        await self._wait(asyncio.sleep(delay))
                    continue
                LOGGER.info(
                    "[TTS] 合成完成；elapsed=%.2fs",
                    time.monotonic() - started,
                )
                self._failures = 0
                record = replace(
                    record,
                    tts_status="completed",
                    audio_archive_status="disabled",
                )
                if self._save_reply_audio:
                    record = replace(record, audio_archive_status="failed")
                    try:
                        audio_path = self._save_audio(
                            archive_name or record.turn_id, audio
                        )
                    except OSError:
                        return record
                    record = replace(
                        record,
                        audio_path=audio_path,
                        audio_archive_status="completed",
                    )
                if self._playback is not None and not self._closed:
                    record = replace(record, playback_status="failed")
                    LOGGER.info("[Playback] 开始播放")
                    try:
                        await self._wait(self._playback(audio))
                    except OSError:
                        pass
                    else:
                        record = replace(record, playback_status="completed")
                    LOGGER.info(
                        "[Playback] 结束；status=%s", record.playback_status
                    )
                return record
        except BaseException:
            # 取消与编程错误仍向外显露；先保存当时已知的回合和输出事实。
            self._save(record, force_record=True)
            raise
        LOGGER.warning(
            "[TTS] 未完成合成；elapsed=%.2fs", time.monotonic() - started
        )
        self._failures += 1
        self._tts_enabled = self._failures < self._failure_threshold
        return replace(
            record, tts_status="failed" if self._tts_enabled else "degraded"
        )

    def _save_audio(self, turn_id: str, audio: PcmAudio) -> str:
        """原子归档成功PCM；磁盘失败不触发合成重试或播放。"""
        destination = self._directory / (turn_id + ".wav")
        temporary = destination.with_suffix(".wav.tmp")
        try:
            with wave.open(str(temporary), "wb") as wav:
                wav.setparams(
                    (audio.channels, 2, audio.sample_rate, 0, "NONE", "PCM")
                )
                wav.writeframes(audio.data)
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        return str(destination)

    def _requires_action_record(
        self, record: VoiceRecord, force_record: bool
    ) -> bool:
        """已提交动作存在不完整或后续失败时，必须保留可核实事实。"""
        if not any(
            action.status != "not_executed" for action in record.actions
        ):
            return False
        return (
            force_record
            or record.status != "completed"
            or any(
                action.status not in ("real_success", "simulated_success")
                for action in record.actions
            )
            or record.tts_status in ("failed", "degraded")
            or record.playback_status == "failed"
            or record.audio_archive_status == "failed"
        )

    def _save(
        self, record: VoiceRecord, *, force_record: bool = False
    ) -> VoiceRecord:
        """按策略原子保存JSON；待核对原记录的确认更新同样必须落盘。"""
        must_save = (
            self._save_turn_records
            or self._requires_action_record(record, force_record)
            or (
                self._pending_record is not None
                and self._pending_record.turn_id == record.turn_id
            )
        )
        destination = self._directory / (record.turn_id + ".json")
        temporary = destination.with_suffix(".json.tmp")
        record = replace(
            record, record_status="completed" if must_save else "disabled"
        )
        self._last_record = record
        has_unknown = any(
            action.status == "unknown" for action in record.actions
        )
        if has_unknown:
            self._pending_record = record
        if not must_save:
            return record
        try:
            temporary.write_text(
                json.dumps(
                    result_to_json(record), ensure_ascii=False, indent=2
                ),
                encoding="utf-8",
            )
            temporary.replace(destination)
        except OSError:
            self._last_record = replace(record, record_status="failed")
            return self._last_record
        finally:
            if temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass
        if (
            not has_unknown
            and self._pending_record is not None
            and self._pending_record.turn_id == record.turn_id
        ):
            self._pending_record = None
        return record


class _IncrementalReplyOutput:
    """一轮输出的私有状态；App 调用消费和封口，不反向调用业务。"""

    def __init__(
        self, owner: VoiceOutput, text: str, session_state: str
    ) -> None:
        """借用唯一语音拥有者，保留本轮文字、前缀和停止事实。"""
        self._owner = owner
        self._text = text
        self._session_state = session_state
        self._pending = ""
        self._spoken = ""
        self._previous: Optional[VoiceRecord] = None
        self._received_text = ""
        self._artifacts: Tuple[AudioArtifact, ...] = ()
        self._received = False
        self._stopped = False

    async def _phrase(self, turn_id: str, content: str) -> None:
        """逐句串行合成播放；LLM 可并发生成，由消费等待施加背压。"""
        record = VoiceRecord(
            TurnResult(turn_id, "processing", content),
            self._text,
            self._session_state,
            spoken_text=self._spoken,
            incremental_status="partial",
            received_text=self._received_text,
            unplayed_text=self._received_text[len(self._spoken) :],
            audio_artifacts=self._artifacts,
        )
        sequence = len(self._artifacts) + 1
        interrupted = False
        try:
            record = await self._owner._speak(
                record, archive_name=f"{turn_id}.phrase-{sequence:04d}"
            )
        except BaseException:
            # _speak 先保存当前句的取消／异常事实，不能回退到上一句。
            record = self._owner.last_record
            interrupted = True
            raise
        finally:
            self._artifacts += (
                AudioArtifact(
                    sequence,
                    content,
                    record.audio_path,
                    record.tts_status,
                    record.playback_status,
                    record.audio_archive_status,
                ),
            )
            if record.playback_status == "completed":
                self._spoken += content
            self._stopped = (
                record.tts_status in ("failed", "degraded")
                or record.playback_status == "failed"
                or record.audio_archive_status == "failed"
            )
            self._previous = replace(
                record,
                spoken_text=self._spoken,
                received_text=self._received_text,
                unplayed_text=self._received_text[len(self._spoken) :],
                audio_artifacts=self._artifacts,
            )
            self._owner._last_record = self._previous
            if interrupted:
                self.save_failure()
        if self._stopped:
            raise ModelTransportError("speech_output_failed")

    async def consume(self, turn_id: str, delta: str) -> None:
        """句尾启动合成，超过8192字符的句子显式失败。"""
        self._received = True
        if self._stopped:
            return
        self._received_text += delta
        if self._previous is None:
            # 原回合归属在首次文字交付时成立，不等待成句或产生音频。
            self._previous = VoiceRecord(
                TurnResult(turn_id, "processing", ""),
                self._text,
                self._session_state,
                spoken_text="",
                audio_artifacts=(),
            )
        self._pending += delta
        while self._pending and not self._stopped:
            boundary = next(
                (
                    i + 1
                    for i, char in enumerate(self._pending)
                    if char in "。！？!?；;\n"
                ),
                None,
            )
            if (boundary or len(self._pending)) > 8192:
                raise ModelProtocolError("增量句子超过容量")
            if boundary is None:
                break
            content = self._pending[:boundary]
            self._pending = self._pending[boundary:]
            await self._phrase(turn_id, content)

    async def complete(self, result: TurnResult) -> VoiceRecord:
        """应用交付最终业务结果；正常尾句刷新，不重复前缀。"""
        if not self._received:
            return await self._owner.complete(
                result, self._text, self._session_state
            )
        if (
            result.status == "completed"
            and not self._stopped
            and self._pending
        ):
            await self._phrase(result.turn_id, self._pending)
        previous = self._previous
        if (
            previous is None
            and self._owner.last_record is not None
            and self._owner.last_record.turn_id == result.turn_id
        ):
            previous = self._owner.last_record
        if previous is None:
            previous = VoiceRecord(result, self._text, self._session_state)
        record = replace(
            previous,
            turn=result,
            spoken_text=self._spoken,
            received_text=self._received_text,
            unplayed_text=self._received_text[len(self._spoken) :],
            audio_artifacts=self._artifacts,
            incremental_status=(
                "completed"
                if result.status == "completed" and not self._stopped
                else "failed"
            ),
        )
        return self._owner._save(record)

    def save_failure(self) -> None:
        """异常只保存已有输出事实，不提交模型、动作或新语音。"""
        if self._previous is not None:
            self._owner._save(
                replace(
                    self._previous,
                    incremental_status="failed",
                    received_text=self._received_text,
                    unplayed_text=self._received_text[len(self._spoken) :],
                ),
                force_record=True,
            )
