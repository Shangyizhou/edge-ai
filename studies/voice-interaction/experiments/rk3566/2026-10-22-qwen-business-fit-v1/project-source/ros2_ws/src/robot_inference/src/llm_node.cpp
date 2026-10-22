#include <ggml-backend.h>
#include <llama.h>

#include <atomic>
#include <chrono>
#include <cmath>
#include <memory>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <robot_interfaces/action/generate_reply.hpp>
#include <std_msgs/msg/string.hpp>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "robot_inference/reply_grammar.hpp"

using Generate   = robot_interfaces::action::GenerateReply;
using GoalHandle = rclcpp_action::ServerGoalHandle<Generate>;
using Clock      = std::chrono::steady_clock;

namespace {
class GenerationError : public std::runtime_error {
public:
    // 仅承载本地生成已定义的失败码；ROS 报告和其他异常必须显露。
    explicit GenerationError(const std::string &code) : std::runtime_error(code) {}
};
}  // namespace

// Feedback 必须在完整 UTF-8 字符处切分，不能发布半个 token 字节串。
size_t complete_utf8_prefix(const std::string &text) {
    size_t offset = 0;
    while (offset < text.size()) {
        const auto lead    = static_cast<unsigned char>(text[offset]);
        const size_t width = lead < 0x80 ? 1 : lead >= 0xC2 && lead <= 0xDF ? 2 : lead >= 0xE0 && lead <= 0xEF ? 3 : lead >= 0xF0 && lead <= 0xF4 ? 4 : 0;
        if (!width) throw GenerationError("invalid_utf8");
        if (offset + width > text.size()) break;
        for (size_t i = 1; i < width; ++i) {
            const auto next = static_cast<unsigned char>(text[offset + i]);
            if (next < 0x80 || next > 0xBF) throw GenerationError("invalid_utf8");
        }
        if (width >= 3) {
            const auto second = static_cast<unsigned char>(text[offset + 1]);
            if ((lead == 0xE0 && second < 0xA0) || (lead == 0xED && second >= 0xA0) || (lead == 0xF0 && second < 0x90) || (lead == 0xF4 && second >= 0x90))
                throw GenerationError("invalid_utf8");
        }
        offset += width;
    }
    return offset;
}

