#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>

#include "rknn_api.h"

// 独立执行一个原有RKNN组件，区分模型算子故障与整个NPU不可用。
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    std::ifstream file(argv[1], std::ios::binary);
    std::vector<char> model((std::istreambuf_iterator<char>(file)), {});
    rknn_context context = 0;
    int result           = rknn_init(&context, model.data(), model.size(), RKNN_FLAG_COLLECT_PERF_MASK, nullptr);
    std::cout << "init=" << result << std::endl;
    if (result != 0) return 3;

    // 1. 从模型查询实际输入，不硬编码ASR与诊断模型的维度。
    rknn_sdk_version version{};
    rknn_query(context, RKNN_QUERY_SDK_VERSION, &version, sizeof(version));
    std::cout << "api=" << version.api_version << " driver=" << version.drv_version << std::endl;
    rknn_input_output_num count{};
    result = rknn_query(context, RKNN_QUERY_IN_OUT_NUM, &count, sizeof(count));
    if (result != 0) return 4;
    std::vector<std::vector<unsigned char>> buffers(count.n_input);
    std::vector<rknn_input> inputs(count.n_input);
    for (uint32_t i = 0; i < count.n_input; ++i) {
        rknn_tensor_attr attr{};
        attr.index = i;
        result     = rknn_query(context, RKNN_QUERY_INPUT_ATTR, &attr, sizeof(attr));
        if (result != 0) return 5;
        buffers[i].resize(attr.size);
        inputs[i].index = i;
        inputs[i].buf   = buffers[i].data();
        inputs[i].size  = attr.size;
        inputs[i].type  = attr.type;
        inputs[i].fmt   = attr.fmt;
        std::cout << "input=" << i << " bytes=" << attr.size << " type=" << attr.type << " qnt_type=" << attr.qnt_type << " scale=" << attr.scale
                  << " zp=" << attr.zp << std::endl;
    }

    // 2. 零输入只验证推理执行，不评价ASR正确率或其他模型质量。
    result = rknn_inputs_set(context, count.n_input, inputs.data());
    std::cout << "inputs_set=" << result << std::endl;
    if (result != 0) return 6;
    result = rknn_run(context, nullptr);
    std::cout << "run=" << result << std::endl;
    if (result != 0) return 7;
    std::vector<rknn_output> outputs(count.n_output);
    for (uint32_t i = 0; i < count.n_output; ++i) {
        outputs[i].index      = i;
        outputs[i].want_float = 1;
    }
    result = rknn_outputs_get(context, count.n_output, outputs.data(), nullptr);
    std::cout << "outputs_get=" << result << std::endl;
    if (result == 0) rknn_outputs_release(context, count.n_output, outputs.data());
    // 调试报告只记录算子执行信息，不将零输入当作识别质量或性能benchmark。
    rknn_perf_detail perf{};
    int perf_status = rknn_query(context, RKNN_QUERY_PERF_DETAIL, &perf, sizeof(perf));
    std::cout << "perf_query=" << perf_status << std::endl;
    if (perf_status == 0 && perf.perf_data) std::cout << perf.perf_data << std::endl;
    rknn_destroy(context);
    return result == 0 ? 0 : 8;
}
