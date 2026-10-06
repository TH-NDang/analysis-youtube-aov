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
    ├── candidate-players.json
    └── candidate-teams.json
```

## Chạy

Pipeline full hiện chạy qua bridge workflow **Analyze YouTube AOV via analysis repo** ở repo nguồn `TH-NDang/bao-tang-lien-quan`.

Lý do: release dataset nguồn không cho `GITHUB_TOKEN` của repository khác đọc chéo repo. Bridge workflow chỉ làm nhiệm vụ truy cập dữ liệu; toàn bộ classifier/config/schema vẫn lấy từ repository `analysis-youtube-aov`.

Workflow:
1. repo nguồn tải release dataset,
2. clone đúng revision của `analysis-youtube-aov`,
3. đồng bộ hero/skin từ trang học viện Garena (best-effort),
4. chạy classifier + entity extraction,
5. build report + validate,
6. upload artifact `analysis-youtube-aov`.

Repo phân tích có workflow riêng để kiểm tra syntax/config mà không cần tải dataset lớn.

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

## Kết quả hiện tại

Snapshot mới nhất được lưu tại `results/latest/`. Full JSONL/index nằm trong GitHub Actions artifact vì không nên commit hàng chục MB dữ liệu sinh ra vào git.

Bản phân tích hiện tại hỗ trợ trực tiếp:
- trang tướng: video spotlight/guide/gameplay/eSports moment
- trang skin: showcase/trailer và candidate skin cần review
- trang lore: lore/cinematic theo tướng
- trang giải: tournament + season + video liên quan
- trang đội: team + video liên quan
- feed eSports: match, highlight, interview, roster, livestream, recap
- quality queues: unclassified, low-confidence, candidate player/team/skin

