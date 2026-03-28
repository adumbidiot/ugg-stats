import curl_cffi
import pandas as pd
import typer

from ugg_stats.database import Database, MatchSummary, User
from ugg_stats.website import Season, iter_match_summaries

SKIP_QUEUE_TYPES = {
    "normal_draft_5x5",
    "swiftplay",
    "ranked_flex_sr",
    "arena",
    "urf",
    "normal_aram",
}


def parse_formatted_name(formatted_name: str) -> User:
    name, tag = formatted_name.split("#")
    return User(name=name, tag=tag)


def main(
    formatted_name: str,
    min_total: int = 3,
    cached: bool = False,
    skip_games_with_user: str | None = None,
) -> None:
    user = parse_formatted_name(formatted_name)

    skip_games_with_user_parsed = None
    if skip_games_with_user is not None:
        skip_games_with_user_parsed = parse_formatted_name(skip_games_with_user)

    seasons = [
        Season.Season16,
        Season.Season15,
        Season.Season14_3,
        Season.Season14_2,
        Season.Season14_1,
        Season.Season13_2,
        Season.Season13_1,
        Season.Season12,
        Season.Season11,
        Season.Season10,
        Season.Season9,
        Season.Season8,
        Season.Season7,
        Season.Season6,
        Season.Season5,
        Season.Season4,
        Season.Season3,
        Season.Season2,
        Season.Season1,
    ]

    with Database("database.db") as database:
        database.upsert_user(user)

        if not cached:
            with curl_cffi.Session() as session:
                for match_summaries in iter_match_summaries(
                    session, user.name, user.tag, seasons
                ):
                    for website_summary in match_summaries.match_summaries:
                        summary = MatchSummary.from_website_match_summary(
                            website_summary
                        )
                        database.upsert_match_summary(summary)

        data_map = dict()
        total_wins = 0
        total_losses = 0
        total_kills = 0
        total_deaths = 0
        total_assists = 0
        for summary in database.list_match_summaries(user):
            if summary.queue_type in SKIP_QUEUE_TYPES:
                continue
            assert summary.queue_type == "ranked_solo_5x5", (
                f'Unknown queue type "{summary.queue_type}"'
            )

            if skip_games_with_user_parsed is not None and summary.has_user(
                skip_games_with_user_parsed
            ):
                continue

            if summary.win:
                total_wins += 1
            else:
                total_losses += 1
            total_kills += summary.kills
            total_deaths += summary.deaths
            total_assists += summary.assists

            team = summary.get_team_for_user(user)
            assert team is not None, "Not in team a or b"

            for team_user in team:
                if team_user.id == user.id:
                    continue

                team_user_formatted_name = f"{team_user.name}#{team_user.tag}"

                entry = data_map.setdefault(
                    team_user_formatted_name,
                    {"User": team_user_formatted_name, "Wins": 0, "Losses": 0},
                )
                if summary.win:
                    entry["Wins"] += 1
                else:
                    entry["Losses"] += 1

    df = pd.DataFrame(data_map.values(), columns=["User", "Wins", "Losses"])
    df["Total"] = df["Wins"] + df["Losses"]
    df["Win %"] = df["Wins"] / df["Total"]
    df = df.sort_values(by="Win %", ascending=False)
    df = df[df["Total"] >= min_total]

    print(df.to_string(index=False))

    total_matches = total_wins + total_losses
    print()
    print(f"Total Wins: {total_wins}")
    print(f"Total Losses: {total_losses}")
    print(f"Total Matches: {total_matches}")
    print(f"Total Win %: {total_wins / total_matches}")
    print(f"Total Kills: {total_kills}")
    print(f"Total Deaths: {total_deaths}")
    print(f"Total Assists: {total_assists}")
    print(
        f"Average K/D/A: {total_kills / total_matches:.3f}/{total_deaths / total_matches:.3f}/{total_assists / total_matches:.3f}"
    )


if __name__ == "__main__":
    typer.run(main)
