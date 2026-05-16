from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GoalType(StrEnum):
    regular = "regular"
    own = "own"
    penalty = "penalty"


class CardColor(StrEnum):
    yellow = "yellow"
    red = "red"


class LineupRole(StrEnum):
    starter = "starter"
    sub = "sub"


class CardTargetKind(StrEnum):
    player = "player"
    coach = "coach"


class Player(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Full name of the player as it appears on the match sheet")
    jersey: int | None = Field(None, description="Jersey number (dorsal); null if not visible")


class Coach(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Full name of the coach or technical staff member")
    role_code: str | None = Field(
        None,
        description="Role code shown next to the name (A=assistant, E=entrenador, D=delegat, X=other)",
    )


class LineupEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player: Player
    role: LineupRole = Field(..., description="'starter' (TITULARS) or 'sub' (SUPLENTS)")


class Goal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minute: int = Field(..., description="Minute of the goal")
    scoreline_home: int = Field(..., description="Home score after this goal")
    scoreline_away: int = Field(..., description="Away score after this goal")
    scorer_name: str = Field(..., description="Name of the scorer as it appears on the match sheet")
    scoring_team: Literal["home", "away"] = Field(
        ..., description="Which team scored: 'home' or 'away'"
    )
    type: GoalType = Field(..., description="'regular', 'own' (own goal), or 'penalty'")


class Card(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minute: int = Field(..., description="Minute the card was shown")
    color: CardColor = Field(..., description="'yellow' or 'red'")
    target_kind: CardTargetKind = Field(
        ..., description="'player' if shown to a player, 'coach' if shown to technical staff"
    )
    target_name: str = Field(..., description="Name of the person who received the card")
    team: Literal["home", "away"] = Field(..., description="Team the card recipient belongs to")


class Team(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Official team name")
    lineup: list[LineupEntry] = Field(default_factory=list, description="All players (starters + subs)")
    coaches: list[Coach] = Field(default_factory=list, description="Technical staff listed in EQUIP TÈCNIC")


class Stadium(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Stadium name (ESTADI)")
    address: str | None = Field(None, description="Address shown below the stadium name")


class Referee(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Referee full name (ÀRBITRES)")
    committee: str | None = Field(None, description="Committee name shown in parentheses")


class MatchExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    journey: int = Field(..., description="Jornada number (e.g. 29)")
    competition: str = Field(..., description="Competition name (e.g. 'FCF')")
    status: str = Field(..., description="Match status (e.g. 'ACTA TANCADA')")
    score_home: int = Field(..., description="Final home score")
    score_away: int = Field(..., description="Final away score")
    home: Team = Field(..., description="Home team with lineup and coaches")
    away: Team = Field(..., description="Away team with lineup and coaches")
    stadium: Stadium
    referee: Referee
    goals: list[Goal] = Field(default_factory=list)
    cards: list[Card] = Field(default_factory=list)
