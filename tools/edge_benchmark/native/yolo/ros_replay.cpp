#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <robot_interfaces/msg/dets.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <set>
#include <thread>

#include "rknn_yolov6/rknn_yolov6_node.hpp"

using Clock = std::chrono::steady_clock;

// 将单调时钟转换为跨进程可比较的秒数。
double monotonic(Clock::time_point value) { return std::chrono::duration<double>(value.time_since_epoch()).count(); }

// 对真实 ROS 节点回放 RGB 图像，测量传输、队列、推理、绘图和检测发布。
int main(int argc, char **argv) {
    if (argc != 13) return 2;
    const int width  = std::stoi(argv[5]);
    const int height = std::stoi(argv[6]);
    const int frames = std::stoi(argv[7]);
    const double fps = std::stod(argv[8]);
    if (width <= 0 || height <= 0 || frames <= 0 || fps <= 0) return 2;
    cv::setNumThreads(std::stoi(argv[11]));
    rclcpp::init(0, nullptr);
    std::ofstream events(std::string(argv[4]) + "/events.jsonl");
    events << std::setprecision(16);

    // 1. 使用隔离域与独立话题，仅构造检测节点，不启动其他机器人节点。
    rclcpp::NodeOptions options;
    options.parameter_overrides({{"model_path", argv[1]},
                                 {"labels_path", argv[2]},
                                 {"confidence_threshold", std::stod(argv[9])},
                                 {"nms_threshold", std::stod(argv[10])},
                                 {"always_process", true},
                                 {"input_topic", "/benchmark/image"},
                                 {"detections_topic", "/benchmark/detections"},
                                 {"annotated_topic", "/benchmark/annotated"}});
    const auto loading = Clock::now();
    auto detector      = std::make_shared<rknn_yolov6::RknnYolov6Node>(options);
    auto replay        = std::make_shared<rclcpp::Node>("vision_replay");
    auto qos           = rclcpp::QoS(1).best_effort();
    auto publisher     = replay->create_publisher<sensor_msgs::msg::Image>("/benchmark/image", qos);
    Clock::time_point started;
    Clock::time_point last_completed;
    std::set<int> received;
    bool warmed = false;
    auto subscription =
        replay->create_subscription<robot_interfaces::msg::Dets>("/benchmark/detections", qos, [&](robot_interfaces::msg::Dets::ConstSharedPtr message) {
            const int frame = std::stoi(message->header.frame_id);
            if (frame < 0) {
                warmed = true;
                return;
            }
            if (!received.insert(frame).second) return;
            last_completed       = Clock::now();
            const double latency = monotonic(last_completed) - monotonic(started) - frame / fps;
            events << "{\"event\":\"frame\",\"scope\":\"ros\",\"frame\":" << frame << ",\"seconds\":" << latency << ",\"latency_seconds\":" << latency
                   << ",\"end_monotonic\":" << monotonic(last_completed) << ",\"detection_count\":" << message->detections.size() << "}\n"
                   << std::flush;
        });
    const bool annotated = std::getenv("YOLO_BENCH_ANNOTATED") != nullptr;
    rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr annotation;
    int annotated_received = 0;
    if (annotated) {
        annotation = replay->create_subscription<sensor_msgs::msg::Image>(
            "/benchmark/annotated", qos, [&](sensor_msgs::msg::Image::ConstSharedPtr) { ++annotated_received; });
    }
    rclcpp::executors::SingleThreadedExecutor executor;
    executor.add_node(detector);
    executor.add_node(replay);
    cv::Mat image = cv::imread(argv[3]);
    if (image.empty()) throw std::runtime_error("unreadable benchmark image");
    cv::resize(image, image, cv::Size(width, height));
    cv::cvtColor(image, image, cv::COLOR_BGR2RGB);
    sensor_msgs::msg::Image message;
    message.width    = width;
    message.height   = height;
    message.encoding = "rgb8";
    message.step     = width * 3;
    message.data.assign(image.data, image.data + image.total() * image.elemSize());

    // 2. 等待 DDS 发现并预热；门禁后使用实际双阶段队列。
    while (publisher->get_subscription_count() == 0) {
        executor.spin_some();
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    for (int i = 0; i < 3; ++i) {
        warmed                  = false;
        message.header.frame_id = "-1";
        publisher->publish(message);
        while (!warmed) {
            executor.spin_some();
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }
    events << "{\"event\":\"loaded\",\"load_seconds\":" << monotonic(Clock::now()) - monotonic(loading) << "}\n" << std::flush;
    std::ofstream(std::string(argv[4]) + "/ready").put('1');
    if (std::string(argv[12]) != "-") {
        while (!std::ifstream(argv[12]).good()) {
            executor.spin_some();
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
    }

    // 3. 按固定节奏发布；保留源端错过的帧，排空窗口限制为两秒。
    started   = Clock::now();
    int sent  = 0;
    int index = 0;
    while (index < frames) {
        executor.spin_some();
        const int due = static_cast<int>((monotonic(Clock::now()) - monotonic(started)) * fps);
        if (due >= frames) break;
        if (due >= index) {
            index                   = due;
            message.header.frame_id = std::to_string(index);
            message.header.stamp    = replay->now();
            publisher->publish(message);
            ++sent;
            ++index;
        } else {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }
    const auto end = started + std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(frames / fps + 2));
    while (Clock::now() < end) {
        executor.spin_some();
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    if (received.empty()) throw std::runtime_error("no measured detections received");
    const double wall = std::max(frames / fps, monotonic(last_completed) - monotonic(started));
    events << "{\"event\":\"sample\",\"scope\":\"ros\",\"index\":0,\"seconds\":" << wall << ",\"processed\":" << received.size()
           << ",\"dropped\":" << frames - received.size() << ",\"offered_frames\":" << frames << ",\"sent_frames\":" << sent
           << ",\"source_skipped\":" << frames - sent << ",\"fps\":" << received.size() / wall << ",\"offered_fps\":" << fps
           << ",\"annotated_subscriber\":" << (annotated ? "true" : "false") << ",\"annotated_received_including_warmup\":" << annotated_received << "}\n"
           << std::flush;
    executor.remove_node(detector);
    executor.remove_node(replay);
    detector.reset();
    rclcpp::shutdown();
}
