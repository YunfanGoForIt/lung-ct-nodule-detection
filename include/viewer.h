#pragma once

#include <string>
#include <vector>

namespace lung {

struct ViewerDataset {
    std::string outputDir;
    std::vector<int> sliceIndices;
    bool hasMIP = false;
};

ViewerDataset discoverViewerDataset(const std::string& outputDir);

} // namespace lung
