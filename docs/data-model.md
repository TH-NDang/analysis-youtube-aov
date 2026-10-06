# Data model

## Game video

```json
{
  "video_id": "...",
  "domain_score": 0.94,
  "primary_type": "skin_showcase",
  "content_types": {"skin_showcase": 0.9},
  "heroes": [{"id": "tulen", "name": "Tulen", "confidence": 0.88, "evidence": []}],
  "skins": [{"id": "tulen--...", "name": "...", "hero": "Tulen", "confidence": 0.93}],
  "lore_segments": []
}
```

## eSports video

```json
{
  "video_id": "...",
  "domain_score": 0.98,
  "primary_type": "highlight",
  "tournaments": [{"id": "dtdv", "name": "Đấu Trường Danh Vọng", "confidence": 0.88}],
  "teams": [{"id": "saigon-phantom", "name": "Saigon Phantom", "confidence": 0.88}],
  "season": "Mùa Đông 2026",
  "game_number": 3,
  "highlight_segments": [{"title": "...", "start": 1234.0, "end": 1288.0}]
}
```

## Frontend usage

- Hero page: đọc `game/hero-video-index.json[heroSlug].videos`.
- Skin page: đọc `game/skin-video-index.json[skinId].videos`.
- Lore/story area: đọc `game/lore-video-index.json`.
- Tournament page: đọc `esports/tournament-video-index.json[tournamentId].videos`.
- Team page: đọc `esports/team-video-index.json[teamId].videos`.
- Highlight feed: stream `esports/highlights.jsonl`.
- Match discovery: stream `esports/matches.jsonl`.

Không coi `channel_handle` là nhãn nội dung. Domain được xác định từ title/tags/description/chapters + entity evidence.
