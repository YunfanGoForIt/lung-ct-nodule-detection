#include "lung_pipeline.h"

#include <algorithm>
#include <cmath>
#include <complex>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <limits>
#include <numeric>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace fs = std::filesystem;

namespace lung {
namespace {

constexpr float kPi = 3.14159265358979323846f;

struct GrayImage {
    int width = 0;
    int height = 0;
    std::vector<std::uint8_t> pixels;

    std::uint8_t& at(int x, int y) { return pixels[static_cast<std::size_t>(y) * width + x]; }
    std::uint8_t at(int x, int y) const { return pixels[static_cast<std::size_t>(y) * width + x]; }
};

struct FloatImage {
    int width = 0;
    int height = 0;
    std::vector<float> pixels;

    float& at(int x, int y) { return pixels[static_cast<std::size_t>(y) * width + x]; }
    float at(int x, int y) const { return pixels[static_cast<std::size_t>(y) * width + x]; }
};

struct RGB {
    std::uint8_t r = 0;
    std::uint8_t g = 0;
    std::uint8_t b = 0;
};

struct RGBImage {
    int width = 0;
    int height = 0;
    std::vector<RGB> pixels;

    RGB& at(int x, int y) { return pixels[static_cast<std::size_t>(y) * width + x]; }
    RGB at(int x, int y) const { return pixels[static_cast<std::size_t>(y) * width + x]; }
};

struct Component {
    int z = 0;
    int area = 0;
    int perimeter = 0;
    int minX = 0;
    int minY = 0;
    int maxX = 0;
    int maxY = 0;
    float centerX = 0.0f;
    float centerY = 0.0f;
    float diameterMm = 0.0f;
    float circularity = 0.0f;
    float meanHU = 0.0f;
    float stdHU = 0.0f;
    float glcmContrast = 0.0f;
    float glcmEnergy = 0.0f;
    float glcmHomogeneity = 0.0f;
    float minBoundaryDistanceMm = 0.0f;
    float aspectRatio = 1.0f;
    std::vector<int> indices;
};

static std::string trim(const std::string& s) {
    const auto begin = s.find_first_not_of(" \t\r\n");
    if (begin == std::string::npos) {
        return "";
    }
    const auto end = s.find_last_not_of(" \t\r\n");
    return s.substr(begin, end - begin + 1);
}

static std::vector<std::string> splitWords(const std::string& s) {
    std::istringstream iss(s);
    std::vector<std::string> words;
    std::string word;
    while (iss >> word) {
        words.push_back(word);
    }
    return words;
}

static fs::path rawPathFor(const fs::path& mhdPath, const std::string& rawName) {
    const fs::path raw(rawName);
    if (raw.is_absolute()) {
        return raw;
    }
    return mhdPath.parent_path() / raw;
}

static std::uint16_t readU16LE(const char* p) {
    return static_cast<std::uint16_t>(static_cast<unsigned char>(p[0]))
         | static_cast<std::uint16_t>(static_cast<unsigned char>(p[1]) << 8U);
}

static std::uint32_t readU32LE(const char* p) {
    return static_cast<std::uint32_t>(static_cast<unsigned char>(p[0]))
         | (static_cast<std::uint32_t>(static_cast<unsigned char>(p[1])) << 8U)
         | (static_cast<std::uint32_t>(static_cast<unsigned char>(p[2])) << 16U)
         | (static_cast<std::uint32_t>(static_cast<unsigned char>(p[3])) << 24U);
}

static GrayImage windowSlice(const Volume& volume, int z, float wl, float ww) {
    GrayImage image{volume.width, volume.height, std::vector<std::uint8_t>(static_cast<std::size_t>(volume.width) * volume.height)};
    const float low = wl - ww * 0.5f;
    for (int y = 0; y < volume.height; ++y) {
        for (int x = 0; x < volume.width; ++x) {
            float value = (volume.at(x, y, z) - low) / ww * 255.0f;
            value = std::clamp(value, 0.0f, 255.0f);
            image.at(x, y) = static_cast<std::uint8_t>(std::lround(value));
        }
    }
    return image;
}

static FloatImage huSlice(const Volume& volume, int z) {
    FloatImage image{volume.width, volume.height, std::vector<float>(static_cast<std::size_t>(volume.width) * volume.height)};
    const std::size_t offset = static_cast<std::size_t>(z) * volume.width * volume.height;
    std::copy(volume.hu.begin() + static_cast<std::ptrdiff_t>(offset),
              volume.hu.begin() + static_cast<std::ptrdiff_t>(offset + image.pixels.size()),
              image.pixels.begin());
    return image;
}

static void writePGM(const fs::path& path, const GrayImage& image) {
    std::ofstream out(path, std::ios::binary);
    if (!out) {
        throw std::runtime_error("cannot write " + path.string());
    }
    out << "P5\n" << image.width << " " << image.height << "\n255\n";
    out.write(reinterpret_cast<const char*>(image.pixels.data()), static_cast<std::streamsize>(image.pixels.size()));
}

static void writePPM(const fs::path& path, const RGBImage& image) {
    std::ofstream out(path, std::ios::binary);
    if (!out) {
        throw std::runtime_error("cannot write " + path.string());
    }
    out << "P6\n" << image.width << " " << image.height << "\n255\n";
    for (const RGB& p : image.pixels) {
        out.put(static_cast<char>(p.r));
        out.put(static_cast<char>(p.g));
        out.put(static_cast<char>(p.b));
    }
}

static GrayImage maskToGray(const std::vector<std::uint8_t>& mask, int width, int height) {
    GrayImage image{width, height, std::vector<std::uint8_t>(static_cast<std::size_t>(width) * height)};
    for (std::size_t i = 0; i < mask.size(); ++i) {
        image.pixels[i] = mask[i] ? 255 : 0;
    }
    return image;
}

static std::vector<std::uint8_t> erode(const std::vector<std::uint8_t>& src, int width, int height, int radius) {
    std::vector<std::uint8_t> dst(src.size(), 0);
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            bool keep = true;
            for (int dy = -radius; dy <= radius && keep; ++dy) {
                for (int dx = -radius; dx <= radius; ++dx) {
                    if (dx * dx + dy * dy > radius * radius) {
                        continue;
                    }
                    const int nx = x + dx;
                    const int ny = y + dy;
                    if (nx < 0 || ny < 0 || nx >= width || ny >= height || !src[static_cast<std::size_t>(ny) * width + nx]) {
                        keep = false;
                        break;
                    }
                }
            }
            dst[static_cast<std::size_t>(y) * width + x] = keep ? 1 : 0;
        }
    }
    return dst;
}

