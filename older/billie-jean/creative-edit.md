Here is a JSONMusicMap of Billie Jean by Michael Jackson:

Found in same folder as this file music.map.full.json, output as creatite-edit.json

I want to create a creative edit for a DJ intro drop. The edit should:

- Start from the very beginning (the iconic bassline intro)
- Build tension by repeating the intro section one extra time before moving forward
- Cut sharply into the most energetic section available
- End abruptly on a strong downbeat — no fade, hard stop
- Total length: between 45-75 seconds
- Must feel intentional and musical, not random

Think like a DJ, not an editor. Repetition and tension are good.
Anticipate where a crowd would react.

Return ONLY valid JSON, no prose, no markdown:
{
  "ops": [
    { "type": "keep", "from": <seconds>, "to": <seconds> },
    { "type": "keep", "from": <seconds>, "to": <seconds> },
    { "type": "keep", "from": <seconds>, "to": <seconds> }
  ],
  "total_duration": <seconds>,
  "hard_stop": true,
  "reasoning": "<two sentences max, think like a DJ>"
}

Note: multiple "keep" ops will be concatenated in order.
The final op ends on the nearest downbeat — calculate from BPM.