from moviepy import VideoFileClip, TextClip, CompositeVideoClip

INPUT_VIDEO = "input.mp4"
OUTPUT_VIDEO = "output.mp4"

video = VideoFileClip(INPUT_VIDEO)

text = TextClip(
    text="Meatball The Frenchie",
    font_size=38,
    color="white",
    stroke_color="black",
    stroke_width=2,
).with_duration(video.duration)

# Put text higher on the screen: 0.72 = 72% down from the top
text_y = int(video.h * 0.72)

text = text.with_position(("center", text_y))

final = CompositeVideoClip([video, text])

final.write_videofile(
    OUTPUT_VIDEO,
    codec="libx264",
    audio_codec="aac",
    fps=video.fps
)

video.close()
final.close()