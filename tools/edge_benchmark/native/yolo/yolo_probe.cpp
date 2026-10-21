#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <rclcpp/rclcpp.hpp>
#include <thread>

#include "rknn_yolov6/detector_backend.hpp"

using Clock = std::chrono::steady_clock;

// 计算两个单调时钟点之间的秒数。
double seconds(Clock::time_point start, Clock::time_point end) { return std::chrono::duration<double>(end - start).count(); }

// 复用真实 ROS 检测后端，以离线 RGB 图像测试连续吞吐或最新帧调度。
int main(int argc, char **argv) {
    if (argc != 13) {
        std::cerr << "model labels image output width height frames fps confidence nms threads gate\n";
        return 2;
    }
    cv::setNumThreads(std::stoi(argv[11]));
    const int width          = std::stoi(argv[5]);
    const int height         = std::stoi(argv[6]);
    const int offered_frames = std::stoi(argv[7]);
    const double fps         = std::stod(argv[8]);
    if (width <= 0 || height <= 0 || offered_frames <= 0 || fps < 0) {
        return 2;
    }

    // 1. 在测量前解码固定图片，转换为相机后端要求的 RGB。
    cv::Mat image = cv::imread(argv[3]);
    if (image.empty()) {
        throw std::runtime_error("unreadable benchmark image");
    }
    cv::resize(image, image, cv::Size(width, height));
    cv::cvtColor(image, image, cv::COLOR_BGR2RGB);
    std::ofstream events(std::string(argv[4]) + "/events.jsonl");
    events << std::setprecision(16);
    rknn_yolov6::detail::DetectorBackendConfig config;
    config.model_path           = argv[1];
    config.labels_path          = argv[2];
    config.confidence_threshold = std::stof(argv[9]);
    config.nms_threshold        = std::stof(argv[10]);
    const auto load_start       = Clock::now();
    auto backend                = rknn_yolov6::detail::create_detector_backend(config, rclcpp::get_logger("yolo_benchmark"), std::make_shared<rclcpp::Clock>());
    events << "{\"event\":\"loaded\",\"load_seconds\":" << seconds(load_start, Clock::now()) << "}\n" << std::flush;

    // 2. 预热三帧后等待共存门禁；加载和预热不计入逐帧吞吐。
    for (int i = 0; i < 3; ++i) {
        auto result = backend->infer(image);
        if (!result) {
            throw std::runtime_error("YOLO warmup inference failed");
        }
        backend->detections(*result);
    }
    std::ofstream(std::string(argv[4]) + "/ready").put('1');
    if (std::string(argv[12]) != "-") {
        while (!std::ifstream(argv[12]).good()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
    }

    // 3. 按最新帧策略跳过已过时输入，不积累无限队列；保留每次完整检测结果。
    const auto start = Clock::now();
    int frame        = 0;
    int processed    = 0;
    int dropped      = 0;
    while (frame < offered_frames) {
        if (fps > 0) {
            const auto due = start + std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(frame / fps));
            std::this_thread::sleep_until(due);
            const int latest = static_cast<int>(seconds(start, Clock::now()) * fps);
            if (latest >= offered_frames) {
                dropped += offered_frames - frame;
                break;
            }
            dropped += latest - frame;
            frame = latest;
        }
        const auto begin    = Clock::now();
        auto result         = backend->infer(image);
        const auto inferred = Clock::now();
        if (!result) {
            throw std::runtime_error("YOLO inference failed");
        }
        auto detections = backend->detections(*result);
        result.reset();
        const auto finished = Clock::now();
        events << "{\"event\":\"frame\",\"frame\":" << frame << ",\"start_monotonic\":" << seconds(Clock::time_point{}, begin)
               << ",\"end_monotonic\":" << seconds(Clock::time_point{}, finished) << ",\"infer_seconds\":" << seconds(begin, inferred)
               << ",\"post_seconds\":" << seconds(inferred, finished) << ",\"seconds\":" << seconds(begin, finished)
               << ",\"latency_seconds\":" << (fps > 0 ? seconds(start, finished) - frame / fps : seconds(begin, finished)) << ",\"detections\":[";
        for (std::size_t i = 0; i < detections.size(); ++i) {
            const auto &d = detections[i];
            if (i) events << ',';
            events << "{\"class\":" << d.cls_id << ",\"confidence\":" << d.conf << ",\"box\":[" << d.x1 << ',' << d.y1 << ',' << d.x2 << ',' << d.y2 << "]}";
        }
        events << "]}\n" << std::flush;
        ++processed;
        ++frame;
    }
    if (fps > 0) {
        std::this_thread::sleep_until(start + std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(offered_frames / fps)));
    }
    const double wall = seconds(start, Clock::now());
    events << "{\"event\":\"sample\",\"index\":0,\"input\":\"fixed image replay\",\"seconds\":" << wall << ",\"processed\":" << processed
           << ",\"dropped\":" << dropped << ",\"offered_frames\":" << offered_frames << ",\"fps\":" << processed / wall << ",\"offered_fps\":" << fps << "}\n";
}
