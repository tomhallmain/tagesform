import datetime
import json
import os

from utils.runner_app_config import RunnerAppConfig

class AppInfoCache:
    CACHE_LOC = os.path.join(os.path.dirname(os.path.abspath(os.path.dirname(__file__))), "app_info_cache.json")
    INFO_KEY = "info"
    HISTORY_KEY = "history"
    DIRECTORIES_KEY = "directories"
    TRACKERS_KEY = "trackers"
    MAX_HISTORY_ENTRIES = 50

    def __init__(self):
        self._cache = {AppInfoCache.INFO_KEY: {}, AppInfoCache.HISTORY_KEY: [], AppInfoCache.DIRECTORIES_KEY: {}}
        self.load()
        self.validate()

    def store(self):
        with open(AppInfoCache.CACHE_LOC, "w") as f:
            json.dump(self._cache, f, indent=4)

    def load(self):
        try:
            with open(AppInfoCache.CACHE_LOC, "r") as f:
                self._cache = json.load(f)
        except FileNotFoundError:
            pass

    def validate(self):
        pass

    def _get_history(self) -> list:
        if AppInfoCache.HISTORY_KEY not in self._cache:
            self._cache[AppInfoCache.HISTORY_KEY] = {}
        return self._cache[AppInfoCache.HISTORY_KEY]

    def _get_directory_info(self):
        if AppInfoCache.DIRECTORIES_KEY not in self._cache:
            self._cache[AppInfoCache.DIRECTORIES_KEY] = {}
        return self._cache[AppInfoCache.DIRECTORIES_KEY]

    def _get_trackers(self) -> dict:
        if AppInfoCache.TRACKERS_KEY not in self._cache:
            self._cache[AppInfoCache.TRACKERS_KEY] = {}
        return self._cache[AppInfoCache.TRACKERS_KEY]

    def set(self, key, value):
        if AppInfoCache.INFO_KEY not in self._cache:
            self._cache[AppInfoCache.INFO_KEY] = {}
        self._cache[AppInfoCache.INFO_KEY][key] = value

    def get(self, key, default_val=None):
        if AppInfoCache.INFO_KEY not in self._cache or key not in self._cache[AppInfoCache.INFO_KEY]:
            return default_val
        return self._cache[AppInfoCache.INFO_KEY][key]

    def set_history(self, runner_config):
        history = self._get_history()
        if len(history) > 0 and runner_config == RunnerAppConfig.from_dict(history[0]):
            return False
        config_dict = runner_config.to_dict()
        history.insert(0, config_dict)
        # Remove the oldest entry from history if over the limit of entries
        while len(history) >= AppInfoCache.MAX_HISTORY_ENTRIES:
            history = history[0:-1]
        return True

    def get_last_history_index(self):
        history = self._get_history()
        return len(history) - 1

    def get_history(self, _idx=0):
        history = self._get_history()
        if _idx >= len(history):
            raise Exception("Invalid history index " + str(_idx))
        return history[_idx]

    def get_history_latest(self):
        history = self._get_history()
        if len(history) == 0:
            return RunnerAppConfig()
        return RunnerAppConfig.from_dict(history[0])

    def set_directory(self, directory, key, value):
        directory = AppInfoCache.normalize_directory_key(directory)
        if directory is None or directory.strip() == "":
            raise Exception(f"Invalid directory provided to app_info_cache.set(). key={key} value={value}")
        directory_info = self._get_directory_info()
        if directory not in directory_info:
            directory_info[directory] = {}
        directory_info[directory][key] = value

    def get_directory(self, directory, key, default_val=None):
        directory = AppInfoCache.normalize_directory_key(directory)
        directory_info = self._get_directory_info()
        if directory not in directory_info or key not in directory_info[directory]:
            return default_val
        return directory_info[directory][key]

    def get_tracker(self, tracker):
        trackers = self._get_trackers()
        if tracker not in trackers:
            trackers[tracker] = {"count": 0, "last": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
        return trackers[tracker]

    def increment_tracker(self, tracker):
        tracker = self.get_tracker(tracker)
        now = datetime.datetime.now()
        last_track = datetime.datetime.strptime(tracker["last"], "%Y-%m-%d %H:%M")
        if now.year <= last_track.year and now.month <= last_track.month and now.day <= last_track.day:
            tracker["count"] += 1
        else:
            tracker["count"] = 1
        tracker["last"] = now.strftime("%Y-%m-%d %H:%M")
        hours_since_last = (now - last_track).total_seconds()/3600
        return int(tracker["count"]), float(hours_since_last)

    @staticmethod
    def normalize_directory_key(directory):
        return os.path.normpath(os.path.abspath(directory))

app_info_cache = AppInfoCache()
