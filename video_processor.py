from moviepy import (
    VideoFileClip,
    ImageClip,
    CompositeVideoClip
)

INPUT_VIDEO = "input.mp4"
OUTPUT_VIDEO = "output.mp4"
LOGO_IMAGE = "meatball.png"

# Load video
video = VideoFileClip(INPUT_VIDEO)

# Create logo clip
logo = (
    ImageClip(LOGO_IMAGE)
    .resized(width=120)          # Adjust logo size
    .with_opacity(0.65)          # Transparency
    .with_duration(video.duration)
    .with_position(("right", "bottom"))
)

# Combine video + logo
final = CompositeVideoClip([
    video,
    logo
])

# Export final video
final.write_videofile(
    OUTPUT_VIDEO,
    codec="libx264",
    audio_codec="aac",
    fps=video.fps
)

# Cleanup
video.close()
final.close()