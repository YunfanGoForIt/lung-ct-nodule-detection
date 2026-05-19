#include "viewer.h"

#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>

namespace fs = std::filesystem;

int main() {
    const fs::path dir = fs::current_path() / "build" / "viewer_scan_test";
    fs::remove_all(dir);
    fs::create_directories(dir);

    for (int z : {2, 0, 1}) {
        std::ofstream(dir / ("slice_00" + std::to_string(z) + "_window.pgm")) << "P5\n1 1\n255\n\x00";
        std::ofstream(dir / ("slice_00" + std::to_string(z) + "_mask.pgm")) << "P5\n1 1\n255\n\x00";
        std::ofstream(dir / ("slice_00" + std::to_string(z) + "_bandpass.pgm")) << "P5\n1 1\n255\n\x00";
        std::ofstream(dir / ("slice_00" + std::to_string(z) + "_overlay.ppm")) << "P6\n1 1\n255\n\x00\x00\x00";
    }
    std::ofstream(dir / "mip.ppm") << "P6\n1 1\n255\n\x00\x00\x00";

    const lung::ViewerDataset dataset = lung::discoverViewerDataset(dir.string());
    assert(dataset.outputDir == dir.string());
    assert(dataset.hasMIP);
    assert(dataset.sliceIndices.size() == 3);
    assert(dataset.sliceIndices[0] == 0);
    assert(dataset.sliceIndices[1] == 1);
    assert(dataset.sliceIndices[2] == 2);

    std::cout << "viewer scan OK\n";
    return 0;
}