static std::vector<std::uint8_t> dilate(const std::vector<std::uint8_t>& src, int width, int height, int radius) {
    std::vector<std::uint8_t> dst(src.size(), 0);
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            bool hit = false;
            for (int dy = -radius; dy <= radius && !hit; ++dy) {
                for (int dx = -radius; dx <= radius; ++dx) {
                    if (dx * dx + dy * dy > radius * radius) {
                        continue;
                    }
                    const int nx = x + dx;
                    const int ny = y + dy;
                    if (nx >= 0 && ny >= 0 && nx < width && ny < height && src[static_cast<std::size_t>(ny) * width + nx]) {
                        hit = true;
                        break;
                    }
                }
            }
            dst[static_cast<std::size_t>(y) * width + x] = hit ? 1 : 0;
        }
    }
    return dst;
}

static std::vector<std::uint8_t> openMask(const std::vector<std::uint8_t>& src, int width, int height, int radius) {
    return dilate(erode(src, width, height, radius), width, height, radius);
}

static std::vector<std::uint8_t> closeMask(const std::vector<std::uint8_t>& src, int width, int height, int radius) {
    return erode(dilate(src, width, height, radius), width, height, radius);
}

static std::vector<std::vector<int>> connectedComponents(const std::vector<std::uint8_t>& mask, int width, int height) {
    std::vector<std::vector<int>> components;
    std::vector<std::uint8_t> seen(mask.size(), 0);
    const int dx[8] = {1, 1, 0, -1, -1, -1, 0, 1};
    const int dy[8] = {0, 1, 1, 1, 0, -1, -1, -1};
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const int start = y * width + x;
            if (!mask[start] || seen[start]) {
                continue;
            }
            std::vector<int> component;
            std::queue<int> q;
            q.push(start);
            seen[start] = 1;
            while (!q.empty()) {
                const int idx = q.front();
                q.pop();
                component.push_back(idx);
                const int cx = idx % width;
                const int cy = idx / width;
                for (int k = 0; k < 8; ++k) {
                    const int nx = cx + dx[k];
                    const int ny = cy + dy[k];
                    if (nx < 0 || ny < 0 || nx >= width || ny >= height) {
                        continue;
                    }
                    const int next = ny * width + nx;
                    if (mask[next] && !seen[next]) {
                        seen[next] = 1;
                        q.push(next);
                    }
                }
            }
            components.push_back(std::move(component));
        }
    }
    return components;
}

static void removeBorderConnected(std::vector<std::uint8_t>& mask, int width, int height) {
    std::vector<std::uint8_t> seen(mask.size(), 0);
    std::queue<int> q;
    auto pushIf = [&](int x, int y) {
        const int idx = y * width + x;
        if (mask[idx] && !seen[idx]) {
            seen[idx] = 1;
            q.push(idx);
        }
    };
    for (int x = 0; x < width; ++x) {
        pushIf(x, 0);
        pushIf(x, height - 1);
    }
    for (int y = 0; y < height; ++y) {
        pushIf(0, y);
        pushIf(width - 1, y);
    }
    const int dx[4] = {1, 0, -1, 0};
    const int dy[4] = {0, 1, 0, -1};
    while (!q.empty()) {
        const int idx = q.front();
        q.pop();
        mask[idx] = 0;
        const int cx = idx % width;
        const int cy = idx / width;
        for (int k = 0; k < 4; ++k) {
            const int nx = cx + dx[k];
            const int ny = cy + dy[k];
            if (nx < 0 || ny < 0 || nx >= width || ny >= height) {
                continue;
            }
            const int next = ny * width + nx;
            if (mask[next] && !seen[next]) {
                seen[next] = 1;
                q.push(next);
            }
        }
    }
}

static std::vector<std::uint8_t> keepLargest(const std::vector<std::uint8_t>& mask, int width, int height, int keepCount) {
    auto components = connectedComponents(mask, width, height);
    std::sort(components.begin(), components.end(), [](const auto& a, const auto& b) {
        return a.size() > b.size();
    });
    std::vector<std::uint8_t> out(mask.size(), 0);
    for (int i = 0; i < keepCount && i < static_cast<int>(components.size()); ++i) {
        for (int idx : components[i]) {
            out[idx] = 1;
        }
    }
    return out;
}

static std::vector<std::uint8_t> fillHoles(const std::vector<std::uint8_t>& mask, int width, int height) {
    std::vector<std::uint8_t> background(mask.size(), 0);
    std::queue<int> q;
    auto pushIf = [&](int x, int y) {
        const int idx = y * width + x;
        if (!mask[idx] && !background[idx]) {
            background[idx] = 1;
            q.push(idx);
        }
    };
    for (int x = 0; x < width; ++x) {
        pushIf(x, 0);
        pushIf(x, height - 1);
    }
    for (int y = 0; y < height; ++y) {
        pushIf(0, y);
        pushIf(width - 1, y);
    }
    const int dx[4] = {1, 0, -1, 0};
    const int dy[4] = {0, 1, 0, -1};
    while (!q.empty()) {
        const int idx = q.front();
        q.pop();
        const int cx = idx % width;
        const int cy = idx / width;
        for (int k = 0; k < 4; ++k) {
            const int nx = cx + dx[k];
            const int ny = cy + dy[k];
            if (nx < 0 || ny < 0 || nx >= width || ny >= height) {
                continue;
            }
            const int next = ny * width + nx;
            if (!mask[next] && !background[next]) {
                background[next] = 1;
                q.push(next);
            }
        }
    }
    std::vector<std::uint8_t> filled = mask;
    for (std::size_t i = 0; i < mask.size(); ++i) {
        if (!mask[i] && !background[i]) {
            filled[i] = 1;
        }
    }
    return filled;
}

static std::vector<std::uint8_t> segmentLungSlice(const FloatImage& hu) {
    std::vector<std::uint8_t> binary(hu.pixels.size(), 0);
    for (std::size_t i = 0; i < hu.pixels.size(); ++i) {
        binary[i] = hu.pixels[i] < -320.0f ? 1 : 0;
    }
    removeBorderConnected(binary, hu.width, hu.height);
    binary = openMask(binary, hu.width, hu.height, 1);
    binary = keepLargest(binary, hu.width, hu.height, 2);
    binary = closeMask(binary, hu.width, hu.height, 3);
    binary = fillHoles(binary, hu.width, hu.height);
    return binary;
}

