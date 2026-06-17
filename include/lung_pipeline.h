#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace lung {

struct MHDHeader {
    int ndims = 3;
    int width = 0;
    int height = 0;
    int depth = 0;
    float spacingX = 1.0f;
    float spacingY = 1.0f;
    float spacingZ = 1.0f;
    std::string elementType;
    std::string elementDataFile;
    bool binaryData = true;
    bool msb = false;
};

struct Volume {
    int width = 0;
    int height = 0;
    int depth = 0;
    float spacingX = 1.0f;
    float spacingY = 1.0f;
    float spacingZ = 1.0f;
    std::vector<float> hu;

    float at(int x, int y, int z) const {
        return hu[static_cast<std::size_t>(z) * width * height + y * width + x];
    }
};

struct Nodule {
    float centerX = 0.0f;
    float centerY = 0.0f;
    float centerZ = 0.0f;
    float diameterMm = 0.0f;
    float circularity = 0.0f;
    float meanHU = 0.0f;
    float stdHU = 0.0f;
    float glcmContrast = 0.0f;
    float glcmEnergy = 0.0f;
    float glcmHomogeneity = 0.0f;
    float minBoundaryDistanceMm = 0.0f;
    float maxAspectRatio = 1.0f;
    int sliceCount = 0;
};

struct PipelineOptions {
    std::string mhdPath;
    std::string outputDir;
    float windowLevel = -600.0f;
    float windowWidth = 1500.0f;
    float sigmaLow = 30.0f;
    float sigmaHigh = 5.0f;
    float minDiameterMm = 3.0f;
    float maxDiameterMm = 30.0f;
    float minCircularity = 0.46f;
    float candidateBandpassPercentile = 85.0f;
    float candidateMinSeedHU = -500.0f;
    float candidateMaxSeedHU = 250.0f;
    float candidateMinMeanHU = -650.0f;
    float finalMinMeanHU = -410.0f;
    float finalMaxMeanHU = 60.0f;
    float finalMinStdHU = 25.0f;
    float finalMaxStdHU = 210.0f;
    float finalMaxGLCMContrast = 3.3f;
    float finalMinGLCMHomogeneity = 0.45f;
    float finalMinBoundaryDistanceMm = 0.0f;
    float finalMaxAspectRatio = 1000.0f;
    int finalMinSliceCount = 0;
    float finalMinSliceCountExceptionDiameterMm = 0.0f;
    int finalMaxSliceCount = 18;
    int maxFinalCandidates = 180;
    float rankDiameterRewardCapMm = 0.0f;
    float rankSliceCountPenalty = 0.0f;
    bool useLearnedRankScore = true;
    float learnedScoreQuantile = 0.50f;
    int learnedTopK = 0;
    bool writeDebugImages = true;
};

struct PipelineResult {
    Volume volume;
    int stage1MaskPixels = 0;
    int stage3Candidates = 0;
    std::vector<Nodule> nodules;
};

MHDHeader parseMHD(const std::string& mhdPath);
Volume loadVolumeFromMHD(const std::string& mhdPath);
PipelineResult runPipeline(const PipelineOptions& options);

} // namespace lung
