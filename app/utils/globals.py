from enum import Enum
import os

from ..utils.config import config


class Globals:
    HOME = os.path.expanduser("~")

    @classmethod
    def set_delay(cls, delay=5):
        cls.DELAY_TIME_SECONDS = int(delay)

    @classmethod
    def set_volume(cls, volume=60):
        cls.DEFAULT_VOLUME_THRESHOLD = int(volume)