class LlmNode : public rclcpp::Node {
public:
    // 常驻模型归本进程；构造失败时不得发布就绪状态。
    LlmNode() : Node("local_llm") {
        status_ = create_publisher<std_msgs::msg::String>("/inference/llm/status", rclcpp::QoS(1).transient_local().reliable());
        state("loading");
        const auto path        = declare_parameter<std::string>("model_path", "");
        const auto context     = declare_parameter<int>("context_tokens", 4096);
        const auto micro_batch = declare_parameter<int>("micro_batch_tokens", context < 512 ? context : 512);
        const auto threads     = declare_parameter<int>("threads", 2);
        const auto cache_type  = declare_parameter<std::string>("cache_type", "f16");
        if (cache_type != "f16" && cache_type != "q8_0") {
            state("failed");
            throw std::runtime_error("invalid_cache_type");
        }
        if (path.empty() || context < 128 || micro_batch < 1 || micro_batch > context || threads < 1) {
            state("failed");
            throw std::runtime_error("invalid_model_configuration");
        }
        ggml_backend_load_all();
        auto model_params         = llama_model_default_params();
        model_params.n_gpu_layers = 0;
        model_.reset(llama_model_load_from_file(path.c_str(), model_params));
        if (!model_) {
            state("failed");
            throw std::runtime_error("model_load_failed");
        }
        auto params    = llama_context_default_params();
        params.n_ctx   = context;
        params.n_batch = context;
        // 微批次约束计算图内存；完整 prompt 和输出预算仍按上下文验证。
        params.n_ubatch        = micro_batch;
        params.n_threads       = threads;
        params.n_threads_batch = threads;
        // 量化 KV 是显式资源选项，不改变权重或静默缩减 prompt。
        params.type_k = params.type_v = cache_type == "q8_0" ? GGML_TYPE_Q8_0 : GGML_TYPE_F16;
        params.abort_callback         = &LlmNode::abort_decode;
        params.abort_callback_data    = this;
        context_.reset(llama_init_from_model(model_.get(), params));
        if (!context_) {
            state("failed");
            throw std::runtime_error("context_create_failed");
        }
        // 完整响应缓存保留五秒，不沿用 ROS 默认十五分钟。
        auto options                       = rcl_action_server_get_default_options();
        options.result_timeout.nanoseconds = 5000000000LL;
        // 默认深度10在快速生成时已观察到丢前缀，双方明确使用256。
        options.feedback_topic_qos.depth = 256;
        server_                          = rclcpp_action::create_server<Generate>(
            this,
            "/inference/llm/generate",
            [this](const rclcpp_action::GoalUUID &, std::shared_ptr<const Generate::Goal> goal) {
                const bool valid = !goal->request_id.empty() && !goal->prompt.empty() && goal->prompt.size() <= 256 * 1024 &&
                                   std::isfinite(goal->budget_seconds) && goal->budget_seconds > 0 && goal->budget_seconds <= 600 && goal->max_tokens > 0 &&
                                   goal->max_tokens <= 4096;
                bool expected = false;
                if (!valid || !busy_.compare_exchange_strong(expected, true)) {
                    return rclcpp_action::GoalResponse::REJECT;
                }
                return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
            },
            [this](std::shared_ptr<GoalHandle>) {
                cancelled_.store(true);
                return rclcpp_action::CancelResponse::ACCEPT;
            },
            [this](std::shared_ptr<GoalHandle> goal) {
                if (worker_.joinable()) {
                    worker_.join();
                }
                cancelled_.store(false);
                worker_ = std::thread([this, goal]() { generate(goal); });
            },
            options);
        state("ready");
    }

    // 必须先等原生调用退役，之后才能销毁 context 和模型。
    ~LlmNode() override {
        stopping_.store(true);
        if (worker_.joinable()) {
            worker_.join();
        }
    }

private:
    // CPU decode 的取消回调只读原子信号和该 worker 设置的期限。
    static bool abort_decode(void *data) {
        auto *self = static_cast<LlmNode *>(data);
        return self->stopping_.load() || self->cancelled_.load() || Clock::now() >= self->deadline_;
    }

    // ROS 状态表示模型生命周期，不以 node 存在代替推理可用。
    void state(const std::string &value) {
        std_msgs::msg::String message;
        message.data = value;
        status_->publish(message);
    }

