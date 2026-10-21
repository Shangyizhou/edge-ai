cmake_minimum_required(VERSION 3.16)
project(edge_summer_benchmark LANGUAGES CXX)

set(SUMMER_SOURCE_DIR "" CACHE PATH "External legacy SummerTTS source")
if(NOT EXISTS "${SUMMER_SOURCE_DIR}/include/SynthesizerTrn.h")
  message(FATAL_ERROR "Set SUMMER_SOURCE_DIR to the legacy robot TTS source")
endif()
find_package(OpenMP REQUIRED)
# 沿用旧目标已验证的推理/前端清单，排除 vendored 单元测试与 ROS server。
file(READ "${SUMMER_SOURCE_DIR}/CMakeLists.txt" LEGACY_CMAKE)
string(REGEX MATCHALL "\\./src/[^ \n\r\)]+\\.(cc|cpp)" SUMMER_PATHS "${LEGACY_CMAKE}")
set(SUMMER_SOURCES)
foreach(SUMMER_PATH IN LISTS SUMMER_PATHS)
  list(APPEND SUMMER_SOURCES "${SUMMER_SOURCE_DIR}/${SUMMER_PATH}")
endforeach()
add_executable(summer_probe summer_probe.cpp ${SUMMER_SOURCES})
target_compile_features(summer_probe PRIVATE cxx_std_17)
target_include_directories(summer_probe PRIVATE
  "${SUMMER_SOURCE_DIR}/eigen-3.4.0"
  "${SUMMER_SOURCE_DIR}/src/tn/header"
  "${SUMMER_SOURCE_DIR}/include"
  "${SUMMER_SOURCE_DIR}/src/header")
target_link_libraries(summer_probe PRIVATE OpenMP::OpenMP_CXX)
