Here is a JSONMusicMap of a song. I need to shorten it to 60 seconds
for a podcast intro. It should end at a natural section boundary,
not mid-phrase.

JSON map can be found in the same directory as this prompt

Return ONLY valid JSON, no prose, no markdown:
{
  "keep_from": <seconds>,
  "keep_to": <seconds>,
  "fade_out_start": <seconds>,
  "fade_out_duration": <seconds>,
  "reasoning": "<one sentence>"
}

