#include "lung_pipeline.h"

#include <cstdlib>
#include <exception>
#include <iostream>
#include <string>

namespace {

void printUsage(const char* argv0) {
    std::cerr << "Usage: " << argv0 << " <input.mhd> <output_dir> [--wl -600] [--ww 1500] "
              << "[--sigma-low 30] [--sigma-high 5] [--min-diameter 3] [--max-diameter 30] "
              << "[--min-circularity 0.45] [--final-min-mean-hu -1000] "
              << "[--final-max-mean-hu 1000] [--final-min-std-hu 0] [--final-max-std-hu 1000] "
              << "[--final-max-glcm-contrast 1000] [--final-min-glcm-homogeneity 0] "
              << "[--final-max-slice-count 1000000] [--max-final-candidates 0]\n";
}

float parseFloat(const char* value, const std::string& name) {
    char* end = nullptr;
    const float parsed = std::strtof(value, &end);
    if (end == value || *end != '\0') {
        throw std::runtime_error("invalid value for " + name + ": " + value);
    }
    return parsed;
}

int parseInt(const char* value, const std::string& name) {
    char* end = nullptr;
    const long parsed = std::strtol(value, &end, 10);
    if (end == value || *end != '\0') {
        throw std::runtime_error("invalid value for " + name + ": " + value);
    }
    return static_cast<int>(parsed);
}

} // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        printUsage(argv[0]);
        return 2;
    }

    lung::PipelineOptions options;
    options.mhdPath = argv[1];
    options.outputDir = argv[2];

    try {
        for (int i = 3; i < argc; ++i) {
            const std::string arg = argv[i];
            if (arg == "--wl" && i + 1 < argc) {
                options.windowLevel = parseFloat(argv[++i], arg);
            } else if (arg == "--ww" && i + 1 < argc) {
                options.windowWidth = parseFloat(argv[++i], arg);
            } else if (arg == "--sigma-low" && i + 1 < argc) {
                options.sigmaLow = parseFloat(argv[++i], arg);
            } else if (arg == "--sigma-high" && i + 1 < argc) {
                options.sigmaHigh = parseFloat(argv[++i], arg);
            } else if (arg == "--min-diameter" && i + 1 < argc) {
                options.minDiameterMm = parseFloat(argv[++i], arg);
            } else if (arg == "--max-diameter" && i + 1 < argc) {
                options.maxDiameterMm = parseFloat(argv[++i], arg);
            } else if (arg == "--min-circularity" && i + 1 < argc) {
                options.minCircularity = parseFloat(argv[++i], arg);
            } else if (arg == "--final-min-mean-hu" && i + 1 < argc) {
                options.finalMinMeanHU = parseFloat(argv[++i], arg);
            } else if (arg == "--final-max-mean-hu" && i + 1 < argc) {
                options.finalMaxMeanHU = parseFloat(argv[++i], arg);
            } else if (arg == "--final-min-std-hu" && i + 1 < argc) {
                options.finalMinStdHU = parseFloat(argv[++i], arg);
            } else if (arg == "--final-max-std-hu" && i + 1 < argc) {
                options.finalMaxStdHU = parseFloat(argv[++i], arg);
            } else if (arg == "--final-max-glcm-contrast" && i + 1 < argc) {
                options.finalMaxGLCMContrast = parseFloat(argv[++i], arg);
            } else if (arg == "--final-min-glcm-homogeneity" && i + 1 < argc) {
                options.finalMinGLCMHomogeneity = parseFloat(argv[++i], arg);
            } else if (arg == "--final-max-slice-count" && i + 1 < argc) {
                options.finalMaxSliceCount = parseInt(argv[++i], arg);
            } else if (arg == "--max-final-candidates" && i + 1 < argc) {
                options.maxFinalCandidates = parseInt(argv[++i], arg);
            } else if (arg == "--no-debug-images") {
                options.writeDebugImages = false;
            } else {
                printUsage(argv[0]);
                return 2;
            }
        }

        const lung::PipelineResult result = lung::runPipeline(options);
        std::cout << "Loaded volume: " << result.volume.width << "x" << result.volume.height
                  << "x" << result.volume.depth << "\n";
        std::cout << "Stage1 lung-mask voxels: " << result.stage1MaskPixels << "\n";
        std::cout << "Stage3/4 confirmed nodules: " << result.nodules.size()
                  << " from " << result.stage3Candidates << " filtered 2D candidates\n";
        std::cout << "Outputs written to: " << options.outputDir << "\n";
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "error: " << ex.what() << "\n";
        return 1;
    }
}
