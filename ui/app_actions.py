

class AppActions:
    def __init__(self,
                 run_callback,
                 shutdown_callback,
                 toast_callback,
                 ):
        self.start_play_callback = run_callback
        self.shutdown_callback = shutdown_callback
        self.toast = toast_callback

