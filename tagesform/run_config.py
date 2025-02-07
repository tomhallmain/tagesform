
from utils.globals import PlaylistSortType # must import first

class RunConfig:

    def __init__(self, args=None, placeholder=False):
        self.args = args
        self.playlist_sort_type = PlaylistSortType.RANDOM
        self.total = -1
        self.is_all_tracks = False
        self.directories = self.get("directories")
        self.overwrite = False
        self.muse = True
        self.extend = True
        self.enable_dynamic_volume = True
        self.enable_long_track_splitting  = False
        self.long_track_splitting_time_cutoff_minutes = 20
        self.placeholder = placeholder
        self.track = None

    def get(self, name):
        if isinstance(self.args, dict):
            return self.args[name]
        elif not self.args:
            return None
        else:
            return getattr(self.args, name)

    def validate(self):
        return True

    def __str__(self):
        return str(self.__dict__)
