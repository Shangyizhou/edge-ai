#include <sherpa-onnx/c-api/c-api.h>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <csignal>
#include <deque>
#include <future>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#include "robot_interfaces/msg/asr_audio.hpp"
#include "robot_interfaces/msg/asr_event.hpp"
#include "robot_interfaces/srv/set_asr_input.hpp"
#include "std_msgs/msg/string.hpp"

using Audio   = robot_interfaces::msg::AsrAudio;
using Event   = robot_interfaces::msg::AsrEvent;
using Control = robot_interfaces::srv::SetAsrInput;
using Clock   = std::chrono::steady_clock;

class AsrNode : public rclcpp::Node {
    struct Change {
        std::string id;
        bool enabled;
        Clock::time_point deadline;
        std::promise<Control::Response> result;
    };

public:
    // 参数明确配置原生模型；构造阶段尚不接受音频。
    AsrNode() : Node("local_asr") {
        status_ = create_publisher<std_msgs::msg::String>("/inference/asr/status", rclcpp::QoS(1).transient_local().reliable());
        state("loading");
        encoder_           = declare_parameter<std::string>("encoder", "");
        decoder_           = declare_parameter<std::string>("decoder", "");
        joiner_            = declare_parameter<std::string>("joiner", "");
        tokens_            = declare_parameter<std::string>("tokens", "");
        sample_rate_       = declare_parameter<int>("sample_rate", 16000);
        max_age_ms_        = declare_parameter<int>("max_audio_age_ms", 500);
        max_queue_         = declare_parameter<int>("max_audio_queue", 10);
        max_frame_samples_ = declare_parameter<int>("max_frame_samples", 1600);
        provider_          = declare_parameter<std::string>("provider", "cpu");
        const int threads  = declare_parameter<int>("num_threads", 2);
        const auto rule1   = declare_parameter<double>("endpoint_silence", 2.4);
        const auto rule2   = declare_parameter<double>("endpoint_speech_silence", 1.2);
        const auto rule3   = declare_parameter<double>("endpoint_max_seconds", 20.0);
        if (encoder_.empty() || decoder_.empty() || joiner_.empty() || tokens_.empty() || sample_rate_ != 16000 || max_age_ms_ <= 0 || max_queue_ <= 0 ||
            max_frame_samples_ <= 0 || threads <= 0 || rule1 <= 0 || rule2 <= 0 || rule3 <= 0) {
            state("failed");
            throw std::invalid_argument("ASR model paths and positive 16kHz stream limits are required");
        }
        if (provider_ != "cpu" && provider_ != "rknn") {
            state("failed");
            throw std::invalid_argument("ASR provider must be cpu or rknn");
        }
        if (provider_ == "rknn" && threads != 1) {
            state("failed");
            throw std::invalid_argument("RKNN ASR requires num_threads=1 on RK3566");
        }
        SherpaOnnxOnlineRecognizerConfig config{};
        config.feat_config.sample_rate         = sample_rate_;
        config.feat_config.feature_dim         = 80;
        config.model_config.transducer.encoder = encoder_.c_str();
        config.model_config.transducer.decoder = decoder_.c_str();
        config.model_config.transducer.joiner  = joiner_.c_str();
        config.model_config.tokens             = tokens_.c_str();
        config.model_config.num_threads        = threads;
        config.model_config.provider           = provider_.c_str();
        config.decoding_method                 = "greedy_search";
        config.enable_endpoint                 = 1;
        config.rule1_min_trailing_silence      = rule1;
        config.rule2_min_trailing_silence      = rule2;
        config.rule3_min_utterance_length      = rule3;
        recognizer_                            = SherpaOnnxCreateOnlineRecognizer(&config);
        if (!recognizer_) {
            state("failed");
            throw std::runtime_error("Sherpa ASR model initialization failed");
        }

        // 1. ROS 回调仅交接有界任务，唯一 worker 独占 stream 和 decode。
        events_ = create_publisher<Event>("/inference/asr/events", rclcpp::QoS(10).reliable());
        audio_  = create_subscription<Audio>("/inference/asr/audio", rclcpp::QoS(10).reliable(), [this](Audio::SharedPtr frame) { enqueue(frame); });
        control_ =
            create_service<Control>("/inference/asr/set_input", [this](const Control::Request::SharedPtr request, Control::Response::SharedPtr response) {
                if (request->stream_id.empty() || request->timeout_ms == 0 || request->timeout_ms > 5000) {
                    response->detail = "invalid control request";
                    return;
                }
                auto change      = std::make_shared<Change>();
                change->id       = request->stream_id;
                change->enabled  = request->enabled;
                change->deadline = Clock::now() + std::chrono::milliseconds(request->timeout_ms);
                auto result      = change->result.get_future();
                {
                    std::lock_guard<std::mutex> lock(mutex_);
                    if (closing_ || change_) {
                        response->detail = "ASR control busy or closed";
                        return;
                    }
                    change_ = change;
                    audio_queue_.clear();
                    overflow_ = false;
                }
                ready_.notify_one();
                if (result.wait_until(change->deadline) != std::future_status::ready) {
                    response->detail = "ASR control deadline expired";
                    return;
                }
                *response = result.get();
            });
        worker_ = std::thread([this] { run(); });
        state("ready");
    }