static int nextPow2(int value) {
    int n = 1;
    while (n < value) {
        n <<= 1;
    }
    return n;
}

static void fft1d(std::vector<std::complex<float>>& a, bool inverse) {
    const int n = static_cast<int>(a.size());
    for (int i = 1, j = 0; i < n; ++i) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1) {
            j ^= bit;
        }
        j ^= bit;
        if (i < j) {
            std::swap(a[i], a[j]);
        }
    }
    for (int len = 2; len <= n; len <<= 1) {
        const float angle = 2.0f * kPi / static_cast<float>(len) * (inverse ? 1.0f : -1.0f);
        const std::complex<float> wlen(std::cos(angle), std::sin(angle));
        for (int i = 0; i < n; i += len) {
            std::complex<float> w(1.0f, 0.0f);
            for (int j = 0; j < len / 2; ++j) {
                const std::complex<float> u = a[i + j];
                const std::complex<float> v = a[i + j + len / 2] * w;
                a[i + j] = u + v;
                a[i + j + len / 2] = u - v;
                w *= wlen;
            }
        }
    }
    if (inverse) {
        for (auto& v : a) {
            v /= static_cast<float>(n);
        }
    }
}

static GrayImage bandPassEnhance(const FloatImage& src, const std::vector<std::uint8_t>& mask, float sigmaLow, float sigmaHigh) {
    const int width = nextPow2(src.width);
    const int height = nextPow2(src.height);
    std::vector<std::complex<float>> data(static_cast<std::size_t>(width) * height);
    const float low = -1000.0f;
    const float high = 400.0f;
    for (int y = 0; y < src.height; ++y) {
        for (int x = 0; x < src.width; ++x) {
            const float normalized = std::clamp((src.at(x, y) - low) / (high - low), 0.0f, 1.0f) * 255.0f;
            const float centered = mask[static_cast<std::size_t>(y) * src.width + x] ? normalized - 80.0f : 0.0f;
            data[static_cast<std::size_t>(y) * width + x] = {centered, 0.0f};
        }
    }

    std::vector<std::complex<float>> line(static_cast<std::size_t>(std::max(width, height)));
    for (int y = 0; y < height; ++y) {
        std::copy(data.begin() + static_cast<std::ptrdiff_t>(static_cast<std::size_t>(y) * width),
                  data.begin() + static_cast<std::ptrdiff_t>(static_cast<std::size_t>(y) * width + width),
                  line.begin());
        line.resize(width);
        fft1d(line, false);
        std::copy(line.begin(), line.end(), data.begin() + static_cast<std::ptrdiff_t>(static_cast<std::size_t>(y) * width));
        line.resize(static_cast<std::size_t>(std::max(width, height)));
    }
    for (int x = 0; x < width; ++x) {
        for (int y = 0; y < height; ++y) {
            line[static_cast<std::size_t>(y)] = data[static_cast<std::size_t>(y) * width + x];
        }
        line.resize(height);
        fft1d(line, false);
        for (int y = 0; y < height; ++y) {
            data[static_cast<std::size_t>(y) * width + x] = line[static_cast<std::size_t>(y)];
        }
        line.resize(static_cast<std::size_t>(std::max(width, height)));
    }

    for (int y = 0; y < height; ++y) {
        const float fy = static_cast<float>(std::min(y, height - y));
        for (int x = 0; x < width; ++x) {
            const float fx = static_cast<float>(std::min(x, width - x));
            const float d2 = fx * fx + fy * fy;
            const float lowPass = std::exp(-d2 / (2.0f * sigmaLow * sigmaLow));
            const float highPassCut = std::exp(-d2 / (2.0f * sigmaHigh * sigmaHigh));
            const float h = std::max(0.0f, lowPass - highPassCut);
            data[static_cast<std::size_t>(y) * width + x] *= h;
        }
    }

    for (int x = 0; x < width; ++x) {
        for (int y = 0; y < height; ++y) {
            line[static_cast<std::size_t>(y)] = data[static_cast<std::size_t>(y) * width + x];
        }
        line.resize(height);
        fft1d(line, true);
        for (int y = 0; y < height; ++y) {
            data[static_cast<std::size_t>(y) * width + x] = line[static_cast<std::size_t>(y)];
        }
        line.resize(static_cast<std::size_t>(std::max(width, height)));
    }
    for (int y = 0; y < height; ++y) {
        std::copy(data.begin() + static_cast<std::ptrdiff_t>(static_cast<std::size_t>(y) * width),
                  data.begin() + static_cast<std::ptrdiff_t>(static_cast<std::size_t>(y) * width + width),
                  line.begin());
        line.resize(width);
        fft1d(line, true);
        std::copy(line.begin(), line.end(), data.begin() + static_cast<std::ptrdiff_t>(static_cast<std::size_t>(y) * width));
        line.resize(static_cast<std::size_t>(std::max(width, height)));
    }

    float minValue = std::numeric_limits<float>::max();
    float maxValue = std::numeric_limits<float>::lowest();
    std::vector<float> response(static_cast<std::size_t>(src.width) * src.height, 0.0f);
    for (int y = 0; y < src.height; ++y) {
        for (int x = 0; x < src.width; ++x) {
            float value = std::abs(data[static_cast<std::size_t>(y) * width + x].real());
            if (!mask[static_cast<std::size_t>(y) * src.width + x]) {
                value = 0.0f;
            }
            response[static_cast<std::size_t>(y) * src.width + x] = value;
            if (mask[static_cast<std::size_t>(y) * src.width + x]) {
                minValue = std::min(minValue, value);
                maxValue = std::max(maxValue, value);
            }
        }
    }
    if (maxValue <= minValue) {
        maxValue = minValue + 1.0f;
    }

    GrayImage out{src.width, src.height, std::vector<std::uint8_t>(response.size(), 0)};
    for (std::size_t i = 0; i < response.size(); ++i) {
        const float value = (response[i] - minValue) / (maxValue - minValue) * 255.0f;
        out.pixels[i] = static_cast<std::uint8_t>(std::clamp(value, 0.0f, 255.0f));
    }
    return out;
}

