cmake_minimum_required(VERSION 3.16)
project(LungNoduleDetection LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(OpenCV REQUIRED)

add_library(lung_pipeline src/lung_pipeline.cpp)
target_include_directories(lung_pipeline PUBLIC include)

add_library(lung_viewer_core src/viewer.cpp)
target_include_directories(lung_viewer_core PUBLIC include)

add_executable(lung_nodule src/main.cpp)
target_link_libraries(lung_nodule PRIVATE lung_pipeline)

add_executable(lung_viewer src/viewer_main.cpp)
target_link_libraries(lung_viewer PRIVATE lung_viewer_core ${OpenCV_LIBS})
target_include_directories(lung_viewer PRIVATE ${OpenCV_INCLUDE_DIRS})

add_executable(test_pipeline tests/test_pipeline.cpp)
target_link_libraries(test_pipeline PRIVATE lung_pipeline)

add_executable(test_viewer tests/test_viewer.cpp)
target_link_libraries(test_viewer PRIVATE lung_viewer_core)

enable_testing()
add_test(NAME e2e_pipeline COMMAND test_pipeline)
add_test(NAME viewer_scan COMMAND test_viewer)
