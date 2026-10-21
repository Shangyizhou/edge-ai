cmake_minimum_required(VERSION 3.16)
project(edge_yolo_benchmark LANGUAGES CXX)
set(YOLO_SOURCE_DIR "" CACHE PATH "External ros-robot rknn_yolov6 package")
set(RKNN_API_INCLUDE_DIR "" CACHE PATH "External RKNN SDK headers")
find_package(rclcpp REQUIRED)
find_package(OpenCV REQUIRED COMPONENTS core imgproc imgcodecs)
find_library(RKNNRT_LIBRARY rknnrt REQUIRED)
find_library(RGA_LIBRARY rga REQUIRED)
find_path(RGA_INCLUDE_DIR im2d.hpp PATH_SUFFIXES rga REQUIRED)
add_executable(yolo_probe yolo_probe.cpp
  ${YOLO_SOURCE_DIR}/src/detector_backend_rknn.cpp
  ${YOLO_SOURCE_DIR}/src/postprocess.cpp)
target_compile_features(yolo_probe PRIVATE cxx_std_17)
target_include_directories(yolo_probe PRIVATE ${YOLO_SOURCE_DIR}/include
  ${RKNN_API_INCLUDE_DIR} ${RGA_INCLUDE_DIR} ${OpenCV_INCLUDE_DIRS})
ament_target_dependencies(yolo_probe rclcpp)
target_link_libraries(yolo_probe ${OpenCV_LIBRARIES} ${RKNNRT_LIBRARY} ${RGA_LIBRARY})
add_library(yolo_postprocess SHARED postprocess_api.cpp
  ${YOLO_SOURCE_DIR}/src/postprocess.cpp)
target_compile_features(yolo_postprocess PRIVATE cxx_std_17)
target_include_directories(yolo_postprocess PRIVATE ${YOLO_SOURCE_DIR}/include)
option(BUILD_ROS_YOLO "Build actual ROS detector for end-to-end replay" OFF)
if(BUILD_ROS_YOLO)
  find_package(sensor_msgs REQUIRED)
  find_package(std_msgs REQUIRED)
  find_package(robot_interfaces REQUIRED)
  add_executable(yolo_ros_probe ros_replay.cpp
    ${YOLO_SOURCE_DIR}/src/rknn_yolov6_node.cpp
    ${YOLO_SOURCE_DIR}/src/detector_backend_rknn.cpp
    ${YOLO_SOURCE_DIR}/src/postprocess.cpp)
  target_compile_features(yolo_ros_probe PRIVATE cxx_std_17)
  target_include_directories(yolo_ros_probe PRIVATE ${YOLO_SOURCE_DIR}/include
    ${RKNN_API_INCLUDE_DIR} ${RGA_INCLUDE_DIR} ${OpenCV_INCLUDE_DIRS})
  ament_target_dependencies(yolo_ros_probe rclcpp sensor_msgs std_msgs robot_interfaces)
  target_link_libraries(yolo_ros_probe ${OpenCV_LIBRARIES} ${RKNNRT_LIBRARY} ${RGA_LIBRARY})
endif()