static void computeGLCM(const GrayImage& image, const Component& component, float& contrast, float& energy, float& homogeneity) {
    constexpr int levels = 16;
    std::vector<float> glcm(levels * levels, 0.0f);
    std::vector<std::uint8_t> inside(static_cast<std::size_t>(image.width) * image.height, 0);
    for (int idx : component.indices) {
        inside[static_cast<std::size_t>(idx)] = 1;
    }
    float total = 0.0f;
    for (int y = component.minY; y <= component.maxY; ++y) {
        for (int x = component.minX; x < component.maxX; ++x) {
            const int idx = y * image.width + x;
            const int right = y * image.width + x + 1;
            if (!inside[idx] || !inside[right]) {
                continue;
            }
            const int a = image.at(x, y) / 16;
            const int b = image.at(x + 1, y) / 16;
            glcm[static_cast<std::size_t>(a) * levels + b] += 1.0f;
            total += 1.0f;
        }
    }
    if (total <= 0.0f) {
        contrast = 0.0f;
        energy = 0.0f;
        homogeneity = 0.0f;
        return;
    }
    contrast = 0.0f;
    energy = 0.0f;
    homogeneity = 0.0f;
    for (int i = 0; i < levels; ++i) {
        for (int j = 0; j < levels; ++j) {
            const float p = glcm[static_cast<std::size_t>(i) * levels + j] / total;
            contrast += static_cast<float>((i - j) * (i - j)) * p;
            energy += p * p;
            homogeneity += p / (1.0f + static_cast<float>(std::abs(i - j)));
        }
    }
}

static std::vector<float> distanceToMaskBoundary(const std::vector<std::uint8_t>& mask,
                                                 int width,
                                                 int height,
                                                 float spacingX,
                                                 float spacingY) {
    std::vector<float> distance(mask.size(), std::numeric_limits<float>::infinity());
    std::queue<int> q;
    const float spacing = std::max(0.001f, (spacingX + spacingY) * 0.5f);
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const int idx = y * width + x;
            if (!mask[static_cast<std::size_t>(idx)]) {
                continue;
            }
            bool boundary = x == 0 || y == 0 || x == width - 1 || y == height - 1;
            const int dx[4] = {1, 0, -1, 0};
            const int dy[4] = {0, 1, 0, -1};
            for (int k = 0; k < 4 && !boundary; ++k) {
                const int nx = x + dx[k];
                const int ny = y + dy[k];
                if (!mask[static_cast<std::size_t>(ny) * width + nx]) {
                    boundary = true;
                }
            }
            if (boundary) {
                distance[static_cast<std::size_t>(idx)] = 0.0f;
                q.push(idx);
            }
        }
    }

    const int dx[4] = {1, 0, -1, 0};
    const int dy[4] = {0, 1, 0, -1};
    while (!q.empty()) {
        const int idx = q.front();
        q.pop();
        const int x = idx % width;
        const int y = idx / width;
        const float nextDistance = distance[static_cast<std::size_t>(idx)] + spacing;
        for (int k = 0; k < 4; ++k) {
            const int nx = x + dx[k];
            const int ny = y + dy[k];
            if (nx < 0 || ny < 0 || nx >= width || ny >= height) {
                continue;
            }
            const int next = ny * width + nx;
            if (!mask[static_cast<std::size_t>(next)] || distance[static_cast<std::size_t>(next)] <= nextDistance) {
                continue;
            }
            distance[static_cast<std::size_t>(next)] = nextDistance;
            q.push(next);
        }
    }
    return distance;
}

static std::vector<Component> detectCandidates(const FloatImage& hu,
                                               const GrayImage& windowed,
                                               const GrayImage& enhanced,
                                               const std::vector<std::uint8_t>& lungMask,
                                               int z,
                                               const PipelineOptions& options,
                                               float spacingX,
                                               float spacingY) {
    std::vector<int> maskedValues;
    for (std::size_t i = 0; i < enhanced.pixels.size(); ++i) {
        if (lungMask[i]) {
            maskedValues.push_back(enhanced.pixels[i]);
        }
    }
    int threshold = 160;
    if (!maskedValues.empty()) {
        std::sort(maskedValues.begin(), maskedValues.end());
        const float percentile = std::clamp(options.candidateBandpassPercentile, 0.0f, 100.0f);
        const std::size_t last = maskedValues.size() - 1;
        const std::size_t index = static_cast<std::size_t>(
            std::lround(static_cast<float>(last) * percentile / 100.0f));
        threshold = std::max(100, maskedValues[index]);
    }

    std::vector<std::uint8_t> seed(lungMask.size(), 0);
    for (std::size_t i = 0; i < seed.size(); ++i) {
        const bool softTissue = hu.pixels[i] > options.candidateMinSeedHU
            && hu.pixels[i] < options.candidateMaxSeedHU;
        const bool bandpassBlob = enhanced.pixels[i] >= threshold;
        seed[i] = lungMask[i] && softTissue && bandpassBlob ? 1 : 0;
    }
    seed = closeMask(seed, hu.width, hu.height, 1);

    auto components = connectedComponents(seed, hu.width, hu.height);
    std::vector<Component> candidates;
    const std::vector<float> boundaryDistance = distanceToMaskBoundary(lungMask, hu.width, hu.height, spacingX, spacingY);
    const float minArea = kPi * std::pow((options.minDiameterMm * 0.5f) / std::max(0.001f, (spacingX + spacingY) * 0.5f), 2.0f) * 0.35f;
    const float maxArea = kPi * std::pow((options.maxDiameterMm * 0.5f) / std::max(0.001f, (spacingX + spacingY) * 0.5f), 2.0f) * 1.8f;

    for (const auto& pixels : components) {
        if (pixels.size() < static_cast<std::size_t>(std::max(2.0f, minArea)) || pixels.size() > static_cast<std::size_t>(std::max(minArea + 1.0f, maxArea))) {
            continue;
        }
        Component component;
        component.z = z;
        component.area = static_cast<int>(pixels.size());
        component.indices = pixels;
        component.minX = hu.width;
        component.minY = hu.height;
        component.maxX = 0;
        component.maxY = 0;
        double sumX = 0.0;
        double sumY = 0.0;
        double sumHU = 0.0;
        double sumHU2 = 0.0;
        std::vector<std::uint8_t> inside(static_cast<std::size_t>(hu.width) * hu.height, 0);
        for (int idx : pixels) {
            inside[static_cast<std::size_t>(idx)] = 1;
        }
        for (int idx : pixels) {
            const int x = idx % hu.width;
            const int y = idx / hu.width;
            component.minX = std::min(component.minX, x);
            component.minY = std::min(component.minY, y);
            component.maxX = std::max(component.maxX, x);
            component.maxY = std::max(component.maxY, y);
            sumX += x;
            sumY += y;
            const float value = hu.pixels[static_cast<std::size_t>(idx)];
            sumHU += value;
            sumHU2 += value * value;

            const int dx[4] = {1, 0, -1, 0};
            const int dy[4] = {0, 1, 0, -1};
            for (int k = 0; k < 4; ++k) {
                const int nx = x + dx[k];
                const int ny = y + dy[k];
                if (nx < 0 || ny < 0 || nx >= hu.width || ny >= hu.height || !inside[static_cast<std::size_t>(ny) * hu.width + nx]) {
                    component.perimeter += 1;
                }
            }
        }
        component.centerX = static_cast<float>(sumX / component.area);
        component.centerY = static_cast<float>(sumY / component.area);
        component.diameterMm = 2.0f * std::sqrt(static_cast<float>(component.area) * spacingX * spacingY / kPi);
        const float boxWidthMm = static_cast<float>(component.maxX - component.minX + 1) * spacingX;
        const float boxHeightMm = static_cast<float>(component.maxY - component.minY + 1) * spacingY;
        component.aspectRatio = std::max(boxWidthMm, boxHeightMm) / std::max(0.001f, std::min(boxWidthMm, boxHeightMm));
        component.minBoundaryDistanceMm = std::numeric_limits<float>::infinity();
        for (int idx : pixels) {
            component.minBoundaryDistanceMm = std::min(component.minBoundaryDistanceMm, boundaryDistance[static_cast<std::size_t>(idx)]);
        }
        if (!std::isfinite(component.minBoundaryDistanceMm)) {
            component.minBoundaryDistanceMm = 0.0f;
        }
        component.circularity = component.perimeter > 0
            ? 4.0f * kPi * static_cast<float>(component.area) / static_cast<float>(component.perimeter * component.perimeter)
            : 0.0f;
        component.meanHU = static_cast<float>(sumHU / component.area);
        const double variance = std::max(0.0, sumHU2 / component.area - static_cast<double>(component.meanHU) * component.meanHU);
        component.stdHU = static_cast<float>(std::sqrt(variance));
        computeGLCM(windowed, component, component.glcmContrast, component.glcmEnergy, component.glcmHomogeneity);

        if (component.circularity >= options.minCircularity
            && component.diameterMm >= options.minDiameterMm
            && component.diameterMm <= options.maxDiameterMm
            && component.meanHU > options.candidateMinMeanHU) {
            candidates.push_back(std::move(component));
        }
    }
    return candidates;
}

