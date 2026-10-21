#include <algorithm>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "sherpa-onnx/c-api/c-api.h"

using Clock = std::chrono::steady_clock;

// 以同一主机单调时钟记录跨进程重叠区间。
double now() { return std::chrono::duration<double>(Clock::now().time_since_epoch()).count(); }

// 转义模型文本与路径，保证每个事件是一行完整 JSON。
std::string quote(const std::string &value) {
    std::ostringstream out;
    out << '"';
    for (unsigned char c : value) {
        if (c == '"' || c == '\\')
            out << '\\' << c;
        else if (c < 32)
            out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(c) << std::dec;
        else
            out << c;
    }
    out << '"';
    return out.str();
}

// 读取当前可见文本，结果对象的生命周期不跨越下一次解码。
std::string text(const SherpaOnnxOnlineRecognizer *recognizer, const SherpaOnnxOnlineStream *stream) {
    const auto *result = SherpaOnnxGetOnlineStreamResult(recognizer, stream);
    if (!result) throw std::runtime_error("missing online result");
    std::string value = result->text;
    SherpaOnnxDestroyOnlineRecognizerResult(result);
    return value;
}

// 解码所有已就绪块，返回实际模型调用次数。
int decode(const SherpaOnnxOnlineRecognizer *recognizer, const SherpaOnnxOnlineStream *stream) {
    int count = 0;
    while (SherpaOnnxIsOnlineStreamReady(recognizer, stream)) {
        SherpaOnnxDecodeOnlineStream(recognizer, stream);
        ++count;
    }
    return count;
}

