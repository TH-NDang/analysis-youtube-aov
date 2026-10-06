#!/usr/bin/env python3
import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


FIELD_WEIGHTS = {
    "title": 0.78,
    "tags": 0.52,
    "chapters": 0.38,
    "description": 0.22,
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def iter_jsonl(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def norm(text):
    if text is None:
        return ""
    text = str(text).replace("’", "'").replace("‘", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("đ", "d")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def slugify(text):
    return norm(text).replace(" ", "-")


def phrase_in(haystack, needle):
    h = f" {norm(haystack)} "
    n = norm(needle)
    return bool(n) and f" {n} " in h


def text_fields(row):
    chapters = row.get("chapters") or []
    chapter_text = " ".join(
        str(x.get("title") or "") for x in chapters if isinstance(x, dict)
    )
    tags = " ".join(str(x) for x in (row.get("tags") or []))
    return {
        "title": row.get("title") or "",
        "tags": tags,
        "description": row.get("description") or "",
        "chapters": chapter_text,
    }


def evidence_for_aliases(fields, aliases, *, description_ok=True, normalized_fields=None):
    evidence = []
    best = 0.0
    normalized_fields = normalized_fields or {k: norm(v) for k, v in fields.items()}
    normalized_aliases = [(alias, norm(alias)) for alias in aliases if norm(alias)]
    for field in fields:
        if field == "description" and not description_ok:
            continue
        ntext = normalized_fields.get(field, "")
        padded = f" {ntext} "
        for alias, nalias in normalized_aliases:
            if f" {nalias} " in padded:
                weight = FIELD_WEIGHTS[field]
                best = max(best, weight)
                evidence.append({"field": field, "matched": alias, "weight": weight})
                break
    if len({e["field"] for e in evidence}) >= 2:
        best = min(0.99, best + 0.10)
    return best, evidence


def keyword_score(fields, keywords, normalized_fields=None):
    evidence = []
    best = 0.0
    normalized_fields = normalized_fields or {k: norm(v) for k, v in fields.items()}
    normalized_keywords = [(kw, norm(kw)) for kw in keywords if norm(kw)]
    for field in fields:
        nt = normalized_fields.get(field, "")
        for kw, nkw in normalized_keywords:
            if nkw and (f" {nkw} " in f" {nt} " or nkw in nt):
                weight = {
                    "title": 0.90,
                    "tags": 0.65,
                    "chapters": 0.52,
                    "description": 0.34,
                }[field]
                best = max(best, weight)
                evidence.append({"field": field, "matched": kw, "weight": weight})
                break
    return best, evidence


def has_strong_evidence(evidence, allowed=("title", "tags", "chapters")):
    return any(item.get("field") in allowed for item in evidence)


def load_heroes(config_path, synced_path):
    cfg = read_json(config_path)
    aliases = cfg.get("aliases", {})
    rows = []

    synced = Path(synced_path)
    if synced.exists():
        data = read_json(synced)
        synced_names = [x.get("name") for x in data.get("heroes", []) if x.get("name")]
    else:
        synced_names = []

    names = []
    seen = set()
    for name in synced_names + cfg.get("heroes", []):
        key = norm(name)
        if key and key not in seen:
            seen.add(key)
            names.append(name)

    for name in names:
        all_aliases = [name] + aliases.get(name, [])
        rows.append(
            {
                "id": slugify(name),
                "name": name,
                "aliases": list(dict.fromkeys(all_aliases)),
            }
        )
    return rows


def load_skins(path):
    p = Path(path)
    if not p.exists():
        return []
    data = read_json(p)
    rows = []
    for item in data.get("skins", []):
        name = item.get("name")
        hero = item.get("hero")
        if not name or not hero:
            continue
        rows.append(
            {
                "id": f"{slugify(hero)}--{slugify(name)}",
                "name": name,
                "hero": hero,
                "aliases": [name, f"{hero} {name}"],
                "source_url": item.get("source_url"),
            }
        )
    return rows


def extract_entities(fields, normalized_fields, heroes, skins, esports):
    hero_mentions = []
    for hero in heroes:
        shortest = min(len(norm(x)) for x in hero["aliases"] if norm(x))
        description_ok = shortest >= 4 or " " in norm(hero["name"])
        score, evidence = evidence_for_aliases(
            fields,
            hero["aliases"],
            description_ok=description_ok,
            normalized_fields=normalized_fields,
        )
        if score >= 0.38 and has_strong_evidence(evidence):
            hero_mentions.append(
                {
                    "id": hero["id"],
                    "name": hero["name"],
                    "confidence": round(score, 3),
                    "evidence": evidence,
                }
            )

    skin_mentions = []
    matched_hero_names = {norm(x["name"]) for x in hero_mentions}
    for skin in skins:
        # Most official skin mentions include the hero name. Restricting to
        # already matched heroes avoids scanning ~1K skins against every long
        # description while preserving high-confidence title/tag relations.
        if norm(skin["hero"]) not in matched_hero_names:
            continue
        score, evidence = evidence_for_aliases(
            fields,
            skin["aliases"],
            description_ok=True,
            normalized_fields=normalized_fields,
        )
        if score >= 0.38 and has_strong_evidence(evidence):
            skin_mentions.append(
                {
                    "id": skin["id"],
                    "name": skin["name"],
                    "hero": skin["hero"],
                    "confidence": round(min(0.99, score + 0.08), 3),
                    "evidence": evidence,
                }
            )

    tournament_mentions = []
    for item in esports.get("tournaments", []):
        score, evidence = evidence_for_aliases(
            fields,
            [item["name"]] + item.get("aliases", []),
            normalized_fields=normalized_fields,
        )
        if score >= 0.38 and has_strong_evidence(evidence, ("title", "chapters")):
            tournament_mentions.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "confidence": round(score, 3),
                    "evidence": evidence,
                }
            )

    team_mentions = []
    for item in esports.get("teams", []):
        aliases = [item["name"]] + item.get("aliases", [])
        short = min(len(norm(x)) for x in aliases if norm(x))
        score, evidence = evidence_for_aliases(
            fields,
            aliases,
            description_ok=short >= 4,
            normalized_fields=normalized_fields,
        )
        if score >= 0.38 and has_strong_evidence(evidence, ("title", "chapters")):
            team_mentions.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "confidence": round(score, 3),
                    "evidence": evidence,
                }
            )

    return hero_mentions, skin_mentions, tournament_mentions, team_mentions