    // 关闭先停止准入并发布 closing；等待真实 native 调用返回后才释放资源。
    void close() {
        if (!closing_.exchange(true)) state("closing");
        {
            std::lock_guard<std::mutex> lock(mutex_);
            audio_queue_.clear();
        }
        ready_.notify_one();
        if (worker_.joinable()) worker_.join();
    }

    // 原生资源只能在 worker 实际退场后销毁。
    ~AsrNode() override {
        close();
        if (stream_) SherpaOnnxDestroyOnlineStream(stream_);
        SherpaOnnxDestroyOnlineRecognizer(recognizer_);
    }

private:
    // 状态表示真实后端阶段；关闭不能被迟到 decode 的 ready 覆盖。
    void state(const std::string &value) {
        if (!rclcpp::ok() || (closing_ && value != "closing")) return;
        std_msgs::msg::String message;
        message.data = value;
        status_->publish(message);
    }

    // 队列溢出意味着不连续输入，整流失效，禁止静默丢帧后拼接。
    void enqueue(const Audio::SharedPtr &frame) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (closing_) return;
        if (audio_queue_.size() >= static_cast<size_t>(max_queue_)) {
            overflow_ = true;
            audio_queue_.clear();
        } else {
            audio_queue_.push_back(frame);
        }
        ready_.notify_one();
    }

    // 所有识别事件都关联当前实际 stream 和发言编号。
    void emit(const std::string &kind, const std::string &text, const std::string &detail = "") {
        if (!rclcpp::ok() || closing_) return;
        Event event;
        event.stream_id    = stream_id_;
        event.utterance_id = utterance_;
        event.kind         = kind;
        event.text         = text;
        event.detail       = detail;
        events_->publish(event);
    }

    // 错误终止当前输入；只有显式新流控制可重新使其可用。
    void fail(const std::string &detail) {
        state("failed");
        emit("error", "", detail);
        enabled_ = false;
        if (stream_) SherpaOnnxDestroyOnlineStream(stream_);
        stream_ = nullptr;
    }

    // 控制在 decode 边界生效，确认时旧流已销毁、新流已创建。
    void apply(const std::shared_ptr<Change> &change) {
        state("busy");
        Control::Response response;
        response.stream_id = change->id;
        if (Clock::now() >= change->deadline) {
            response.detail = "control expired before stream change";
            fail(response.detail);
            change->result.set_value(response);
            return;
        }
        if (change->enabled && change->id == stream_id_) {
            response.detail = "enable requires a fresh stream id";
            fail(response.detail);
            change->result.set_value(response);
            return;
        }
        enabled_ = false;
        if (stream_) SherpaOnnxDestroyOnlineStream(stream_);
        stream_        = nullptr;
        stream_id_     = change->id;
        next_sequence_ = 0;
        utterance_     = 0;
        last_partial_.clear();
        if (change->enabled) {
            stream_ = SherpaOnnxCreateOnlineStream(recognizer_);
            if (!stream_) {
                response.detail = "native stream creation failed";
                fail(response.detail);
                change->result.set_value(response);
                return;
            }
            enabled_ = true;
        }
        if (Clock::now() >= change->deadline) {
            enabled_ = false;
            if (stream_) SherpaOnnxDestroyOnlineStream(stream_);
            stream_         = nullptr;
            response.detail = "control expired during native stream creation";
            fail(response.detail);
            change->result.set_value(response);
            return;
        }
        state("ready");
        response.applied = true;
        change->result.set_value(response);
    }

    // 校验外部边界，再按连续 PCM 增量推进原生识别及端点。
    void recognize(const Audio &frame) {
        if (!enabled_ || frame.stream_id != stream_id_) return;
        const auto wall_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
        const bool stale   = frame.captured_at_ns > static_cast<uint64_t>(wall_ns) ||
                           static_cast<uint64_t>(wall_ns) - frame.captured_at_ns > static_cast<uint64_t>(max_age_ms_) * 1000000;
        if (frame.sequence != next_sequence_ || stale || frame.sample_rate != sample_rate_ || frame.pcm.empty() || frame.pcm.size() % 2 != 0 ||
            frame.pcm.size() / 2 > static_cast<size_t>(max_frame_samples_)) {
            fail("invalid, stale, or discontinuous audio frame");
            return;
        }
        state("busy");
        ++next_sequence_;
        std::vector<float> samples(frame.pcm.size() / 2);
        for (size_t i = 0; i < samples.size(); ++i) {
            const auto value = static_cast<int16_t>(static_cast<uint16_t>(frame.pcm[2 * i]) | (static_cast<uint16_t>(frame.pcm[2 * i + 1]) << 8));
            samples[i]       = value / 32768.0f;
        }
        SherpaOnnxOnlineStreamAcceptWaveform(stream_, sample_rate_, samples.data(), samples.size());
        while (SherpaOnnxIsOnlineStreamReady(recognizer_, stream_)) {
            SherpaOnnxDecodeOnlineStream(recognizer_, stream_);
        }
        const auto *result = SherpaOnnxGetOnlineStreamResult(recognizer_, stream_);
        if (!result) {
            fail("native recognizer result unavailable");
            return;
        }
        const std::string text = result->text ? result->text : "";
        SherpaOnnxDestroyOnlineRecognizerResult(result);
        if (SherpaOnnxOnlineStreamIsEndpoint(recognizer_, stream_)) {
            if (!text.empty()) emit("final", text);
            ++utterance_;
            last_partial_.clear();
            SherpaOnnxOnlineStreamReset(recognizer_, stream_);
        } else if (text != last_partial_) {
            last_partial_ = text;
            emit("partial", text);
        }
        state("ready");
    }

    // 优先处理控制，音频和控制永不并发使用原生 stream。
    void run() {
        while (true) {
            std::shared_ptr<Change> change;
            Audio::SharedPtr frame;
            bool overflow = false;
            {
                std::unique_lock<std::mutex> lock(mutex_);
                ready_.wait(lock, [this] { return closing_ || change_ || overflow_ || !audio_queue_.empty(); });
                if (closing_) {
                    if (change_) {
                        Control::Response response;
                        response.detail = "ASR closed";
                        change_->result.set_value(response);
                    }
                    return;
                }
                change.swap(change_);
                overflow  = overflow_;
                overflow_ = false;
                if (!change && !overflow) {
                    frame = audio_queue_.front();
                    audio_queue_.pop_front();
                }
            }
            if (change) apply(change);
            if (overflow && enabled_) fail("audio queue overflow");
            if (frame) recognize(*frame);
        }
    }

    std::string encoder_, decoder_, joiner_, tokens_, provider_;
    int sample_rate_, max_age_ms_, max_queue_, max_frame_samples_;
    const SherpaOnnxOnlineRecognizer *recognizer_ = nullptr;
    const SherpaOnnxOnlineStream *stream_         = nullptr;
    bool enabled_                                 = false;
    std::string stream_id_, last_partial_;
    uint64_t next_sequence_ = 0, utterance_ = 0;
    std::mutex mutex_;
    std::condition_variable ready_;
    std::atomic<bool> closing_{false};
    bool overflow_ = false;
    std::shared_ptr<Change> change_;
    std::deque<Audio::SharedPtr> audio_queue_;
    std::thread worker_;
    rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_;
    rclcpp::Publisher<Event>::SharedPtr events_;
    rclcpp::Subscription<Audio>::SharedPtr audio_;
    rclcpp::Service<Control>::SharedPtr control_;
};

