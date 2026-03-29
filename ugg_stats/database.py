import itertools
import json
import sqlite3
from dataclasses import dataclass
from types import TracebackType

from .website import MatchSummary as WebsiteMatchSummary

SETUP_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    tag TEXT NOT NULL,
    
    UNIQUE (name, tag)
) STRICT;

CREATE TABLE IF NOT EXISTS match_summary (
    user_id INTEGER NOT NULL,
    match_id INTEGER NOT NULL,
    queue_type TEXT NOT NULL,
    win INTEGER NOT NULL CHECK (win IN (0, 1)),
    kills INTEGER NOT NULL,
    deaths INTEGER NOT NULL,
    assists INTEGER NOT NULL,
    team_a BLOB NOT NULL,
    team_b BLOB NOT NULL,
    
    PRIMARY KEY (user_id, match_id),
    FOREIGN KEY (user_id) REFERENCES user (id)
) STRICT;
"""

UPSERT_USER_SQL = """
INSERT INTO user (
    id,
    name,
    tag
) VALUES (
    :id,
    :name,
    :tag
) ON CONFLICT (name, tag) DO UPDATE SET
    name = :name,
    tag = :tag
RETURNING id;
"""

UPSERT_MATCH_SUMMARY_SQL = """
INSERT OR REPLACE INTO match_summary (
    user_id,
    match_id,
    queue_type,
    win,
    kills,
    deaths,
    assists,
    team_a,
    team_b
) VALUES (
    :user_id,
    :match_id,
    :queue_type,
    :win,
    :kills,
    :deaths,
    :assists,
    jsonb(:team_a),
    jsonb(:team_b)
);
"""

GET_USER_SQL = """
SELECT
    id,
    name,
    tag
FROM
    user
WHERE
    id = :id;
"""

GET_MATCH_SUMMARIES_SQL = """
SELECT
    user_id,
    match_id,
    queue_type,
    win,
    kills,
    deaths,
    assists,
    json(match_summary.team_a) as team_a,
    json(match_summary.team_b) as team_b
FROM
    match_summary
WHERE
    match_summary.user_id = :user_id;
"""


@dataclass
class User:
    name: str
    tag: str
    id: int = 0

    def formatted_name(self) -> str:
        return f"{self.name}#{self.tag}"

    def as_row(self) -> dict[str, int | str | None]:
        return {
            "id": None if self.id == 0 else self.id,
            "name": self.name,
            "tag": self.tag,
        }

    @staticmethod
    def from_row(row) -> "User":
        return User(id=row["id"], name=row["name"], tag=row["tag"])


def user_is_in_team(team: list[User], test_user: User) -> bool:
    for user in team:
        if user.name == test_user.name and user.tag == test_user.tag:
            return True
    return False


@dataclass
class MatchSummary:
    user: User
    match_id: int
    queue_type: str
    win: bool
    kills: int
    deaths: int
    assists: int
    team_a: list[User]
    team_b: list[User]

    @staticmethod
    def from_website_match_summary(value: WebsiteMatchSummary) -> "MatchSummary":
        return MatchSummary(
            user=User(name=value.riot_user_name, tag=value.riot_tag_line),
            match_id=value.match_id,
            queue_type=value.queue_type,
            win=value.win,
            kills=value.kills,
            deaths=value.deaths,
            assists=value.assists,
            team_a=[
                User(name=value.riot_user_name, tag=value.riot_tag_line)
                for value in value.team_a
            ],
            team_b=[
                User(name=value.riot_user_name, tag=value.riot_tag_line)
                for value in value.team_b
            ],
        )

    def get_team_for_user(self, user: User) -> list[User] | None:
        if user_is_in_team(self.team_a, user):
            return self.team_a
        elif user_is_in_team(self.team_b, user):
            return self.team_b
        else:
            return None

    def has_user(self, user: User) -> bool:
        return self.get_team_for_user(user) is not None


class Database:
    path: str
    connection: sqlite3.Connection | None

    def __init__(self, path) -> None:
        self.path = path
        self.connection = None

    def __enter__(self) -> "Database":
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row

        self.connection.executescript(SETUP_SQL)

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_tb: TracebackType | None,
    ):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def upsert_user(self, user: User) -> None:
        assert self.connection is not None

        with self.connection:
            cursor = self.connection.cursor()
            cursor.execute(UPSERT_USER_SQL, user.as_row())
            row = cursor.fetchone()
            user.id = row["id"]

    def upsert_match_summary(self, match_summary: MatchSummary) -> None:
        assert self.connection is not None

        with self.connection:
            cursor = self.connection.cursor()
            for user in itertools.chain(
                [match_summary.user], match_summary.team_a, match_summary.team_b
            ):
                cursor.execute(UPSERT_USER_SQL, user.as_row())
                row = cursor.fetchone()
                user.id = row["id"]

            cursor.execute(
                UPSERT_MATCH_SUMMARY_SQL,
                {
                    "user_id": match_summary.user.id,
                    "match_id": match_summary.match_id,
                    "queue_type": match_summary.queue_type,
                    "win": match_summary.win,
                    "kills": match_summary.kills,
                    "deaths": match_summary.deaths,
                    "assists": match_summary.assists,
                    "team_a": json.dumps([value.id for value in match_summary.team_a]),
                    "team_b": json.dumps([value.id for value in match_summary.team_b]),
                },
            )

    def list_match_summaries(self, user: User) -> list[MatchSummary]:
        def resolve_user_ids(cursor: sqlite3.Cursor, user_ids: list[int]) -> list[User]:
            users = []
            for id in user_ids:
                cursor.execute(GET_USER_SQL, {"id": id})
                row = cursor.fetchone()
                user = User.from_row(row)
                users.append(user)
            return users

        assert self.connection is not None
        assert user.id != 0

        cursor = self.connection.cursor()
        nested_cursor = self.connection.cursor()
        cursor.execute(GET_USER_SQL, {"id": user.id})
        row = cursor.fetchone()
        if row is None:
            return []
        user = User.from_row(row)

        cursor.execute(GET_MATCH_SUMMARIES_SQL, {"user_id": user.id})
        results = []
        for row in cursor:
            team_a_ids = json.loads(row["team_a"])
            team_b_ids = json.loads(row["team_b"])

            team_a = resolve_user_ids(
                nested_cursor,
                team_a_ids,
            )
            team_b = resolve_user_ids(
                nested_cursor,
                team_b_ids,
            )

            results.append(
                MatchSummary(
                    user=user,
                    match_id=row["match_id"],
                    queue_type=row["queue_type"],
                    win=row["win"],
                    kills=row["kills"],
                    deaths=row["deaths"],
                    assists=row["assists"],
                    team_a=team_a,
                    team_b=team_b,
                )
            )

        return results