static std::vector<Nodule> groupCandidates(const std::vector<Component>& components, float spacingZ) {
    std::vector<Nodule> nodules;
    std::vector<std::uint8_t> used(components.size(), 0);
    for (std::size_t i = 0; i < components.size(); ++i) {
        if (used[i]) {
            continue;
        }
        used[i] = 1;
        std::vector<std::size_t> group{i};
        bool expanded = true;
        while (expanded) {
            expanded = false;
            for (std::size_t j = 0; j < components.size(); ++j) {
                if (used[j]) {
                    continue;
                }
                for (std::size_t g : group) {
                    const float dz = std::abs(static_cast<float>(components[j].z - components[g].z)) * spacingZ;
                    const float dx = components[j].centerX - components[g].centerX;
                    const float dy = components[j].centerY - components[g].centerY;
                    if (dz <= std::max(1.5f, spacingZ * 1.5f) && std::sqrt(dx * dx + dy * dy) <= 6.0f) {
                        used[j] = 1;
                        group.push_back(j);
                        expanded = true;
                        break;
                    }
                }
            }
        }
        Nodule nodule;
        float weightSum = 0.0f;
        for (std::size_t index : group) {
            const Component& c = components[index];
            const float weight = static_cast<float>(c.area);
            weightSum += weight;
            nodule.centerX += c.centerX * weight;
            nodule.centerY += c.centerY * weight;
            nodule.centerZ += static_cast<float>(c.z) * weight;
            nodule.diameterMm = std::max(nodule.diameterMm, c.diameterMm);
            nodule.circularity += c.circularity;
            nodule.meanHU += c.meanHU;
            nodule.stdHU += c.stdHU;
            nodule.glcmContrast += c.glcmContrast;
            nodule.glcmEnergy += c.glcmEnergy;
            nodule.glcmHomogeneity += c.glcmHomogeneity;
            if (nodule.minBoundaryDistanceMm == 0.0f) {
                nodule.minBoundaryDistanceMm = c.minBoundaryDistanceMm;
            } else {
                nodule.minBoundaryDistanceMm = std::min(nodule.minBoundaryDistanceMm, c.minBoundaryDistanceMm);
            }
            nodule.maxAspectRatio = std::max(nodule.maxAspectRatio, c.aspectRatio);
        }
        if (weightSum > 0.0f) {
            nodule.centerX /= weightSum;
            nodule.centerY /= weightSum;
            nodule.centerZ /= weightSum;
        }
        const float count = static_cast<float>(group.size());
        nodule.circularity /= count;
        nodule.meanHU /= count;
        nodule.stdHU /= count;
        nodule.glcmContrast /= count;
        nodule.glcmEnergy /= count;
        nodule.glcmHomogeneity /= count;
        nodule.sliceCount = static_cast<int>(group.size());
        nodules.push_back(nodule);
    }
    std::sort(nodules.begin(), nodules.end(), [](const Nodule& a, const Nodule& b) {
        return a.diameterMm > b.diameterMm;
    });
    return nodules;
}

static RGB pseudoColor(std::uint8_t value) {
    const float t = value / 255.0f;
    RGB out;
    if (t < 0.33f) {
        const float u = t / 0.33f;
        out = {0, static_cast<std::uint8_t>(80 + 120 * u), static_cast<std::uint8_t>(160 + 80 * u)};
    } else if (t < 0.66f) {
        const float u = (t - 0.33f) / 0.33f;
        out = {static_cast<std::uint8_t>(30 + 220 * u), static_cast<std::uint8_t>(220 - 40 * u), static_cast<std::uint8_t>(220 - 200 * u)};
    } else {
        const float u = (t - 0.66f) / 0.34f;
        out = {255, static_cast<std::uint8_t>(180 - 150 * u), 0};
    }
    return out;
}

