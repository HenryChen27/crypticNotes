from dataclasses import dataclass

# 游戏里的两张地图。`curse`=厄运之女（原有全部图库），`linguang`=磷光症。
SCENES = ('curse', 'linguang')
SCENE_NAMES = {'curse': '厄运之女', 'linguang': '磷光症'}
# 磷光症目前：凉哈皮只有困难，展十只有噩梦（十四棺）；其余难度待作者更新后在这里放开。
SCENE_CONTEXTS = {
    'linguang': {
        'lianghapi': dict(difficulties=('hard',), modes=(None,)),
        'zhanshi': dict(difficulties=('nightmare',), modes=('full',)),
    },
}


def scene_options(scene, provider):
    """(difficulties, modes) an author currently offers for a map; None = unrestricted."""
    limits = SCENE_CONTEXTS.get(scene)
    if limits is None:
        return None
    entry = limits.get(provider)
    return (entry['difficulties'], entry['modes']) if entry else ((), ())


@dataclass(frozen=True)
class SessionContext:
    """User-supplied before the game; never inferred from benchmark labels."""
    difficulty: str
    mode: str | None = None
    provider: str = "lianghapi"
    scene: str = "curse"

    def __post_init__(self) -> None:
        if self.provider not in ('lianghapi', 'zhanshi'):
            raise ValueError('Unknown map provider')
        if self.scene not in SCENES:
            raise ValueError('Unknown map scene')
        options = scene_options(self.scene, self.provider)
        if options is not None:
            difficulties, modes = options
            if self.difficulty not in difficulties or self.mode not in modes:
                raise ValueError(f'{SCENE_NAMES[self.scene]}目前没有这位作者的这个难度（凉哈皮：困难；展十：噩梦十四棺）')
            return
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