def classify_types(fields, normalized_fields, taxonomy):
    scores = {}
    evidence = {}
    for label, keywords in taxonomy.get("content_types", {}).items():
        score, ev = keyword_score(fields, keywords, normalized_fields=normalized_fields)
        if score >= 0.52 and has_strong_evidence(ev):
            scores[label] = round(score, 3)
            evidence[label] = ev
    return scores, evidence


def extract_season(title):
    patterns = [
        r"(?i)mùa\s+(xuân|đông)\s+(20\d{2})",
        r"(?i)(spring|summer|fall|autumn|winter)\s+(20\d{2})",
        r"(?i)season\s+(\d{1,2})\s*[/\- ]\s*(20\d{2})",
    ]
    for pattern in patterns:
        m = re.search(pattern, title or "")
        if m:
            return m.group(0)
    return None


def extract_game_number(title):
    patterns = [
        r"(?i)\b(?:game|ván|map)\s*#?\s*(\d{1,2})\b",
        r"(?i)\bg\s*(\d{1,2})\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, title or "")
        if m:
            return int(m.group(1))
    return None


def chapter_segments(row, keywords):
    result = []
    for ch in row.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        title = ch.get("title") or ""
        nt = norm(title)
        matched = [kw for kw in keywords if norm(kw) in nt]
        if matched:
            result.append(
                {
                    "title": title,
                    "start": ch.get("start_time"),
                    "end": ch.get("end_time"),
                    "matched_keywords": matched[:5],
                }
            )
    return result


def compact_base(row):
    return {
        "video_id": row.get("video_id") or row.get("id"),
        "url": row.get("url") or row.get("webpage_url"),
        "title": row.get("title"),
        "description": row.get("description"),
        "upload_date": row.get("upload_date"),
        "timestamp": row.get("timestamp"),
        "duration": row.get("duration"),
        "source_type": row.get("source_type"),
        "source_route": row.get("source_route"),
        "channel": row.get("channel"),
        "channel_id": row.get("channel_id"),
        "channel_handle": row.get("channel_handle"),
        "view_count": row.get("view_count"),
        "like_count": row.get("like_count"),
        "comment_count": row.get("comment_count"),
        "thumbnail": row.get("thumbnail"),
        "live_status": row.get("live_status"),
        "was_live": row.get("was_live"),
    }


def index_item(video, score, reason=None):
    item = {
        "video_id": video["video_id"],
        "url": video.get("url"),
        "title": video.get("title"),
        "upload_date": video.get("upload_date"),
        "source_type": video.get("source_type"),
        "view_count": video.get("view_count"),
        "confidence": round(float(score), 3),
    }
    if reason:
        item["reason"] = reason
    return item


def sort_index(items, limit=60):
    def key(x):
        return (
            x.get("confidence") or 0,
            x.get("view_count") or 0,
            x.get("upload_date") or "",
        )
    return sorted(items, key=key, reverse=True)[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", default="output")
    ap.add_argument("--heroes", default="config/heroes.json")
    ap.add_argument("--synced-heroes", default="data/entities/heroes.json")
    ap.add_argument("--skins", default="data/entities/skins.json")
    ap.add_argument("--game-taxonomy", default="config/game_taxonomy.json")
    ap.add_argument("--esports-taxonomy", default="config/esports_taxonomy.json")
    ap.add_argument("--esports-entities", default="config/esports_entities.json")
    args = ap.parse_args()

    out = Path(args.output)
    game_dir = out / "game"
    esports_dir = out / "esports"
    quality_dir = out / "quality"
    for p in [game_dir, esports_dir, quality_dir]:
        p.mkdir(parents=True, exist_ok=True)

    heroes = load_heroes(args.heroes, args.synced_heroes)
    skins = load_skins(args.skins)
    game_tax = read_json(args.game_taxonomy)
    esports_tax = read_json(args.esports_taxonomy)
    esports_entities = read_json(args.esports_entities)

    game_counts = Counter()
    esports_counts = Counter()
    domain_counts = Counter()
    tournament_stats = defaultdict(lambda: Counter())
    tournament_seasons = defaultdict(lambda: Counter())
    team_stats = defaultdict(lambda: Counter())
    hero_index = defaultdict(list)
    skin_index = defaultdict(list)
    lore_index = defaultdict(list)
    tournament_index = defaultdict(list)
    team_index = defaultdict(list)
    candidate_skins = {}
    candidate_players = Counter()
    totals = Counter()

    game_fp = (game_dir / "videos.jsonl").open("w", encoding="utf-8")
    esports_fp = (esports_dir / "videos.jsonl").open("w", encoding="utf-8")
    highlights_fp = (esports_dir / "highlights.jsonl").open("w", encoding="utf-8")
    matches_fp = (esports_dir / "matches.jsonl").open("w", encoding="utf-8")
    patches_fp = (game_dir / "patches.jsonl").open("w", encoding="utf-8")
    unclassified_fp = (quality_dir / "unclassified.jsonl").open("w", encoding="utf-8")
    low_fp = (quality_dir / "low-confidence.jsonl").open("w", encoding="utf-8")

    try:
        for row in iter_jsonl(args.input):
            totals["videos"] += 1
            fields = text_fields(row)
            normalized_fields = {k: norm(v) for k, v in fields.items()}
            base = compact_base(row)

            hero_mentions, skin_mentions, tournament_mentions, team_mentions = extract_entities(
                fields, normalized_fields, heroes, skins, esports_entities
            )
            game_type_scores, game_evidence = classify_types(fields, normalized_fields, game_tax)
            esports_type_scores, esports_evidence = classify_types(fields, normalized_fields, esports_tax)

            # Hero-specific labels need an actual hero relation. This prevents
            # generic phrases such as "wombo combo" or "hướng dẫn sự kiện"
            # from being treated as hero guides.
            if not hero_mentions:
                for label in ("hero_spotlight", "hero_guide", "hero_gameplay", "hero_update"):
                    game_type_scores.pop(label, None)
                    game_evidence.pop(label, None)

            hero_best = max((x["confidence"] for x in hero_mentions), default=0.0)
            skin_best = max((x["confidence"] for x in skin_mentions), default=0.0)
            tournament_best = max((x["confidence"] for x in tournament_mentions), default=0.0)
            team_best = max((x["confidence"] for x in team_mentions), default=0.0)

            # Short content from the sports channel is a useful esports moment
            # signal only when it is on the sports channel or already anchored
            # to a tournament/team.
            sports_channel = "sports" in norm(base.get("channel_handle") or base.get("channel") or "")
            pre_anchor = max(tournament_best, team_best)
            if base.get("source_type") == "short" and (sports_channel or pre_anchor >= 0.52):
                esports_type_scores["short_moment"] = max(
                    esports_type_scores.get("short_moment", 0.0), 0.70
                )

            game_type_best = max(game_type_scores.values(), default=0.0)
            esports_type_best = max(esports_type_scores.values(), default=0.0)

            lore_score = max(
                game_type_scores.get("lore_story", 0.0),
                game_type_scores.get("cinematic", 0.0),
            )

            game_score = max(hero_best, skin_best, game_type_best)

            anchor_type_score = max(
                esports_type_scores.get("match_full", 0.0),
                esports_type_scores.get("livestream", 0.0),
                esports_type_scores.get("interview", 0.0),
                esports_type_scores.get("roster", 0.0),
                esports_type_scores.get("tournament_info", 0.0),
            )
            esports_anchor = max(tournament_best, team_best, anchor_type_score)
            moment_score = max(
                esports_type_scores.get("highlight", 0.0),
                esports_type_scores.get("recap", 0.0),
                esports_type_scores.get("short_moment", 0.0),
            )

            if esports_anchor >= 0.52:
                esports_score = min(
                    0.99,
                    max(esports_anchor, esports_type_best)
                    + (0.08 if len(team_mentions) >= 2 else 0.0),
                )
            elif sports_channel and moment_score >= 0.65:
                esports_score = moment_score
            else:
                esports_score = 0.0

            # Event-only labels should not pull a clearly esports-only video
            # into the game domain.
            if (
                esports_score >= 0.65
                and not hero_mentions
                and not skin_mentions
                and set(game_type_scores).issubset({"event_promo"})
            ):
                game_score = 0.0

            game_types = sorted(game_type_scores, key=game_type_scores.get, reverse=True)
            esports_types = sorted(esports_type_scores, key=esports_type_scores.get, reverse=True)

            primary_game = game_types[0] if game_types else None
            primary_esports = esports_types[0] if esports_types else None
            season = extract_season(base.get("title") or "")
            game_number = extract_game_number(base.get("title") or "")

            lore_keywords = sum(game_tax.get("story_groups", {}).values(), [])
            highlight_keywords = esports_tax.get("content_types", {}).get("highlight", [])
            lore_segments = chapter_segments(row, lore_keywords)
            highlight_segments = chapter_segments(row, highlight_keywords)

            if game_score >= 0.34:
                game_rec = {
                    **base,
                    "domain_score": round(game_score, 3),
                    "primary_type": primary_game,
                    "content_types": game_type_scores,
                    "heroes": hero_mentions,
                    "skins": skin_mentions,
                    "lore_segments": lore_segments,
                    "evidence": game_evidence,
                }
                game_fp.write(json.dumps(game_rec, ensure_ascii=False) + "\n")
                domain_counts["game"] += 1
                if primary_game:
                    game_counts[primary_game] += 1

                for h in hero_mentions:
                    relation = min(0.99, max(h["confidence"], game_type_best))
                    hero_index[h["id"]].append(index_item(base, relation, primary_game))
                    if lore_score >= 0.34:
                        lore_index[h["id"]].append(index_item(base, max(h["confidence"], lore_score), "hero_lore"))

                for s in skin_mentions:
                    relation = min(0.99, max(s["confidence"], game_type_scores.get("skin_showcase", 0), game_type_scores.get("skin_trailer", 0)))
                    skin_index[s["id"]].append(index_item(base, relation, primary_game))

                if lore_score >= 0.34 and not hero_mentions:
                    lore_index["general"].append(index_item(base, lore_score, primary_game))

                if primary_game == "patch_update":
                    patches_fp.write(json.dumps(game_rec, ensure_ascii=False) + "\n")

                skin_signal = max(
                    game_type_scores.get("skin_showcase", 0),
                    game_type_scores.get("skin_trailer", 0),
                )
                if skin_signal >= 0.65 and hero_mentions and not skin_mentions:
                    key = base.get("video_id")
                    candidate_skins[key] = {
                        "video_id": key,
                        "title": base.get("title"),
                        "heroes": [h["name"] for h in hero_mentions],
                        "confidence": round(skin_signal, 3),
                        "url": base.get("url"),
                    }

            if esports_score >= 0.34:
                highlight_kind = None
                if esports_type_scores.get("highlight", 0) >= 0.52:
                    if len(team_mentions) >= 2:
                        highlight_kind = "match"
                    elif len(team_mentions) == 1:
                        highlight_kind = "team"
                    elif tournament_mentions:
                        highlight_kind = "tournament"
                    else:
                        highlight_kind = "general"

                esports_rec = {
                    **base,
                    "domain_score": round(esports_score, 3),
                    "primary_type": primary_esports,
                    "content_types": esports_type_scores,
                    "tournaments": tournament_mentions,
                    "teams": team_mentions,
                    "season": season,
                    "game_number": game_number,
                    "highlight_kind": highlight_kind,
                    "highlight_segments": highlight_segments,
                    "evidence": esports_evidence,
                }
                esports_fp.write(json.dumps(esports_rec, ensure_ascii=False) + "\n")
                domain_counts["esports"] += 1
                if primary_esports:
                    esports_counts[primary_esports] += 1

                for t in tournament_mentions:
                    tournament_stats[t["id"]]["videos"] += 1
                    if season:
                        tournament_seasons[t["id"]][season] += 1
                    if primary_esports:
                        tournament_stats[t["id"]][primary_esports] += 1
                    tournament_index[t["id"]].append(index_item(base, max(t["confidence"], esports_type_best), primary_esports))

                for tm in team_mentions:
                    team_stats[tm["id"]]["videos"] += 1
                    if primary_esports:
                        team_stats[tm["id"]][primary_esports] += 1
                    team_index[tm["id"]].append(index_item(base, max(tm["confidence"], esports_type_best), primary_esports))

                if esports_type_scores.get("highlight", 0) >= 0.52:
                    highlights_fp.write(json.dumps(esports_rec, ensure_ascii=False) + "\n")
                    totals["highlights"] += 1

                is_match = (
                    len(team_mentions) >= 2
                    or esports_type_scores.get("match_full", 0) >= 0.65
                )
                if is_match:
                    matches_fp.write(json.dumps(esports_rec, ensure_ascii=False) + "\n")
                    totals["matches"] += 1

                title = base.get("title") or ""
                for pattern in esports_entities.get("player_patterns", []):
                    for m in re.finditer(pattern, title):
                        if m.groups():
                            name = m.group(1)
                            if len(name) >= 2:
                                candidate_players[name] += 1

            if game_score < 0.34 and esports_score < 0.34:
                unclassified_fp.write(json.dumps(base, ensure_ascii=False) + "\n")
                domain_counts["unclassified"] += 1
            elif max(game_score, esports_score) < 0.65:
                low_fp.write(
                    json.dumps(
                        {
                            **base,
                            "game_score": round(game_score, 3),
                            "esports_score": round(esports_score, 3),
                            "heroes": hero_mentions,
                            "tournaments": tournament_mentions,
                            "teams": team_mentions,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                domain_counts["low_confidence"] += 1
    finally:
        for fp in [game_fp, esports_fp, highlights_fp, matches_fp, patches_fp, unclassified_fp, low_fp]:
            fp.close()

    hero_by_id = {x["id"]: x for x in heroes}
    skin_by_id = {x["id"]: x for x in skins}
    tournament_by_id = {x["id"]: x for x in esports_entities.get("tournaments", [])}
    team_by_id = {x["id"]: x for x in esports_entities.get("teams", [])}

    hero_output = {
        key: {
            "hero": hero_by_id.get(key, {"id": key, "name": key}),
            "videos": sort_index(items),
            "total_relations": len(items),
        }
        for key, items in hero_index.items()
    }
    skin_output = {
        key: {
            "skin": skin_by_id.get(key, {"id": key, "name": key}),
            "videos": sort_index(items),
            "total_relations": len(items),
        }
        for key, items in skin_index.items()
    }
    lore_output = {
        key: {
            "entity": hero_by_id.get(key, {"id": key, "name": "General lore"}),
            "videos": sort_index(items),
            "total_relations": len(items),
        }
        for key, items in lore_index.items()
    }

    tournament_output = []
    for tid, stats in tournament_stats.items():
        entity = tournament_by_id.get(tid, {"id": tid, "name": tid})
        tournament_output.append(
            {
                **entity,
                "stats": dict(stats),
                "seasons": [
                    {"name": name, "videos": count}
                    for name, count in tournament_seasons[tid].most_common()
                ],
            }
        )
    tournament_output.sort(key=lambda x: x["stats"].get("videos", 0), reverse=True)

    team_output = []
    for tid, stats in team_stats.items():
        entity = team_by_id.get(tid, {"id": tid, "name": tid})
        team_output.append(
            {
                **entity,
                "stats": dict(stats),
            }
        )
    team_output.sort(key=lambda x: x["stats"].get("videos", 0), reverse=True)

    write_json(game_dir / "hero-video-index.json", hero_output)
    write_json(game_dir / "skin-video-index.json", skin_output)
    write_json(game_dir / "lore-video-index.json", lore_output)
    write_json(game_dir / "content-type-counts.json", dict(game_counts))

    write_json(esports_dir / "tournaments.json", tournament_output)
    write_json(esports_dir / "teams.json", team_output)
    write_json(
        esports_dir / "tournament-video-index.json",
        {k: {"entity": tournament_by_id.get(k), "videos": sort_index(v), "total_relations": len(v)} for k, v in tournament_index.items()},
    )
    write_json(
        esports_dir / "team-video-index.json",
        {k: {"entity": team_by_id.get(k), "videos": sort_index(v), "total_relations": len(v)} for k, v in team_index.items()},
    )

    write_json(quality_dir / "candidate-skins.json", list(candidate_skins.values()))
    write_json(
        quality_dir / "candidate-players.json",
        [{"name": name, "mentions": count} for name, count in candidate_players.most_common(300)],
    )

    summary = {
        "input_videos": totals["videos"],
        "domains": dict(domain_counts),
        "game_content_types": dict(game_counts),
        "esports_content_types": dict(esports_counts),
        "hero_dictionary_size": len(heroes),
        "skin_dictionary_size": len(skins),
        "heroes_with_related_videos": len(hero_index),
        "skins_with_related_videos": len(skin_index),
        "lore_entities_with_videos": len(lore_index),
        "tournaments_detected": len(tournament_stats),
        "teams_detected": len(team_stats),
        "highlights": totals["highlights"],
        "matches": totals["matches"],
        "candidate_skins": len(candidate_skins),
        "candidate_players": len(candidate_players),
    }
    write_json(out / "summary.json", summary)

    report = [
        "# YouTube AOV analysis report",
        "",
        f"- Input videos: {summary['input_videos']:,}",
        f"- Game-domain videos: {domain_counts['game']:,}",
        f"- eSports-domain videos: {domain_counts['esports']:,}",
        f"- Unclassified: {domain_counts['unclassified']:,}",
        f"- Low-confidence review queue: {domain_counts['low_confidence']:,}",
        f"- Hero dictionary: {len(heroes):,}",
        f"- Skin dictionary: {len(skins):,}",
        f"- Heroes with related videos: {len(hero_index):,}",
        f"- Skins with related videos: {len(skin_index):,}",
        f"- Highlights: {totals['highlights']:,}",
        f"- Match-like videos: {totals['matches']:,}",
        "",
        "## Game content types",
        "",
    ]
    report += [f"- {k}: {v:,}" for k, v in game_counts.most_common()]
    report += ["", "## eSports content types", ""]
    report += [f"- {k}: {v:,}" for k, v in esports_counts.most_common()]
    report += ["", "## Tournaments", ""]
    report += [f"- {x['name']}: {x['stats'].get('videos', 0):,} videos" for x in tournament_output]
    report += ["", "## Teams", ""]
    report += [f"- {x['name']}: {x['stats'].get('videos', 0):,} videos" for x in team_output]
    (out / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