static RGBImage overlaySlice(const GrayImage& base,
                             const std::vector<std::uint8_t>& mask,
                             const std::vector<Nodule>& nodules,
                             int z) {
    RGBImage out{base.width, base.height, std::vector<RGB>(base.pixels.size())};
    for (std::size_t i = 0; i < base.pixels.size(); ++i) {
        out.pixels[i] = {base.pixels[i], base.pixels[i], base.pixels[i]};
    }
    for (int y = 1; y < base.height - 1; ++y) {
        for (int x = 1; x < base.width - 1; ++x) {
            const int idx = y * base.width + x;
            if (!mask[static_cast<std::size_t>(idx)]) {
                continue;
            }
            bool boundary = false;
            const int dx[4] = {1, 0, -1, 0};
            const int dy[4] = {0, 1, 0, -1};
            for (int k = 0; k < 4; ++k) {
                const int next = (y + dy[k]) * base.width + x + dx[k];
                if (!mask[static_cast<std::size_t>(next)]) {
                    boundary = true;
                }
            }
            if (boundary) {
                out.at(x, y) = {0, 230, 80};
            }
        }
    }
    for (const Nodule& nodule : nodules) {
        if (std::abs(nodule.centerZ - static_cast<float>(z)) > std::max(1.0f, nodule.sliceCount * 0.6f)) {
            continue;
        }
        const int cx = static_cast<int>(std::lround(nodule.centerX));
        const int cy = static_cast<int>(std::lround(nodule.centerY));
        const int radius = std::max(3, static_cast<int>(std::lround(nodule.diameterMm * 0.55f)));
        for (int a = 0; a < 360; ++a) {
            const float rad = static_cast<float>(a) * kPi / 180.0f;
            const int x = cx + static_cast<int>(std::lround(std::cos(rad) * radius));
            const int y = cy + static_cast<int>(std::lround(std::sin(rad) * radius));
            if (x >= 0 && y >= 0 && x < out.width && y < out.height) {
                out.at(x, y) = {255, 40, 40};
            }
        }
    }
    return out;
}

static RGBImage computeMIP(const Volume& volume, float wl, float ww) {
    GrayImage mip{volume.width, volume.height, std::vector<std::uint8_t>(static_cast<std::size_t>(volume.width) * volume.height)};
    const float low = wl - ww * 0.5f;
    for (int y = 0; y < volume.height; ++y) {
        for (int x = 0; x < volume.width; ++x) {
            float maxHU = volume.at(x, y, 0);
            for (int z = 1; z < volume.depth; ++z) {
                maxHU = std::max(maxHU, volume.at(x, y, z));
            }
            const float value = std::clamp((maxHU - low) / ww * 255.0f, 0.0f, 255.0f);
            mip.at(x, y) = static_cast<std::uint8_t>(std::lround(value));
        }
    }
    RGBImage color{volume.width, volume.height, std::vector<RGB>(mip.pixels.size())};
    for (std::size_t i = 0; i < mip.pixels.size(); ++i) {
        color.pixels[i] = pseudoColor(mip.pixels[i]);
    }
    return color;
}

static void writeMeta(const fs::path& outDir, const Volume& volume, const PipelineOptions& options) {
    std::ofstream meta(outDir / "meta.txt");
    meta << "width " << volume.width << "\n";
    meta << "height " << volume.height << "\n";
    meta << "slices " << volume.depth << "\n";
    meta << "spacing_x " << volume.spacingX << "\n";
    meta << "spacing_y " << volume.spacingY << "\n";
    meta << "spacing_z " << volume.spacingZ << "\n";
    meta << "window_level " << options.windowLevel << "\n";
    meta << "window_width " << options.windowWidth << "\n";
    meta << "bandpass_sigma_low " << options.sigmaLow << "\n";
    meta << "bandpass_sigma_high " << options.sigmaHigh << "\n";
    meta << "candidate_bandpass_percentile " << options.candidateBandpassPercentile << "\n";
    meta << "candidate_min_seed_hu " << options.candidateMinSeedHU << "\n";
    meta << "candidate_max_seed_hu " << options.candidateMaxSeedHU << "\n";
    meta << "candidate_min_mean_hu " << options.candidateMinMeanHU << "\n";
    meta << "min_circularity " << options.minCircularity << "\n";
    meta << "final_min_mean_hu " << options.finalMinMeanHU << "\n";
    meta << "final_max_mean_hu " << options.finalMaxMeanHU << "\n";
    meta << "final_min_std_hu " << options.finalMinStdHU << "\n";
    meta << "final_max_std_hu " << options.finalMaxStdHU << "\n";
    meta << "final_max_glcm_contrast " << options.finalMaxGLCMContrast << "\n";
    meta << "final_min_glcm_homogeneity " << options.finalMinGLCMHomogeneity << "\n";
    meta << "final_min_boundary_distance_mm " << options.finalMinBoundaryDistanceMm << "\n";
    meta << "final_max_aspect_ratio " << options.finalMaxAspectRatio << "\n";
    meta << "final_min_slice_count " << options.finalMinSliceCount << "\n";
    meta << "final_min_slice_count_exception_diameter_mm "
         << options.finalMinSliceCountExceptionDiameterMm << "\n";
    meta << "final_max_slice_count " << options.finalMaxSliceCount << "\n";
    meta << "max_final_candidates " << options.maxFinalCandidates << "\n";
    meta << "rank_diameter_reward_cap_mm " << options.rankDiameterRewardCapMm << "\n";
    meta << "rank_slice_count_penalty " << options.rankSliceCountPenalty << "\n";
    meta << "rank_score_policy "
         << (options.useLearnedRankScore ? "learned_grid0256_d1c1m1s1x0h2z0_mt280" : "legacy") << "\n";
    meta << "learned_score_quantile " << options.learnedScoreQuantile << "\n";
    meta << "learned_top_k " << options.learnedTopK << "\n";
}

