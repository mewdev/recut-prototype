import json
import subprocess
import sys

with open("edit.json") as f:
    edit = json.load(f)

input_file = sys.argv[1] if len(sys.argv) > 1 else "billie_jean.mp3"
output_file = "podcast_intro.mp3"

import os
FFMPEG = os.path.join(os.path.dirname(sys.executable), "ffmpeg")

cmd = [
    FFMPEG, "-y",
    "-i", input_file,
    "-ss", str(edit["keep_from"]),
    "-to", str(edit["keep_to"]),
    "-af", f"afade=t=out:st={edit['fade_out_start']}:d={edit['fade_out_duration']}",
    output_file
]

print("Running:", " ".join(cmd))
subprocess.run(cmd, check=True)
print(f"\n✅ Saved to {output_file}")
