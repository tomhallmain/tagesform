from copy import deepcopy
import json

class RunnerAppConfig:
    def __init__(self):
        pass

    def set_from_run_config(self, args):
        pass

    @staticmethod
    def from_dict(_dict):
        app_config = RunnerAppConfig()
        for key in _dict:
            if hasattr(app_config, key):
                setattr(app_config, key, _dict[key])
            else:
                raise Exception("Invalid property: " + str(key))
        return app_config

    def to_dict(self):
        _dict = deepcopy(self.__dict__)
        return _dict

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __hash__(self):
        class EnumsEncoder(json.JSONEncoder):
            def default(self, z):
                # if isinstance(z, ):
                #     return (str(z.name))
                # else:
                return super().default(z)
        return hash(json.dumps(self, cls=EnumsEncoder, sort_keys=True))
