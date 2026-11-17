"""Optional appearance: player, speech, events and self-contained skins."""
from .player import PetAnimation
from .lantern import LanternAnimation
from .puppet import PuppetAnimation
from .speech import SpeechBubble
from .events import reaction
from .behavior import PetBehavior
from .heist import Heist

# Desk-pet bodies the player can choose between, in menu order.
SKINS = (('doll', PetAnimation), ('lantern', LanternAnimation), ('puppet', PuppetAnimation))
DEFAULT_SKIN = 'doll'


def skin_name(settings):
    """The chosen body from a settings mapping, falling back to the doll."""
    name = settings.get('pet_skin', DEFAULT_SKIN) if isinstance(settings, dict) else DEFAULT_SKIN
    return name if name in dict(SKINS) else DEFAULT_SKIN


def create_pet(button, skin=DEFAULT_SKIN):
    return dict(SKINS).get(skin, PetAnimation)(button)
