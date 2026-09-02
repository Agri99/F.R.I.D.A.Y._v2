"""Quick wake-word test."""
from friday.interaction.wakeword import WakeWordListener

wl = WakeWordListener()
wl.listen_for_wakeword()