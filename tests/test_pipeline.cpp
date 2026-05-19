#include "lung_pipeline.h"

#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

static void writeSyntheticMHD(const fs::path& dir) {
    fs::create_directories(dir);
    const int width = 64;
    const int height = 64;
    const int depth = 16;
    std::vector<short> voxels(width * height * depth, 80);

    auto setVoxel = [&](int x, int y, int z, short value) {
        voxels[z * width * height + y * width + x] = value;
    };

    for (int z = 0; z < depth; ++z) {
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                const double left = ((x - 22.0) * (x - 22.0)) / (12.0 * 12.0)
                                  + ((y - 32.0) * (y - 32.0)) / (20.0 * 20.0);
                const double right = ((x - 42.0) * (x - 42.0)) / (12.0 * 12.0)
                                   + ((y - 32.0) * (y - 32.0)) / (20.0 * 20.0);
                if (left <= 1.0 || right <= 1.0) {
                    setVoxel(x, y, z, -760);
                }
            }
        }
    }

    for (int z = 6; z <= 9; ++z) {
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                const double r2 = (x - 42.0) * (x - 42.0) + (y - 31.0) * (y - 31.0);
                if (r2 <= 4.0 * 4.0) {
                    setVoxel(x, y, z, -120);
                }
            }
        }
    }

    std::ofstream raw(dir / "synthetic.raw", std::ios::binary);
    raw.write(reinterpret_cast<const char*>(voxels.data()), static_cast<std::streamsize>(voxels.size() * sizeof(short)));

    std::ofstream mhd(dir / "synthetic.mhd");
    mhd << "ObjectType = Image\n";
    mhd << "NDims = 3\n";
    mhd << "DimSize = " << width << " " << height << " " << depth << "\n";
    mhd << "ElementType = MET_SHORT\n";
    mhd << "ElementSpacing = 1 1 1\n";
    mhd << "ElementByteOrderMSB = False\n";
    mhd << "ElementDataFile = synthetic.raw\n";
    mhd << "BinaryData = True\n";
    mhd << "Offset = 0 0 0\n";
}

int main() {
    const fs::path root = fs::current_path();
    const fs::path testDir = root / "build" / "synthetic_case";
    const fs::path outDir = root / "build" / "e2e_output";
    fs::remove_all(testDir);
    fs::remove_all(outDir);
    writeSyntheticMHD(testDir);

    lung::PipelineOptions options;
    options.mhdPath = (testDir / "synthetic.mhd").string();
    options.outputDir = outDir.string();
    options.windowLevel = -600.0f;
    options.windowWidth = 1500.0f;
    options.sigmaLow = 12.0f;
    options.sigmaHigh = 2.5f;
    options.minDiameterMm = 3.0f;
    options.maxDiameterMm = 14.0f;
    options.minCircularity = 0.45f;
    options.writeDebugImages = true;

    const lung::PipelineResult result = lung::runPipeline(options);

    assert(result.volume.width == 64);
    assert(result.volume.height == 64);
    assert(result.volume.depth == 16);
    assert(result.stage1MaskPixels > 300);
    assert(result.stage3Candidates >= 1);
    assert(!result.nodules.empty());

    bool foundSyntheticNodule = false;
    for (const auto& nodule : result.nodules) {
        if (std::abs(nodule.centerX - 42) <= 4 && std::abs(nodule.centerY - 31) <= 4 && nodule.centerZ >= 5 && nodule.centerZ <= 10) {
            foundSyntheticNodule = true;
            assert(nodule.circularity > 0.45);
            assert(nodule.diameterMm >= 3.0f);
            assert(nodule.glcmEnergy > 0.0);
        }
    }
    assert(foundSyntheticNodule);

    assert(fs::exists(outDir / "meta.txt"));
    assert(fs::exists(outDir / "features.csv"));
    assert(fs::exists(outDir / "mip.ppm"));
    assert(fs::exists(outDir / "slice_008_window.pgm"));
    assert(fs::exists(outDir / "slice_008_mask.pgm"));
    assert(fs::exists(outDir / "slice_008_bandpass.pgm"));
    assert(fs::exists(outDir / "slice_008_overlay.ppm"));

    std::cout << "E2E pipeline OK: "
              << result.nodules.size() << " nodules, "
              << result.stage3Candidates << " raw candidates\n";
    return 0;
}
