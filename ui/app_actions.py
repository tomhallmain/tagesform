

class AppActions:
    def __init__(self,
                 shutdown_callback,
                 toast_callback,
                 ):
        self.shutdown_callback = shutdown_callback
        self.toast = toast_callback

