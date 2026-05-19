CXX ?= c++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -pedantic
CPPFLAGS ?= -Iinclude

SRC := src/lung_pipeline.cpp
APP_SRC := src/main.cpp
TEST_SRC := tests/test_pipeline.cpp
VIEWER_SRC := src/viewer.cpp
VIEWER_APP_SRC := src/viewer_main.cpp
VIEWER_TEST_SRC := tests/test_viewer.cpp
OPENCV_FLAGS := $(shell /opt/homebrew/bin/pkg-config --cflags --libs opencv4 2>/dev/null)

.PHONY: all test clean

all: build/lung_pipeline build/lung_viewer

build:
	mkdir -p build

build/lung_pipeline: $(SRC) $(APP_SRC) | build
	$(CXX) $(CXXFLAGS) $(CPPFLAGS) $(SRC) $(APP_SRC) -o $@

build/test_pipeline: $(SRC) $(TEST_SRC) | build
	$(CXX) $(CXXFLAGS) $(CPPFLAGS) $(SRC) $(TEST_SRC) -o $@

build/lung_viewer: $(VIEWER_SRC) $(VIEWER_APP_SRC) | build
	$(CXX) $(CXXFLAGS) $(CPPFLAGS) $(VIEWER_SRC) $(VIEWER_APP_SRC) $(OPENCV_FLAGS) -o $@

build/test_viewer: $(VIEWER_SRC) $(VIEWER_TEST_SRC) | build
	$(CXX) $(CXXFLAGS) $(CPPFLAGS) $(VIEWER_SRC) $(VIEWER_TEST_SRC) -o $@

test: build/test_pipeline build/test_viewer
	./build/test_pipeline
	./build/test_viewer

clean:
	rm -rf build
