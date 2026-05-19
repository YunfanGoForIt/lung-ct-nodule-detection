#include "viewer.h"

#include <algorithm>
#include <filesystem>
#include <regex>
#include <stdexcept>

namespace fs = std::filesystem;

namespace lung {
namespace {

int parseSliceIndex(const std::string& name) {
    static const std::regex pattern(R"(slice_(\d{3})_window\.pgm)");
    std::smatch match;
    if (!std::regex_match(name, match, pattern)) {
        return -1;
    }
    return std::stoi(match[1].str());
}

} // namespace

ViewerDataset discoverViewerDataset(const std::string& outputDir) {
    if (!fs::exists(outputDir)) {
        throw std::runtime_error("output dir does not exist: " + outputDir);
    }
    ViewerDataset dataset;
    dataset.outputDir = outputDir;
    for (const auto& entry : fs::directory_iterator(outputDir)) {
        if (!entry.is_regular_file()) {
            continue;
        }
        const std::string name = entry.path().filename().string();
        const int index = parseSliceIndex(name);
        if (index >= 0) {
            dataset.sliceIndices.push_back(index);
            continue;
        }
        if (name == "mip.ppm") {
            dataset.hasMIP = true;
        }
    }
    std::sort(dataset.sliceIndices.begin(), dataset.sliceIndices.end());
    dataset.sliceIndices.erase(std::unique(dataset.sliceIndices.begin(), dataset.sliceIndices.end()), dataset.sliceIndices.end());
    return dataset;
}

} // namespace lung
