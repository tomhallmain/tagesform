import json
import os
import sys

from utils.utils import Utils

root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
configs_dir = os.path.join(root_dir, "configs")


class Config:
    CONFIGS_DIR_LOC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs")

    def __init__(self):
        self.dict = {}
        self.foreground_color = "white"
        self.background_color = "#2596BE"

        self.debug = False

        self.server_port = 6000
        self.server_password = "<PASSWORD>"
        self.server_host = "localhost"

        configs =  [ f.path for f in os.scandir(Config.CONFIGS_DIR_LOC) if f.is_file() and f.path.endswith(".json") ]
        self.config_path = None

        for c in configs:
            if os.path.basename(c) == "config.json":
                self.config_path = c
                break
            elif os.path.basename(c) != "config_example.json":
                self.config_path = c

        if self.config_path is None:
            self.config_path = os.path.join(Config.CONFIGS_DIR_LOC, "config_example.json")

        try:
            self.dict = json.load(open(self.config_path, "r", encoding="utf-8"))
        except Exception as e:
            Utils.log_red(e)
            Utils.log_yellow("Unable to load config. Ensure config.json file settings are correct.")

        self.set_values(str,
            "foreground_color",
            "background_color",
            "llm_model_name",
        )
        self.set_values(int,
        )
        self.set_values(list,
        )
        self.set_values(bool,
        )
        self.set_values(dict,
        )
        self.set_directories(
        )
        self.set_filepaths(
        )

        # i = 0
        # while i < len(self.directories):
        #     d = self.directories[i]
        #     try:
        #         if sys.platform == "win32" and not d.startswith("C:\\") and not d.startswith("{HOME}"):
        #             pass
        #         elif not os.path.isdir(d):
        #             d = self.validate_and_set_directory(d, override=True)
        #             self.directories[i] = d if d is None else os.path.normpath(os.path.realpath(d))
        #     except Exception as e:
        #         pass
        #     i += 1

        self.coqui_tts_model = tuple(self.coqui_tts_model)


    def validate_and_set_directory(self, key, override=False):
        loc = key if override else self.dict[key]
        if loc and loc.strip() != "":
            if "{HOME}" in loc:
                loc = loc.strip().replace("{HOME}", os.path.expanduser("~"))
            if not sys.platform == "win32" and "\\" in loc:
                loc = loc.replace("\\", "/")
            if not os.path.isdir(loc):
                raise Exception(f"Invalid location provided for {key}: {loc}")
            return loc
        return None

    def validate_and_set_filepath(self, key):
        filepath = self.dict[key]
        if filepath and filepath.strip() != "":
            if "{HOME}" in filepath:
                filepath = filepath.strip().replace("{HOME}", os.path.expanduser("~"))
            elif not os.path.isfile(filepath):
                try_path = os.path.join(configs_dir, filepath)
                filepath = try_path
            if not os.path.isfile(filepath):
                raise Exception(f"Invalid location provided for {key}: {filepath}")
            return filepath
        return None

    def set_directories(self, *directories):
        for directory in directories:
            try:
                setattr(self, directory, self.validate_and_set_directory(directory))
            except Exception as e:
                Utils.log_yellow(e)
                Utils.log_yellow(f"Failed to set {directory} from config.json file. Ensure the key is set.")

    def set_filepaths(self, *filepaths):
        for filepath in filepaths:
            try:
                setattr(self, filepath, self.validate_and_set_filepath(filepath))
            except Exception as e:
               Utils.log_yellow(e)
               Utils.log_yellow(f"Failed to set {filepath} from config.json file. Ensure the key is set.")

    def set_values(self, type, *names):
        for name in names:
            if type:
                try:
                    setattr(self, name, type(self.dict[name]))
                except Exception as e:
                    Utils.log_red(e)
                    Utils.log_yellow(f"Failed to set {name} from config.json file. Ensure the value is set and of the correct type.")
            else:
                try:
                    setattr(self, name, self.dict[name])
                except Exception as e:
                    Utils.log_red(e)
                    Utils.log_yellow(f"Failed to set {name} from config.json file. Ensure the key is set.")


config = Config()
