import argparse
from copy import deepcopy
import time
import traceback

from ..services.run_config import RunConfig
from utils.temp_dir import TempDir
from ..utils.translations import I18N
from ..utils.utils import Utils

_ = I18N._


class Run:
    def __init__(self, args, callbacks=None):
        self.id = str(time.time())
        self.is_started = False
        self.is_complete = False
        self.is_cancelled = False
        self.args = args
        self.last_config = None
        self.callbacks = callbacks
        pass

    def run(self, playback_config):
        Utils.log(playback_config)
        if self.last_config and playback_config == self.last_config:
            Utils.log("\n\nConfig matches last config. Please modify it or quit.")
            return

        try:
            self.is_started = True
            # self.get_playback().run()
            TempDir.cleanup()
        except ScheduledShutdownException as e:
            TempDir.cleanup()
            if self.callbacks is not None:
                print("Shutting down main thread! Good-bye.")
                self.callbacks.shutdown_callback()
        except Exception as e:
            TempDir.cleanup()
            # self.get_library_data().reset_extension()
            raise e

        # self.last_config = deepcopy(self.get_playback()._playback_config)

    def do_workflow(self):
        # playback_config = PlaybackConfig(args=self.args, data_callbacks=self.library_data.data_callbacks)
        # self.playback = Playback(playback_config, self.callbacks, self)
        self.last_config = None

        # try:
        #     self.run(playback_config)
        # except KeyboardInterrupt:
        #     pass

    def load_and_run(self):
        try:
            self.do_workflow()
        except Exception as e:
            Utils.log(e)
            traceback.print_exc()

    def execute(self):
        self.is_complete = False
        self.is_cancelled = False
        self.load_and_run()
        self.is_complete = True

    def cancel(self):
        Utils.log("Canceling...")
        self.is_cancelled = True
        # self.get_playback().next()

def main(args):
    run = Run(args)
    run.execute()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    main(RunConfig(args))
