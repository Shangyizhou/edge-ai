#include "rknn_yolov6/postprocess.hpp"

// 为 ONNX Runtime 提供与现用 RKNN 相同的 YOLOv6 后处理。
extern "C" int yolo_decode(const float *head0, const float *head1, const float *head2, int width, int height, float confidence, float nms, float *rows) {
    rknn_yolov6::YoloV6PostprocessorConfig config;
    config.model_width          = 640;
    config.model_height         = 352;
    config.confidence_threshold = confidence;
    config.nms_threshold        = nms;
    for (int i = 0; i < 80; ++i)
        config.labels.push_back(std::to_string(i));
    rknn_yolov6::YoloV6Postprocessor postprocessor(config);
    auto detections = postprocessor.process({{head0, head1, head2}, width, height});
    for (std::size_t i = 0; i < detections.size(); ++i) {
        const auto &d   = detections[i];
        rows[6 * i]     = d.cls_id;
        rows[6 * i + 1] = d.conf;
        rows[6 * i + 2] = d.x1;
        rows[6 * i + 3] = d.y1;
        rows[6 * i + 4] = d.x2;
        rows[6 * i + 5] = d.y2;
    }
    return static_cast<int>(detections.size());
}