static void writeFeatures(const fs::path& outDir, const std::vector<Nodule>& nodules) {
    std::ofstream csv(outDir / "features.csv");
    csv << "id,center_x,center_y,center_z,diameter_mm,circularity,mean_hu,std_hu,glcm_contrast,glcm_energy,glcm_homogeneity,min_boundary_distance_mm,max_aspect_ratio,slice_count\n";
    for (std::size_t i = 0; i < nodules.size(); ++i) {
        const Nodule& n = nodules[i];
        csv << i + 1 << ","
            << std::fixed << std::setprecision(3)
            << n.centerX << "," << n.centerY << "," << n.centerZ << ","
            << n.diameterMm << "," << n.circularity << ","
            << n.meanHU << "," << n.stdHU << ","
            << n.glcmContrast << "," << n.glcmEnergy << "," << n.glcmHomogeneity << ","
            << n.minBoundaryDistanceMm << "," << n.maxAspectRatio << ","
            << n.sliceCount << "\n";
    }
}

static std::string sliceName(int z, const std::string& suffix) {
    std::ostringstream oss;
    oss << "slice_" << std::setw(3) << std::setfill('0') << z << suffix;
    return oss.str();
}

static float legacyNoduleRankScore(const Nodule& nodule, const PipelineOptions& options) {
    const float diameterReward = options.rankDiameterRewardCapMm > 0.0f
        ? std::min(nodule.diameterMm, options.rankDiameterRewardCapMm)
        : nodule.diameterMm;
    const float singleSlicePenalty = nodule.sliceCount <= 1 ? options.rankSliceCountPenalty : 0.0f;
    return 2.0f * diameterReward
         + 3.0f * nodule.glcmHomogeneity
         - 0.02f * nodule.stdHU
         - 0.2f * nodule.glcmContrast
         - singleSlicePenalty;
}

static float learnedNoduleRankScore(const Nodule& nodule) {
    const float diameter = std::clamp(nodule.diameterMm, 0.0f, 20.0f) / 20.0f;
    const float circularity = std::clamp(nodule.circularity, 0.0f, 1.0f);
    const float meanCloseness = 1.0f - std::min(std::abs(nodule.meanHU - (-280.0f)) / 320.0f, 1.0f);
    const float stdHU = std::clamp(nodule.stdHU, 0.0f, 260.0f) / 260.0f;
    const float homogeneity = std::clamp(nodule.glcmHomogeneity, 0.0f, 1.0f);
    return diameter + circularity + meanCloseness - stdHU + 2.0f * homogeneity;
}

static std::vector<Nodule> filterFinalNodules(std::vector<Nodule> nodules,
                                              const PipelineOptions& options) {
    nodules.erase(std::remove_if(nodules.begin(), nodules.end(), [&](const Nodule& nodule) {
        const bool tooFewSlices = options.finalMinSliceCount > 0
            && nodule.sliceCount < options.finalMinSliceCount
            && (options.finalMinSliceCountExceptionDiameterMm <= 0.0f
                || nodule.diameterMm < options.finalMinSliceCountExceptionDiameterMm);
        const bool tooCloseToBoundary = options.finalMinBoundaryDistanceMm > 0.0f
            && nodule.minBoundaryDistanceMm < options.finalMinBoundaryDistanceMm;
        return nodule.meanHU < options.finalMinMeanHU
            || nodule.meanHU > options.finalMaxMeanHU
            || nodule.stdHU < options.finalMinStdHU
            || nodule.stdHU > options.finalMaxStdHU
            || nodule.glcmContrast > options.finalMaxGLCMContrast
            || nodule.glcmHomogeneity < options.finalMinGLCMHomogeneity
            || tooCloseToBoundary
            || nodule.maxAspectRatio > options.finalMaxAspectRatio
            || tooFewSlices
            || nodule.sliceCount > options.finalMaxSliceCount;
    }), nodules.end());

    std::sort(nodules.begin(), nodules.end(), [&](const Nodule& a, const Nodule& b) {
        return legacyNoduleRankScore(a, options) > legacyNoduleRankScore(b, options);
    });
    if (options.maxFinalCandidates > 0 && nodules.size() > static_cast<std::size_t>(options.maxFinalCandidates)) {
        nodules.resize(static_cast<std::size_t>(options.maxFinalCandidates));
    }

    if (!options.useLearnedRankScore) {
        return nodules;
    }

    std::stable_sort(nodules.begin(), nodules.end(), [](const Nodule& a, const Nodule& b) {
        return learnedNoduleRankScore(a) > learnedNoduleRankScore(b);
    });

    if (options.learnedScoreQuantile >= 0.0f && !nodules.empty()) {
        std::vector<float> scores;
        scores.reserve(nodules.size());
        for (const Nodule& nodule : nodules) {
            scores.push_back(learnedNoduleRankScore(nodule));
        }
        std::sort(scores.begin(), scores.end());
        const float quantile = std::clamp(options.learnedScoreQuantile, 0.0f, 1.0f);
        const std::size_t index = std::min(
            scores.size() - 1,
            static_cast<std::size_t>(std::floor(static_cast<float>(scores.size() - 1) * quantile)));
        const float threshold = scores[index];
        nodules.erase(std::remove_if(nodules.begin(), nodules.end(), [&](const Nodule& nodule) {
            return learnedNoduleRankScore(nodule) < threshold;
        }), nodules.end());
    }

    if (options.learnedTopK > 0 && nodules.size() > static_cast<std::size_t>(options.learnedTopK)) {
        nodules.resize(static_cast<std::size_t>(options.learnedTopK));
    }
    return nodules;
}

} // namespace

MHDHeader parseMHD(const std::string& mhdPath) {
    std::ifstream file(mhdPath);
    if (!file) {
        throw std::runtime_error("cannot open mhd: " + mhdPath);
    }
    MHDHeader header;
    std::string line;
    while (std::getline(file, line)) {
        const auto comment = line.find('#');
        if (comment != std::string::npos) {
            line = line.substr(0, comment);
        }
        const auto eq = line.find('=');
        if (eq == std::string::npos) {
            continue;
        }
        const std::string key = trim(line.substr(0, eq));
        const std::string value = trim(line.substr(eq + 1));
        const auto words = splitWords(value);
        if (key == "NDims" && !words.empty()) {
            header.ndims = std::stoi(words[0]);
        } else if (key == "DimSize" && words.size() >= 3) {
            header.width = std::stoi(words[0]);
            header.height = std::stoi(words[1]);
            header.depth = std::stoi(words[2]);
        } else if (key == "ElementSpacing" && words.size() >= 3) {
            header.spacingX = std::stof(words[0]);
            header.spacingY = std::stof(words[1]);
            header.spacingZ = std::stof(words[2]);
        } else if (key == "ElementType") {
            header.elementType = value;
        } else if (key == "ElementDataFile") {
            header.elementDataFile = value;
        } else if (key == "BinaryData") {
            header.binaryData = value == "True" || value == "true" || value == "1";
        } else if (key == "ElementByteOrderMSB") {
            header.msb = value == "True" || value == "true" || value == "1";
        }
    }
    if (header.ndims != 3 || header.width <= 0 || header.height <= 0 || header.depth <= 0 || header.elementDataFile.empty()) {
        throw std::runtime_error("invalid or unsupported mhd header: " + mhdPath);
    }
    return header;
}

