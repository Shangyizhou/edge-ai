set(SHERPA_ONNX_ROOT "" CACHE PATH "External Sherpa ONNX package prefix")
# ASR 可独立选择 RKNN SDK；不改变 TTS 的 Sherpa 依赖。
set(ASR_SHERPA_ONNX_ROOT "${SHERPA_ONNX_ROOT}" CACHE PATH "ASR-only matching Sherpa prefix")
set(ASR_RKNN_RUNTIME_DIR "" CACHE PATH "Private ASR RKNN runtime directory")
find_path(ASR_SHERPA_INCLUDE sherpa-onnx/c-api/c-api.h HINTS "${ASR_SHERPA_ONNX_ROOT}/include" REQUIRED)
find_library(ASR_SHERPA_LIBRARY sherpa-onnx-c-api HINTS "${ASR_SHERPA_ONNX_ROOT}/lib" REQUIRED)
find_package(Threads REQUIRED)
add_executable(asr_node src/asr_node.cpp)
target_include_directories(asr_node PRIVATE "${ASR_SHERPA_INCLUDE}")
target_link_libraries(asr_node "${ASR_SHERPA_LIBRARY}" Threads::Threads)
target_compile_features(asr_node PRIVATE cxx_std_17)
ament_target_dependencies(asr_node rclcpp robot_interfaces std_msgs)
set(ASR_RUNTIME_PATH "${ASR_SHERPA_ONNX_ROOT}/lib")
if(ASR_RKNN_RUNTIME_DIR)
  find_library(ASR_RKNN_LIBRARY rknnrt PATHS "${ASR_RKNN_RUNTIME_DIR}" NO_DEFAULT_PATH REQUIRED)
  # 直接加载私有 runtime，避免 Sherpa 自带 RUNPATH 回落到系统旧库。
  target_link_libraries(asr_node "-Wl,--no-as-needed" "${ASR_RKNN_LIBRARY}" "-Wl,--as-needed")
  list(APPEND ASR_RUNTIME_PATH "${ASR_RKNN_RUNTIME_DIR}")
endif()
set_target_properties(asr_node PROPERTIES
  BUILD_RPATH "${ASR_RUNTIME_PATH}"
  INSTALL_RPATH "${ASR_RUNTIME_PATH}")
install(TARGETS asr_node DESTINATION lib/${PROJECT_NAME})