// 在一个常驻模型上回放多段音频，端点重置不销毁模型。
int main(int argc, char **argv) {
    if (argc != 10) {
        std::cerr << "model output fixtures.tsv endpoint chunk_ms realtime tail_seconds gate provider\n";
        return 2;
    }
    const std::string model    = argv[1];
    const std::string output   = argv[2];
    const float endpoint       = std::stof(argv[4]);
    const int chunk            = std::stoi(argv[5]) * 16;
    const bool realtime        = std::stoi(argv[6]) != 0;
    const double tail          = std::stod(argv[7]);
    const std::string provider = argv[9];
    if (chunk <= 0 || tail < 0 || endpoint <= 0) return 2;
    std::ofstream events(output + "/events.jsonl");
    events << std::setprecision(16);
    const std::string encoder = model + (provider == "rknn" ? "/encoder.rknn" : "/encoder-epoch-99-avg-1.int8.onnx");
    const std::string decoder = model + (provider == "rknn" ? "/decoder.rknn" : "/decoder-epoch-99-avg-1.onnx");
    const std::string joiner  = model + (provider == "rknn" ? "/joiner.rknn" : "/joiner-epoch-99-avg-1.int8.onnx");
    const std::string tokens  = model + "/tokens.txt";

    // 1. 仅创建一次模型，先用独立静音流预热，再等待共跑门禁。
    SherpaOnnxOnlineRecognizerConfig config{};
    config.feat_config.sample_rate         = 16000;
    config.feat_config.feature_dim         = 80;
    config.model_config.transducer.encoder = encoder.c_str();
    config.model_config.transducer.decoder = decoder.c_str();
    config.model_config.transducer.joiner  = joiner.c_str();
    config.model_config.tokens             = tokens.c_str();
    config.model_config.num_threads        = provider == "rknn" ? 1 : 2;
    config.model_config.provider           = provider.c_str();
    config.decoding_method                 = "greedy_search";
    config.max_active_paths                = 4;
    config.enable_endpoint                 = 1;
    config.rule1_min_trailing_silence      = 2.4;
    config.rule2_min_trailing_silence      = endpoint;
    config.rule3_min_utterance_length      = 20;
    const double loading                   = now();
    const auto *recognizer                 = SherpaOnnxCreateOnlineRecognizer(&config);
    if (!recognizer) throw std::runtime_error("online recognizer creation failed");
    const double loaded = now();
    const auto *warm    = SherpaOnnxCreateOnlineStream(recognizer);
    std::vector<float> zeros(32000, 0);
    SherpaOnnxOnlineStreamAcceptWaveform(warm, 16000, zeros.data(), zeros.size());
    SherpaOnnxOnlineStreamInputFinished(warm);
    decode(recognizer, warm);
    SherpaOnnxDestroyOnlineStream(warm);
    events << "{\"event\":\"loaded\",\"load_seconds\":" << loaded - loading << ",\"warmup_seconds\":" << now() - loaded << ",\"model_creations\":1}\n"
           << std::flush;
    std::ofstream(output + "/ready").put('1');
    if (std::string(argv[8]) != "-") {
        while (!std::ifstream(argv[8]).good())
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }

    // 2. 每个素材只创建轻量流状态；按音频块末端到达时间喂入 PCM。
    std::ifstream fixtures(argv[3]);
    std::string filename;
    double anchor;
    int index = 0;
    while (fixtures >> filename >> anchor) {
        const auto *wave = SherpaOnnxReadWave(filename.c_str());
        if (!wave || wave->sample_rate != 16000) throw std::runtime_error("expected readable 16kHz mono WAV");
        const double duration = wave->num_samples / 16000.0;
        std::vector<float> samples(wave->samples, wave->samples + wave->num_samples);
        SherpaOnnxFreeWave(wave);
        samples.resize(samples.size() + static_cast<std::size_t>(tail * 16000), 0);
        const auto *stream    = SherpaOnnxCreateOnlineStream(recognizer);
        const double started  = now();
        double compute        = 0;
        double first_partial  = -1;
        double last_partial   = -1;
        double final_endpoint = -1;
        int early             = 0;
        int endpoints         = 0;
        std::string finalized;
        std::string previous;
        for (std::size_t offset = 0; offset < samples.size(); offset += chunk) {
            const int count     = std::min<std::size_t>(chunk, samples.size() - offset);
            const double cursor = (offset + count) / 16000.0;
            if (realtime) {
                const auto due = Clock::time_point(std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(started + cursor)));
                std::this_thread::sleep_until(due);
            }
            const double begin = now();
            SherpaOnnxOnlineStreamAcceptWaveform(stream, 16000, samples.data() + offset, count);
            const int calls       = decode(recognizer, stream);
            const auto current    = text(recognizer, stream);
            const bool ended      = SherpaOnnxOnlineStreamIsEndpoint(recognizer, stream);
            const double finished = now();
            compute += finished - begin;
            events << "{\"event\":\"asr_block\",\"utterance\":" << index << ",\"audio_cursor\":" << cursor << ",\"processing_seconds\":" << finished - begin
                   << ",\"submit_lateness_seconds\":" << (realtime ? std::max(0.0, begin - started - cursor) : 0)
                   << ",\"completion_lag_seconds\":" << (realtime ? std::max(0.0, finished - started - cursor) : 0) << ",\"decode_calls\":" << calls
                   << ",\"end_monotonic\":" << finished << "}\n";
            if (!current.empty() && current != previous) {
                if (first_partial < 0) first_partial = finished - started;
                last_partial = finished - started;
                events << "{\"event\":\"partial\",\"utterance\":" << index << ",\"audio_cursor\":" << cursor << ",\"wall_seconds\":" << finished - started
                       << ",\"transcript\":" << quote(current) << "}\n";
                previous = current;
            }
            // 3. 端点只重置流；输入完成只在整段素材全部喂完后调用。
            if (ended) {
                if (!current.empty()) {
                    ++endpoints;
                    finalized += current;
                    if (cursor < anchor)
                        ++early;
                    else
                        final_endpoint = finished - started;
                    events << "{\"event\":\"endpoint\",\"utterance\":" << index << ",\"audio_cursor\":" << cursor << ",\"wall_seconds\":" << finished - started
                           << ",\"transcript\":" << quote(current) << "}\n";
                }
                SherpaOnnxOnlineStreamReset(recognizer, stream);
                previous.clear();
            }
            events << std::flush;
        }
        const double flush_start = now();
        SherpaOnnxOnlineStreamInputFinished(stream);
        decode(recognizer, stream);
        const auto residual = text(recognizer, stream);
        compute += now() - flush_start;
        finalized += residual;
        events << "{\"event\":\"sample\",\"index\":" << index << ",\"input\":" << quote(filename) << ",\"seconds\":" << compute
               << ",\"rtf\":" << compute / duration << ",\"audio_seconds\":" << duration << ",\"supplied_audio_seconds\":" << samples.size() / 16000.0
               << ",\"rtf_supplied\":" << compute / (samples.size() / 16000.0) << ",\"realtime\":" << (realtime ? "true" : "false")
               << ",\"first_partial_seconds\":" << first_partial << ",\"energy_end_seconds\":" << anchor << ",\"last_partial_seconds\":" << last_partial
               << ",\"endpoint_after_energy_seconds\":" << (final_endpoint < 0 || !realtime ? -1 : final_endpoint - anchor)
               << ",\"endpoint_count\":" << endpoints << ",\"early_endpoint_count\":" << early << ",\"eof_residual\":" << quote(residual)
               << ",\"transcript\":" << quote(finalized) << ",\"start_monotonic\":" << started << ",\"end_monotonic\":" << now() << "}\n"
               << std::flush;
        SherpaOnnxDestroyOnlineStream(stream);
        ++index;
    }
    SherpaOnnxDestroyOnlineRecognizer(recognizer);
    if (!index) throw std::runtime_error("no streaming fixtures supplied");
}
