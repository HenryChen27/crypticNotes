from dataclasses import dataclass


@dataclass(frozen=True)
class SessionContext:
    """User-supplied before the game; never inferred from benchmark labels."""
    difficulty: str
    mode: str | None = None

    def __post_init__(self) -> None:
        if self.difficulty not in ('hard', 'nightmare'):
            raise ValueError('Choose hard or nightmare before matching')
        if self.difficulty == 'hard' and self.mode is not None:
            raise ValueError('Hard mode does not take a solo/duo selector')
        if self.difficulty == 'nightmare' and self.mode not in ('solo', 'duo'):
            raise ValueError('Nightmare requires solo or duo (multiplayer) before matching')