    // 单 worker 重建每轮上下文，完整输出才成功；截断不成为有效调用。
    void generate(const std::shared_ptr<GoalHandle> &handle) {
        const auto goal = handle->get_goal();
        auto result     = std::make_shared<Generate::Result>();
        deadline_       = Clock::now() + std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(goal->budget_seconds));
        state("busy");
        try {
            // 1. 明确验证整个 prompt 的 token 预算，不裁掉工具和用户意图。
            llama_memory_clear(llama_get_memory(context_.get()), true);
            const auto *vocab = llama_model_get_vocab(model_.get());
            const int count   = -llama_tokenize(vocab, goal->prompt.data(), goal->prompt.size(), nullptr, 0, true, true);
            if (count <= 0 || count + goal->max_tokens > llama_n_ctx(context_.get())) {
                throw GenerationError("context_budget");
            }
            std::vector<llama_token> tokens(count);
            llama_tokenize(vocab, goal->prompt.data(), goal->prompt.size(), tokens.data(), count, true, true);
            std::unique_ptr<llama_sampler, decltype(&llama_sampler_free)> sampler(llama_sampler_chain_init(llama_sampler_chain_default_params()),
                                                                                  llama_sampler_free);
            auto *grammar = llama_sampler_init_grammar(vocab, OUTPUT_GRAMMAR, "root");
            if (!grammar) throw GenerationError("grammar_unavailable");
            llama_sampler_chain_add(sampler.get(), grammar);
            llama_sampler_chain_add(sampler.get(), llama_sampler_init_greedy());
            std::string pending_utf8;
            uint32_t sequence = 0;
            auto batch        = llama_batch_get_one(tokens.data(), tokens.size());
            llama_token token;
            bool complete = false;
            // 2. grammar 先于终端采样生效；Feedback 传原始 JSON 增量，Python 决定可播内容。
            for (uint32_t generated = 0; generated < goal->max_tokens; ++generated) {
                if (abort_decode(this)) {
                    throw GenerationError(cancelled_.load() ? "cancelled" : "timeout");
                }
                const int decoded = llama_decode(context_.get(), batch);
                if (decoded != 0) {
                    throw GenerationError(decoded == 2 ? (cancelled_.load() ? "cancelled" : "timeout") : "decode_failed");
                }
                token = llama_sampler_sample(sampler.get(), context_.get(), -1);
                if (llama_vocab_is_eog(vocab, token)) {
                    complete = true;
                    break;
                }
                std::vector<char> piece(256);
                int length = llama_token_to_piece(vocab, token, piece.data(), piece.size(), 0, false);
                if (length < 0) {
                    piece.resize(-length);
                    length = llama_token_to_piece(vocab, token, piece.data(), piece.size(), 0, false);
                }
                result->output.append(piece.data(), length);
                if (result->output.size() > 256 * 1024) {
                    throw GenerationError("output_budget");
                }
                pending_utf8.append(piece.data(), length);
                const auto prefix = complete_utf8_prefix(pending_utf8);
                if (prefix) {
                    auto feedback             = std::make_shared<Generate::Feedback>();
                    feedback->request_id      = goal->request_id;
                    feedback->sequence        = ++sequence;
                    feedback->output_contract = "fc-first-v1";
                    feedback->text_delta      = pending_utf8.substr(0, prefix);
                    handle->publish_feedback(feedback);
                    pending_utf8.erase(0, prefix);
                }
                batch = llama_batch_get_one(&token, 1);
            }
            if (!pending_utf8.empty()) throw GenerationError("invalid_utf8");
            if (!complete) {
                throw GenerationError("output_truncated");
            }
            if (abort_decode(this)) {
                throw GenerationError(cancelled_.load() ? "cancelled" : "timeout");
            }
            result->final_sequence = sequence;
            result->success        = true;
        } catch (const GenerationError &error) {
            result->success    = false;
            result->error_code = error.what();
            result->output.clear();
        }
        // 3. 取消终态只在 native 已退出后发布；失败输出不允许进入执行。
        if (!rclcpp::ok()) {
            // context 关闭后不再向失效 ROS publisher 写终态。
            busy_.store(false);
            return;
        }
        if (handle->is_canceling()) {
            result->success = false;
            result->output.clear();
            handle->canceled(result);
        } else if (result->success) {
            handle->succeed(result);
        } else {
            handle->abort(result);
        }
        busy_.store(false);
        state(stopping_.load() ? "closing" : "ready");
    }

    std::unique_ptr<llama_model, decltype(&llama_model_free)> model_{nullptr, llama_model_free};
    std::unique_ptr<llama_context, decltype(&llama_free)> context_{nullptr, llama_free};
    rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_;
    rclcpp_action::Server<Generate>::SharedPtr server_;
    std::atomic<bool> busy_{false};
    std::atomic<bool> cancelled_{false};
    std::atomic<bool> stopping_{false};
    Clock::time_point deadline_;
    std::thread worker_;
};

// 启动加载失败直接退出非零，由所属 Launch 统一收尾。
int main(int argc, char **argv) {
    rclcpp::init(argc, argv);
    int status = 0;
    try {
        rclcpp::spin(std::make_shared<LlmNode>());
    } catch (const std::exception &error) {
        RCLCPP_ERROR(rclcpp::get_logger("local_llm"), "%s", error.what());
        status = 1;
    }
    rclcpp::shutdown();
    return status;
}