Volume loadVolumeFromMHD(const std::string& mhdPath) {
    const MHDHeader header = parseMHD(mhdPath);
    if (!header.binaryData) {
        throw std::runtime_error("only BinaryData=True is supported");
    }
    if (header.msb) {
        throw std::runtime_error("big-endian raw files are not supported in this implementation");
    }
    const fs::path rawPath = rawPathFor(fs::path(mhdPath), header.elementDataFile);
    std::ifstream raw(rawPath, std::ios::binary);
    if (!raw) {
        throw std::runtime_error("cannot open raw: " + rawPath.string());
    }
    int bytesPerVoxel = 0;
    if (header.elementType == "MET_SHORT" || header.elementType == "MET_USHORT") {
        bytesPerVoxel = 2;
    } else if (header.elementType == "MET_FLOAT") {
        bytesPerVoxel = 4;
    } else if (header.elementType == "MET_UCHAR" || header.elementType == "MET_CHAR") {
        bytesPerVoxel = 1;
    } else {
        throw std::runtime_error("unsupported ElementType: " + header.elementType);
    }
    const std::size_t voxelCount = static_cast<std::size_t>(header.width) * header.height * header.depth;
    std::vector<char> buffer(voxelCount * static_cast<std::size_t>(bytesPerVoxel));
    raw.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
    if (raw.gcount() != static_cast<std::streamsize>(buffer.size())) {
        throw std::runtime_error("raw file is smaller than DimSize requires");
    }

    Volume volume;
    volume.width = header.width;
    volume.height = header.height;
    volume.depth = header.depth;
    volume.spacingX = header.spacingX;
    volume.spacingY = header.spacingY;
    volume.spacingZ = header.spacingZ;
    volume.hu.resize(voxelCount);
    for (std::size_t i = 0; i < voxelCount; ++i) {
        const char* p = buffer.data() + i * static_cast<std::size_t>(bytesPerVoxel);
        if (header.elementType == "MET_SHORT") {
            volume.hu[i] = static_cast<float>(static_cast<std::int16_t>(readU16LE(p)));
        } else if (header.elementType == "MET_USHORT") {
            volume.hu[i] = static_cast<float>(readU16LE(p));
        } else if (header.elementType == "MET_UCHAR") {
            volume.hu[i] = static_cast<float>(static_cast<unsigned char>(*p));
        } else if (header.elementType == "MET_CHAR") {
            volume.hu[i] = static_cast<float>(static_cast<signed char>(*p));
        } else {
            const std::uint32_t bits = readU32LE(p);
            float value = 0.0f;
            static_assert(sizeof(float) == sizeof(std::uint32_t), "float must be 32-bit");
            std::memcpy(&value, &bits, sizeof(float));
            volume.hu[i] = value;
        }
    }
    return volume;
}

PipelineResult runPipeline(const PipelineOptions& options) {
    if (options.mhdPath.empty() || options.outputDir.empty()) {
        throw std::runtime_error("mhdPath and outputDir are required");
    }
    fs::create_directories(options.outputDir);

    PipelineResult result;
    result.volume = loadVolumeFromMHD(options.mhdPath);
    const Volume& volume = result.volume;
    writeMeta(options.outputDir, volume, options);

    std::vector<GrayImage> windowedSlices;
    std::vector<GrayImage> enhancedSlices;
    std::vector<std::vector<std::uint8_t>> masks;
    std::vector<Component> allComponents;
    windowedSlices.reserve(static_cast<std::size_t>(volume.depth));
    enhancedSlices.reserve(static_cast<std::size_t>(volume.depth));
    masks.reserve(static_cast<std::size_t>(volume.depth));

    for (int z = 0; z < volume.depth; ++z) {
        const FloatImage hu = huSlice(volume, z);
        GrayImage windowed = windowSlice(volume, z, options.windowLevel, options.windowWidth);
        std::vector<std::uint8_t> mask = segmentLungSlice(hu);
        result.stage1MaskPixels += static_cast<int>(std::count(mask.begin(), mask.end(), 1));
        GrayImage enhanced = bandPassEnhance(hu, mask, options.sigmaLow, options.sigmaHigh);
        auto components = detectCandidates(hu, windowed, enhanced, mask, z, options, volume.spacingX, volume.spacingY);
        result.stage3Candidates += static_cast<int>(components.size());
        allComponents.insert(allComponents.end(), components.begin(), components.end());

        windowedSlices.push_back(std::move(windowed));
        enhancedSlices.push_back(std::move(enhanced));
        masks.push_back(std::move(mask));
    }

    result.nodules = filterFinalNodules(groupCandidates(allComponents, volume.spacingZ), options);
    writeFeatures(options.outputDir, result.nodules);
    writePPM(fs::path(options.outputDir) / "mip.ppm", computeMIP(volume, options.windowLevel, options.windowWidth));

    if (options.writeDebugImages) {
        for (int z = 0; z < volume.depth; ++z) {
            writePGM(fs::path(options.outputDir) / sliceName(z, "_window.pgm"), windowedSlices[static_cast<std::size_t>(z)]);
            writePGM(fs::path(options.outputDir) / sliceName(z, "_mask.pgm"), maskToGray(masks[static_cast<std::size_t>(z)], volume.width, volume.height));
            writePGM(fs::path(options.outputDir) / sliceName(z, "_bandpass.pgm"), enhancedSlices[static_cast<std::size_t>(z)]);
            writePPM(fs::path(options.outputDir) / sliceName(z, "_overlay.ppm"),
                     overlaySlice(windowedSlices[static_cast<std::size_t>(z)], masks[static_cast<std::size_t>(z)], result.nodules, z));
        }
    }

    return result;
}

} // namespace lung
