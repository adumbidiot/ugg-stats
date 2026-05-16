import time
from dataclasses import dataclass
from enum import Enum
from typing import Iterator

import dacite
from curl_cffi.requests import Response, Session

FETCH_MATCH_SUMMARIES_QUERY = """
query FetchMatchSummaries($championId: [Int], $page: Int, $queueType: [Int], $duoRiotUserName: String, $duoRiotTagLine: String, $regionId: String!, $role: [Int], $seasonIds: [Int]!, $riotUserName: String!, $riotTagLine: String!) {
  fetchPlayerMatchSummaries(
    championId: $championId
    page: $page
    queueType: $queueType
    duoRiotUserName: $duoRiotUserName
    duoRiotTagLine: $duoRiotTagLine
    regionId: $regionId
    role: $role
    seasonIds: $seasonIds
    riotUserName: $riotUserName
    riotTagLine: $riotTagLine
  ) {
    finishedMatchSummaries
    totalNumMatches
    matchSummaries {
      assists
      augments
      championId
      cs
      damage
      deaths
      gold
      items
      jungleCs
      killParticipation
      kills
      level
      matchCreationTime
      matchDuration
      matchId
      maximumKillStreak
      primaryStyle
      queueType
      regionId
      role
      runes
      subStyle
      summonerName
      riotUserName
      riotTagLine
      summonerSpells
      psHardCarry
      psTeamPlay
      lpInfo {
        lp
        placement
        promoProgress
        promoTarget
        promotedTo {
          tier
          rank
          __typename
        }
        __typename
      }
      teamA {
        championId
        summonerName
        riotUserName
        riotTagLine
        teamId
        role
        hardCarry
        teamplay
        placement
        playerSubteamId
        __typename
      }
      teamB {
        championId
        summonerName
        riotUserName
        riotTagLine
        teamId
        role
        hardCarry
        teamplay
        placement
        playerSubteamId
        __typename
      }
      version
      visionScore
      win
      roleQuestCompletion
      roleBoundItem
      __typename
    }
    __typename
  }
}
"""


def to_camel_case(key: str) -> str:
    first_part, *remaining_parts = key.split("_")
    return first_part + "".join(part.title() for part in remaining_parts)


@dataclass
class TeamPlayer:
    riot_user_name: str
    riot_tag_line: str


def user_is_in_team(team: list[TeamPlayer], user_name: str, user_tag_line: str) -> bool:
    for player in team:
        if player.riot_user_name == user_name and player.riot_tag_line == user_tag_line:
            return True
    return False


@dataclass
class MatchSummary:
    riot_user_name: str
    riot_tag_line: str
    match_id: int
    queue_type: str
    win: bool
    kills: int
    deaths: int
    assists: int
    team_a: list[TeamPlayer]
    team_b: list[TeamPlayer]

    def get_team_for_user(
        self, user_name: str, tag_line: str
    ) -> list[TeamPlayer] | None:
        if user_is_in_team(self.team_a, user_name, tag_line):
            return self.team_a
        elif user_is_in_team(self.team_b, user_name, tag_line):
            return self.team_b
        else:
            return None


@dataclass
class PlayerMatchSummaries:
    finished_match_summaries: bool
    match_summaries: list[MatchSummary]


def graphql_request(
    session: Session[Response], operation: str, query: str, variables: dict[str, object]
) -> dict[str, object]:
    for i in range(3):
        if i > 0:
            time.sleep(2**i)

        response: Response = session.post(
            "https://u.gg/api",
            params={"operationName": operation, "query": query, "variables": variables},  # type: ignore
        )

        if response.status_code in {500, 502, 503}:
            continue

        break

    response.raise_for_status()  # type: ignore

    data: object = response.json()  # type: ignore
    assert isinstance(data, dict)

    assert all(isinstance(value, str) for value in data.keys())
    assert all(isinstance(value, object) for value in data.values())

    return data  # ty:ignore


class Season(Enum):
    Season1 = "1"
    Season2 = "2"
    Season3 = "3"
    Season4 = "4"
    Season5 = "5"
    Season6 = "6"
    Season7 = "7"
    Season8 = "8"
    Season9 = "9"
    Season10 = "10"
    Season11 = "11"
    Season12 = "12"
    Season13_1 = "13-1"
    Season13_2 = "13-2"
    Season14_1 = "14-1"
    Season14_2 = "14-2"
    Season14_3 = "14-3"
    Season15 = "15"
    Season16 = "16"


SEASON_ID_MAP = {
    Season.Season1: 1,
    Season.Season2: 2,
    Season.Season3: 3,
    Season.Season4: 4,
    Season.Season5: 5,
    Season.Season6: 6,
    Season.Season7: 7,
    Season.Season8: 8,
    Season.Season9: 9,
    Season.Season10: 14,
    Season.Season11: 16,
    Season.Season12: 18,
    Season.Season13_1: 20,
    Season.Season13_2: 21,
    Season.Season14_1: 22,
    Season.Season14_2: 23,
    Season.Season14_3: 24,
    Season.Season15: 25,
    Season.Season16: 26,
}


def fetch_match_summaries(
    session: Session[Response],
    user_name: str,
    user_tag_line: str,
    seasons: list[Season],
    page: int = 1,
) -> PlayerMatchSummaries:
    response = graphql_request(
        session,
        "FetchMatchSummaries",
        FETCH_MATCH_SUMMARIES_QUERY,
        {
            "championId": [],
            "duoRiotTagLine": "",
            "duoRiotUserName": "",
            "page": page,
            "queueType": [],
            "regionId": "na1",
            "riotTagLine": user_tag_line,
            "riotUserName": user_name,
            "role": [],
            "seasonIds": [SEASON_ID_MAP[season] for season in seasons],
        },
    )
    response_data: object = response["data"]
    assert isinstance(response_data, dict)
    assert all(isinstance(value, str) for value in response_data.keys())
    assert all(isinstance(value, object) for value in response_data.values())

    summaries: object = response_data["fetchPlayerMatchSummaries"]  # ty: ignore
    assert isinstance(summaries, dict)
    assert all(isinstance(value, str) for value in summaries.keys())
    assert all(isinstance(value, object) for value in summaries.values())

    value = dacite.from_dict(
        PlayerMatchSummaries, summaries, dacite.Config(convert_key=to_camel_case)
    )

    return value


def iter_match_summaries(
    session: Session[Response],
    user_name: str,
    user_tag_line: str,
    season_ids: list[Season],
) -> Iterator[PlayerMatchSummaries]:
    page = 1
    should_exit = False
    while not should_exit:
        match_summaries = fetch_match_summaries(
            session, user_name, user_tag_line, season_ids, page=page
        )
        should_exit = match_summaries.finished_match_summaries
        yield match_summaries
        page += 1
