from dataclasses import dataclass

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
ALL_SEASONS = [
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


def parse_formatted_name(formatted_name: str) -> User:
    name, tag = formatted_name.split("#")
    return User(name=name, tag=tag)


def update_match_summaries(database: Database, user: User, seasons: list[Season]):
    with curl_cffi.Session() as session:
        for match_summaries in iter_match_summaries(
            session, user.name, user.tag, seasons
        ):
            for website_summary in match_summaries.match_summaries:
                summary = MatchSummary.from_website_match_summary(website_summary)
                database.upsert_match_summary(summary)


@dataclass
class Stats:
    df: pd.DataFrame
    total_wins: int = 0
    total_losses: int = 0
    total_kills: int = 0
    total_deaths: int = 0
    total_assists: int = 0

    @property
    def total_matches(self) -> int:
        return self.total_wins + self.total_losses

    @property
    def win_pct(self) -> float:
        return self.total_wins / self.total_matches

    @property
    def average_kills(self) -> float:
        return self.total_kills / self.total_matches

    @property
    def average_deaths(self) -> float:
        return self.total_deaths / self.total_matches

    @property
    def average_assists(self) -> float:
        return self.total_assists / self.total_matches


def get_stats_for_user(
    database: Database, user: User, skip_games_with_user: User | None = None
) -> Stats:
    data_map = dict()
    stats = Stats(df=pd.DataFrame())
    for summary in database.list_match_summaries(user):
        if summary.queue_type in SKIP_QUEUE_TYPES:
            continue
        assert summary.queue_type == "ranked_solo_5x5", (
            f'Unknown queue type "{summary.queue_type}"'
        )

        if skip_games_with_user is not None and summary.has_user(skip_games_with_user):
            continue

        if summary.win:
            stats.total_wins += 1
        else:
            stats.total_losses += 1
        stats.total_kills += summary.kills
        stats.total_deaths += summary.deaths
        stats.total_assists += summary.assists

        team = summary.get_team_for_user(user)
        assert team is not None, "Not in team a or b"

        for team_user in team:
            if team_user.id == user.id:
                continue

            entry = data_map.setdefault(
                team_user.formatted_name(),
                {"User": team_user.formatted_name(), "Wins": 0, "Losses": 0},
            )
            if summary.win:
                entry["Wins"] += 1
            else:
                entry["Losses"] += 1

    stats.df = pd.DataFrame(data_map.values(), columns=["User", "Wins", "Losses"])
    stats.df["Total"] = stats.df["Wins"] + stats.df["Losses"]
    stats.df["Win %"] = (stats.df["Wins"] / stats.df["Total"]) * 100.0

    return stats


def main(
    formatted_name: str,
    min_total: int = 3,
    cached: bool = False,
    skip_games_with_user: str | None = None,
    # seasons: list[str] = [],
) -> None:
    user = parse_formatted_name(formatted_name)

    skip_games_with_user_parsed = None
    if skip_games_with_user is not None:
        skip_games_with_user_parsed = parse_formatted_name(skip_games_with_user)

    parsed_seasons = ALL_SEASONS

    with Database("database.db") as database:
        database.upsert_user(user)

        if not cached:
            update_match_summaries(database, user, parsed_seasons)

        stats = get_stats_for_user(database, user, skip_games_with_user_parsed)

    stats.df["Win %"] = stats.df["Win %"].round(decimals=3)
    stats.df = stats.df.sort_values(by="Win %", ascending=False)
    stats.df = stats.df[stats.df["Total"] >= min_total]

    print(stats.df.to_string(index=False))

    print()
    print(f"Total Wins: {stats.total_wins}")
    print(f"Total Losses: {stats.total_losses}")
    print(f"Total Matches: {stats.total_matches}")
    print(f"Total Win %: {stats.win_pct:.3f}")
    print(f"Total Kills: {stats.total_kills}")
    print(f"Total Deaths: {stats.total_deaths}")
    print(f"Total Assists: {stats.total_assists}")
    print(
        f"Average K/D/A: {stats.average_kills:.3f}/{stats.average_deaths:.3f}/{stats.average_assists:.3f}"
    )


if __name__ == "__main__":
    typer.run(main)
