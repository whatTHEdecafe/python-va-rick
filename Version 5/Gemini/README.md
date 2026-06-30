# Version 5 - Video Support via Gemini File API

**Latest version** featuring video file processing in addition to batch image analysis.

---

## 🎯 Key Improvements

### Video Support Added
- **📹 Video Processing**: Supports .mp4, .mov, .avi, .mkv, .webm, .flv, .wmv, .m4v
- **🎬 Mixed Media**: Upload any combination of images and videos
- **🔍 Auto Detection**: Automatically detects file types (image vs video)
- **Single API Call**: Processes all media files in one batch
- **No Duplicates**: Smart deduplication across video frames and images

### Technical Upgrades
- **Model**: Gemini 2.5 Flash (latest)
- **File API**: Handles both images and videos
- **Video Processing**: Automatic wait for video processing completion
- **Same Speed**: Images process at Version 4 speeds, videos add ~15-30s per video

---

## 📊 Supported Formats

| Type | Formats |
|------|---------|
| **Images** | .jpg, .jpeg, .png, .gif, .bmp, .webp, .tiff, .heic, .heif (iPhone) |
| **Videos** | .mp4, .mov, .avi, .mkv, .webm, .flv, .wmv, .m4v |

---

## 🏗️ Architecture

```
Input Files (Images/Videos) → File API Upload → Video Processing Wait → 
Batch Analysis (Single Call) → Item Detection → JSON Database → Logistics → Quote
```

### Workflow
1. **Upload**: All images and videos uploaded to Gemini via File API
2. **Process**: Videos automatically processed (frame extraction)
3. **Analyze**: Single API call processes all media together
4. **Parse**: Extract items with size hints (e.g., "queen bed", "large sofa")
5. **Calculate**: JSON database provides volume/weight/time data
6. **Optimize**: Vehicle selection and pricing calculation

---

## 💻 Usage

### Basic Example
```bash
cd "Version 5/Gemini"
python vision-agent.py
```

### Interactive Prompts
1. **Media Files**: Enter paths (comma-separated)
   ```
   bedroom.jpg, living_room_tour.mp4, kitchen.jpg
   ```

2. **Pickup Access**: `ground` / `stairs` / `elevator`
3. **Floors**: Number of floors (if applicable)
4. **Dropoff Access**: `ground` / `stairs` / `elevator`
5. **Dropoff Floors**: Number of floors
6. **Travel Time**: Minutes between locations

### Output
- Detected items with quantities and locations
- Volume, weight, and time calculations
- Optimal vehicle recommendations
- Complete pricing breakdown
- Exportable JSON results with media metrics

---

## 📈 Performance Metrics

**Typical 2 Images + 1 Video (30s) Analysis:**
- Image Upload: ~1 second per image
- Video Upload: ~5-10 seconds per video
- Video Processing: ~5-15 seconds per video
- API Analysis: ~3-5 seconds
- Calculation: <1 second
- **Total**: ~20-40 seconds

**API Call Tracking:**
```python
metrics = {
    "images_processed": 2,
    "videos_processed": 1,
    "file_analysis_time": 25.3,
    "calculation_time": 0.3,
    "api_calls": 1,  # Always 1 regardless of file count
    "total_time": 25.6
}
```

---

## 📦 Data Dependencies

### Required Files
- `../../Data/moving_items_logistics_v2.json` - 80+ item database
- `../../Data/moving_calculation_rules.json` - Calculation rules

### Environment Variables
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

---

## 🚀 Key Features

- **Video Support**: Process video walkthroughs of rooms/properties
- **Mixed Media**: Combine images and videos in single request
- **Batch Processing**: Multiple files in single API call
- **Smart Detection**: Identifies items with size classification (S/M/L)
- **No Double-Counting**: Handles same items across multiple files/frames
- **Detailed Breakdown**: Per-item time, volume, weight analysis
- **Multi-Vehicle Support**: Optimal truck combination for large moves
- **Access Factors**: Stairs, elevators, floor count adjustments

---

## 🔄 Version Comparison

### vs Version 4
- ✅ Video file support (MP4, MOV, AVI, etc.)
- ✅ Mixed media uploads (images + videos)
- ✅ Better coverage for large spaces
- ✅ Same performance for images
- ✅ All Version 4 features retained

### Best Use Cases
- **Images Only**: Small apartments, individual rooms, quick quotes
- **Videos Only**: Large properties, virtual tours, detailed walkthroughs
- **Mixed**: Overview videos + detailed images of specific items

---

## 📝 Video Best Practices

- **Duration**: 30-60 seconds per room optimal
- **Resolution**: 720p or 1080p recommended
- **Format**: MP4 with H.264 codec works best
- **File Size**: Keep under 100MB for faster processing
- **Quality**: Steady camera, good lighting, slow panning

---

## ⚠️ Notes

- Videos take longer to process than images (~15-30s per video)
- Recommended max video size: 100MB (limit: 2GB)
- All files auto-cleanup after processing
- Works best with clear, well-lit media
- Single API call for all files regardless of type