namespace {
std::atomic<bool> stop_requested{false};
static_assert(std::atomic<bool>::is_always_lock_free, "signal flag must be lock free");
// 信号处理只设置标记，ROS 发布和 native 回收由正常主线程执行。
void request_stop(int) { stop_requested.store(true, std::memory_order_relaxed); }
}  // namespace

// 主线程在 ROS context 仍有效时发布关闭状态并等待唯一 worker 退场。
int main(int argc, char **argv) {
    rclcpp::InitOptions options;
    options.shutdown_on_sigint = false;
    rclcpp::init(argc, argv, options);
    rclcpp::uninstall_signal_handlers();
    std::signal(SIGINT, request_stop);
    std::signal(SIGTERM, request_stop);
    try {
        auto node = std::make_shared<AsrNode>();
        rclcpp::executors::SingleThreadedExecutor executor;
        executor.add_node(node);
        while (rclcpp::ok() && !stop_requested.load(std::memory_order_relaxed)) {
            executor.spin_some();
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        node->close();
        executor.remove_node(node);
    } catch (const std::exception &error) {
        RCLCPP_FATAL(rclcpp::get_logger("local_asr"), "%s", error.what());
        rclcpp::shutdown();
        return 1;
    }
    rclcpp::shutdown();
    return 0;
}
