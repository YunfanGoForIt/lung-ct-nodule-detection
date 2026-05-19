#include "viewer.h"

#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>

namespace fs = std::filesystem;

namespace {

cv::Mat loadImageOrThrow(const fs::path& path, int flags) {
    cv::Mat image = cv::imread(path.string(), flags);
    if (image.empty()) {
        throw std::runtime_error("cannot load image: " + path.string());
    }
    return image;
}

cv::Mat composeGrid(const cv::Mat& a, const cv::Mat& b, const cv::Mat& c, const cv::Mat& d) {
    const int width = std::max({a.cols, b.cols, c.cols, d.cols});
    const int height = std::max({a.rows, b.rows, c.rows, d.rows});
    cv::Mat out(height * 2, width * 2, CV_8UC3, cv::Scalar(20, 20, 20));
    auto paste = [&](const cv::Mat& src, int ox, int oy) {
        cv::Mat dst = out(cv::Rect(ox, oy, src.cols, src.rows));
        if (src.channels() == 1) {
            cv::Mat color;
            cv::cvtColor(src, color, cv::COLOR_GRAY2BGR);
            color.copyTo(dst);
        } else {
            src.copyTo(dst);
        }
    };
    paste(a, 0, 0);
    paste(b, width, 0);
    paste(c, 0, height);
    paste(d, width, height);
    return out;
}

} // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <output_dir>\n";
        return 2;
    }

    try {
        const std::string outputDir = argv[1];
        const lung::ViewerDataset dataset = lung::discoverViewerDataset(outputDir);
        if (dataset.sliceIndices.empty()) {
            throw std::runtime_error("no slice_XXX_window.pgm files found in " + outputDir);
        }

        const fs::path dir(outputDir);
        const int maxIndex = dataset.sliceIndices.back();
        int current = dataset.sliceIndices.front();

        cv::namedWindow("control", cv::WINDOW_AUTOSIZE);
        cv::namedWindow("viewer", cv::WINDOW_NORMAL);
        if (dataset.hasMIP) {
            cv::namedWindow("mip", cv::WINDOW_NORMAL);
        }

        cv::createTrackbar("slice", "control", &current, maxIndex);
        cv::resizeWindow("viewer", 960, 720);

        for (;;) {
            if (std::find(dataset.sliceIndices.begin(), dataset.sliceIndices.end(), current) == dataset.sliceIndices.end()) {
                cv::imshow("viewer", cv::Mat(200, 400, CV_8UC3, cv::Scalar(0, 0, 0)));
                cv::displayOverlay("viewer", "No data for this slice index", 1000);
            } else {
                const std::string suffix = "slice_" + (current < 10 ? std::string("00") : current < 100 ? std::string("0") : std::string("")) + std::to_string(current);
                const cv::Mat window = loadImageOrThrow(dir / (suffix + "_window.pgm"), cv::IMREAD_GRAYSCALE);
                const cv::Mat mask = loadImageOrThrow(dir / (suffix + "_mask.pgm"), cv::IMREAD_GRAYSCALE);
                const cv::Mat bandpass = loadImageOrThrow(dir / (suffix + "_bandpass.pgm"), cv::IMREAD_GRAYSCALE);
                const cv::Mat overlay = loadImageOrThrow(dir / (suffix + "_overlay.ppm"), cv::IMREAD_COLOR);
                cv::imshow("viewer", composeGrid(window, mask, bandpass, overlay));
            }

            if (dataset.hasMIP) {
                const cv::Mat mip = loadImageOrThrow(dir / "mip.ppm", cv::IMREAD_COLOR);
                cv::imshow("mip", mip);
            }

            const int key = cv::waitKey(30);
            if (key == 27 || key == 'q') {
                break;
            }
            if (key == 81 || key == 'a') {
                current = std::max(0, current - 1);
                cv::setTrackbarPos("slice", "control", current);
            } else if (key == 83 || key == 'd') {
                current = std::min(maxIndex, current + 1);
                cv::setTrackbarPos("slice", "control", current);
            }
        }

        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "error: " << ex.what() << "\n";
        return 1;
    }
}
