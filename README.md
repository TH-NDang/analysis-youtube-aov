# analysis-youtube-aov

Pipeline phân tích dataset YouTube Liên Quân/Arena of Valor để phục vụ **hai khu vực độc lập của website**:

1. **Game / Liên Quân Wiki**
   - Video liên quan đến tướng
   - Video trang phục / skin showcase / trailer
   - Cốt truyện / lore / cinematic
   - Patch / cập nhật
   - Guide / gameplay / event
   - Tạo index `hero -> related videos`, `skin -> related videos`, `lore -> related videos`

2. **eSports**
   - Giải đấu / mùa giải
   - Trận / game / livestream
   - Highlight / pha hay / short moment
   - Team / player / interview / recap
   - Tạo index `tournament -> videos`, `team -> videos`, và danh sách highlight

Nguồn YouTube hiện tại: release `youtube-deep-2026-10-01` từ repo
`TH-NDang/bao-tang-lien-quan`, gồm **16.988 video deep-enriched**.

## Nguyên tắc

Pipeline ưu tiên deterministic rules + entity dictionaries trước:

- mọi relation có `confidence`
- giữ `evidence` cho biết match từ `title`, `tags`, `description`, chapter...
- một video có thể thuộc đồng thời `game` và `esports`
- không ép channel eSports = nội dung eSports
- dữ liệu confidence thấp được đẩy vào `quality/` để review
- transcript/CV/LLM là enrichment tùy chọn ở phase sau

## Output

```text
output/
├── summary.json
├── report.md
├── game/
│   ├── videos.jsonl
│   ├── hero-video-index.json
│   ├── skin-video-index.json
│   ├── lore-video-index.json
│   ├── patches.jsonl
│   └── content-type-counts.json
├── esports/
│   ├── videos.jsonl
│   ├── highlights.jsonl
│   ├── matches.jsonl
│   ├── tournaments.json
│   ├── tournament-video-index.json
│   ├── teams.json
│   └── team-video-index.json
└── quality/
    ├── unclassified.jsonl
    ├── low-confidence.jsonl
    ├── candidate-skins.json
    └── candidate-players.json
```

## Chạy

GitHub Actions: **Analyze YouTube AOV dataset**.

Workflow:
1. tải release dataset nguồn,
2. đồng bộ hero/skin từ trang học viện Garena (best-effort),
3. chạy classifier + entity extraction,
4. build report,
5. upload artifact `analysis-youtube-aov`.

## Confidence

- `>= 0.85`: có thể dùng tự động trên website
- `0.65 - 0.84`: dùng được nhưng nên cho phép review
- `< 0.65`: giữ ở candidate / quality queue

## Phase tiếp theo

- tải caption text và map transcript timestamp
- phát hiện segment `draft/game/result/highlight`
- CV/OCR để xác nhận HUD, team score, hero pick/ban
- dictionary player/team lịch sử đầy đủ
- incremental analysis chỉ cho video mới
