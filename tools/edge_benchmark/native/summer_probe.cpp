#include <omp.h>

#include <Eigen/Core>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "SynthesizerTrn.h"
#include "utils.h"

using Clock = std::chrono::steady_clock;

// 返回单调时钟经过秒数，用于区分加载与合成时间。
double elapsed(Clock::time_point start) { return std::chrono::duration<double>(Clock::now() - start).count(); }

// 常驻一次旧 Summer 模型，逐行合成到裸 PCM，不访问声卡。
int main(int argc, char **argv) {
    if (argc != 6 && argc != 7) {
        std::cerr << "summer_probe MODEL THREADS TEXT_FILE OUTPUT_DIR SCALE\n";
        return 2;
    }
    const int threads = std::stoi(argv[2]);
    omp_set_dynamic(0);
    omp_set_num_threads(threads);
    Eigen::setNbThreads(threads);
    std::ifstream texts(argv[3]);
    std::ofstream metrics(std::string(argv[4]) + "/events.jsonl");
    metrics << std::setprecision(17);
    if (!texts || !metrics) {
        throw std::runtime_error("cannot open benchmark input/output");
    }

    // 1. 加载保持旧权重和前端的实现，单独记初始化时间。
    auto start     = Clock::now();
    float *data    = nullptr;
    const int size = ttsLoadModel(argv[1], &data);
    if (size <= 0 || data == nullptr) {
        throw std::runtime_error("Summer model loading failed");
    }
    std::unique_ptr<float, decltype(&tts_free_data)> weights(data, &tts_free_data);
    SynthesizerTrn model(data, size);
    metrics << "{\"event\":\"loaded\",\"load_seconds\":" << elapsed(start) << ",\"threads\":" << Eigen::nbThreads() << "}" << std::endl;
    if (argc == 7) {
        while (!std::filesystem::exists(argv[6])) {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
    }

    // 2. 每行是独立请求，音频写盘时间不计入纯合成耗时。
    std::string line;
    int index = 0;
    while (std::getline(texts, line)) {
        start           = Clock::now();
        int32_t samples = 0;
        std::unique_ptr<int16_t, decltype(&tts_free_data)> pcm(model.infer(line, 0, std::stof(argv[5]), samples), &tts_free_data);
        const double seconds = elapsed(start);
        if (!pcm || samples <= 0) {
            throw std::runtime_error("Summer produced no PCM");
        }
        std::ofstream audio(std::string(argv[4]) + "/" + std::to_string(index) + ".pcm", std::ios::binary);
        audio.write(reinterpret_cast<char *>(pcm.get()), samples * sizeof(int16_t));
        if (!audio) {
            throw std::runtime_error("cannot write Summer PCM");
        }
        metrics << "{\"event\":\"sample\",\"index\":" << index << ",\"seconds\":" << seconds << ",\"samples\":" << samples
                << ",\"sample_rate\":16000,\"rtf\":" << seconds / (samples / 16000.0)
                << ",\"started_monotonic_seconds\":" << std::chrono::duration<double>(start.time_since_epoch()).count() << "}" << std::endl;
        ++index;
    }
    return 0;
}
