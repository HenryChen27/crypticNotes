from dataclasses import dataclass


@dataclass(frozen=True)
class SessionContext:
    """User-supplied before the game; never inferred from benchmark labels."""
    difficulty: str
    mode: str | None = None
    provider: str = "lianghapi"

    def __post_init__(self) -> None:
        if self.provider not in ('lianghapi', 'zhanshi'):
            raise ValueError('Unknown map provider')
        if self.provider == 'zhanshi':
            if self.difficulty not in ('hard','nightmare') or self.mode not in ('full', 'speed'):
                raise ValueError('展十地图请选择困难/噩梦及全棺/速刷路线')
            return
        if self.difficulty not in ('hard', 'nightmare'):
            raise ValueError('Choose hard or nightmare before matching')
        if self.difficulty == 'hard' and self.mode is not None:
            raise ValueError('Hard mode does not take a solo/duo selector')
        if self.difficulty == 'nightmare' and self.mode not in ('solo', 'duo'):
            raise ValueError('Nightmare requires solo or duo (multiplayer) before matching')
