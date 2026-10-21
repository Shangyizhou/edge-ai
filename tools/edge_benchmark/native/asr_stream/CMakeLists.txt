cmake_minimum_required(VERSION 3.16)
project(edge_asr_stream LANGUAGES CXX)
set(SHERPA_ROOT "" CACHE PATH "External RKNN sherpa-onnx distribution")
set(SHERPA_INCLUDE_DIR "" CACHE PATH "External matching public C API headers")
set(RKNN_RUNTIME_DIR "" CACHE PATH "Private validated RKNN runtime")
add_executable(asr_stream_probe asr_stream_probe.cpp)
target_compile_features(asr_stream_probe PRIVATE cxx_std_17)
target_include_directories(asr_stream_probe PRIVATE ${SHERPA_INCLUDE_DIR})
target_link_libraries(asr_stream_probe PRIVATE
  ${SHERPA_ROOT}/lib/libsherpa-onnx-c-api.so
  ${RKNN_RUNTIME_DIR}/librknnrt.so)
