from copy import deepcopy
import signal
import time
import traceback

from tkinter import messagebox, Toplevel, Frame, Label, Checkbutton, Text, StringVar, BooleanVar, Scale, END, HORIZONTAL, NW, BOTH, YES, N, E, W
import tkinter.font as fnt
from tkinter.ttk import Button, Entry, OptionMenu, Progressbar, Scale
from lib.autocomplete_entry import AutocompleteEntry, matches
from ttkthemes import ThemedTk

from utils.globals import Globals

from ui.app_actions import AppActions
from ui.app_style import AppStyle
from ui.composers_window import ComposersWindow
from ui.extensions_window import ExtensionsWindow
from ui.playlist_window import PlaylistWindow
from ui.preset import Preset
from ui.presets_window import PresetsWindow
from ui.schedules_window import SchedulesWindow
from ui.search_window import SearchWindow
from ui.track_details_window import TrackDetailsWindow
from ui.weather_window import WeatherWindow
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.job_queue import JobQueue
from utils.runner_app_config import RunnerAppConfig
from utils.temp_dir import TempDir
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._

# TODO figure out why overwrite not working

def set_attr_if_not_empty(text_box):
    current_value = text_box.get()
    if not current_value or current_value == "":
        return None
    return 

def matches_tag(fieldValue, acListEntry):
    if fieldValue and "+" in fieldValue:
        pattern_base = fieldValue.split("+")[-1]
    elif fieldValue and "," in fieldValue:
        pattern_base = fieldValue.split(",")[-1]
    else:
        pattern_base = fieldValue
    return matches(pattern_base, acListEntry)

def set_tag(current_value, new_value):
    if current_value and (current_value.endswith("+") or current_value.endswith(",")):
        return current_value + new_value
    else:
        return new_value
    
def clear_quotes(s):
    if len(s) > 0:
        if s.startswith('"'):
            s = s[1:]
        if s.endswith('"'):
            s = s[:-1]
        if s.startswith("'"):
            s = s[1:]
        if s.endswith("'"):
            s = s[:-1]
    return s

class Sidebar(Frame):
    def __init__(self, master=None, cnf={}, **kw):
        Frame.__init__(self, master=master, cnf=cnf, **kw)


class ProgressListener:
    def __init__(self, update_func):
        self.update_func = update_func

    def update(self, context, percent_complete):
        self.update_func(context, percent_complete)


class App():
    '''
    UI for Tagesform scheduler application.
    '''

    def __init__(self, master):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.progress_bar = None
        self.job_queue = JobQueue("Playlist Runs")
        self.job_queue_preset_schedules = JobQueue("Preset Schedules")
        self.runner_app_config = self.load_info_cache()
        self.config_history_index = 0
        self.fullscreen = False
        self.current_run = Run(RunConfig(placeholder=True))
        self.app_actions = AppActions(
            self.start_playback,
            self.on_closing,
            self.toast,
        )

        # Sidebar
        self.sidebar = Sidebar(self.master)
        self.sidebar.columnconfigure(0, weight=1)
        self.sidebar.columnconfigure(0, weight=1)
        self.row_counter0 = 0
        self.row_counter1 = 0
        self.sidebar.grid(column=0, row=0)

        # self.label_volume = Label(self.sidebar)
        # self.add_label(self.label_volume, _("Volume"), sticky=None, increment_row_counter=False)
        # self.volume_slider = Scale(self.sidebar, from_=0, to=100, orient=HORIZONTAL, command=self.set_volume)
        # self.set_widget_value(self.volume_slider, Globals.DEFAULT_VOLUME_THRESHOLD)
        # self.apply_to_grid(self.volume_slider, interior_column=2, sticky=W)

        self.row_counter0 += 1
        self.row_counter1 += 1

        self.run_btn = None
        self.add_button("run_btn", _("Play"), self.run, increment_row_counter=False)

        self.schedules_btn = None
        self.add_button("schedules_btn", _("Schedules"), self.open_schedules_window)

        # TODO multiselect
        # self.label_workflows = Label(self.sidebar)
        # self.add_label(self.label_workflows, _("Playlist Sort"), increment_row_counter=False)
        # self.sort_type = StringVar(master)
        # current_type = PlaylistSortType[self.runner_app_config.workflow_type].get_translation()
        # self.sort_type_choice = OptionMenu(self.sidebar, self.sort_type, current_type,
        #                                    *PlaylistSortType.get_translated_names(), command=self.set_playlist_sort_type)
        # self.apply_to_grid(self.sort_type_choice, interior_column=2, sticky=W)

        # self.extend = BooleanVar(value=self.runner_app_config.muse)
        # self.extend_choice = Checkbutton(self.sidebar, text=_('Extension'), variable=self.extend, command=self.set_extend)
        # self.apply_to_grid(self.extend_choice, sticky=W)

        self.master.bind("<Control-Return>", self.run)
        self.master.bind("<Shift-R>", self.run)
        self.master.bind("<F11>", self.toggle_fullscreen)
        self.master.bind("<Shift-F>", self.toggle_fullscreen)
        self.master.bind("<Prior>", lambda event: self.one_config_away(change=1))
        self.master.bind("<Next>", lambda event: self.one_config_away(change=-1))
        self.master.bind("<Home>", lambda event: self.first_config())
        self.master.bind("<End>", lambda event: self.first_config(end=True))
        self.master.bind("<Control-q>", self.quit)
        self.toggle_theme()
        self.master.update()
        # self.close_autocomplete_popups()

    def toggle_theme(self, to_theme=None, do_toast=True):
        if (to_theme is None and AppStyle.IS_DEFAULT_THEME) or to_theme == AppStyle.LIGHT_THEME:
            if to_theme is None:
                self.master.set_theme("breeze", themebg="black")  # Changes the window to light theme
            AppStyle.BG_COLOR = "gray"
            AppStyle.FG_COLOR = "black"
        else:
            if to_theme is None:
                self.master.set_theme("black", themebg="black")  # Changes the window to dark theme
            AppStyle.BG_COLOR = config.background_color if config.background_color and config.background_color != "" else "#053E10"
            AppStyle.FG_COLOR = config.foreground_color if config.foreground_color and config.foreground_color != "" else "white"
        AppStyle.IS_DEFAULT_THEME = (not AppStyle.IS_DEFAULT_THEME or to_theme
                                     == AppStyle.DARK_THEME) and to_theme != AppStyle.LIGHT_THEME
        self.master.config(bg=AppStyle.BG_COLOR)
        self.sidebar.config(bg=AppStyle.BG_COLOR)
        self.media_frame.set_background_color(AppStyle.BG_COLOR)
        for name, attr in self.__dict__.items():
            if isinstance(attr, Label):
                attr.config(bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
                            # font=fnt.Font(size=config.font_size))
            elif isinstance(attr, Checkbutton):
                attr.config(bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR,
                            selectcolor=AppStyle.BG_COLOR)#, font=fnt.Font(size=config.font_size))
        self.master.update()
        if do_toast:
            self.toast(f"Theme switched to {AppStyle.get_theme_name()}.")

    # def close_autocomplete_popups(self):
    #     self.lora_tags_box.closeListbox()

    def on_closing(self):
        self.store_info_cache()
        # if self.server is not None:
        #     try:
        #         self.server.stop()
        #     except Exception as e:
        #         Utils.log_yellow(f"Error stopping server: {e}")
        TempDir.cleanup()
        self.master.destroy()

    def quit(self, event=None):
        res = self.alert(_("Confirm Quit"), _("Would you like to quit the application?"), kind="askokcancel")
        if res == messagebox.OK or res == True:
            Utils.log("Exiting application")
            self.on_closing()

    def store_info_cache(self):
        if self.runner_app_config is not None:
            if app_info_cache.set_history(self.runner_app_config):
                if self.config_history_index > 0:
                    self.config_history_index -= 1
        app_info_cache.set("config_history_index", self.config_history_index)
        app_info_cache.store()

    def load_info_cache(self):
        try:
            PlaylistWindow.load_named_playlist_configs()
            SchedulesManager.set_schedules()
            self.config_history_index = app_info_cache.get("config_history_index", default_val=0)
            return app_info_cache.get_history_latest()
        except Exception as e:
            Utils.log_red(e)
            return RunnerAppConfig()

    def one_config_away(self, change=1):
        assert type(self.config_history_index) == int, "History index must be an integer"
        self.config_history_index += change
        try:
            self.runner_app_config = RunnerAppConfig.from_dict(app_info_cache.get_history(self.config_history_index))
            self.set_widgets_from_config()
            # self.close_autocomplete_popups()
        except Exception as e:
            self.config_history_index -= change

    def first_config(self, end=False):
        self.config_history_index = app_info_cache.get_last_history_index() if end else 0
        try:
            self.runner_app_config = RunnerAppConfig.from_dict(app_info_cache.get_history(self.config_history_index))
            self.set_widgets_from_config()
            # self.close_autocomplete_popups()
        except Exception as e:
            self.config_history_index = 0

    def set_default_config(self, event=None):
        self.runner_app_config = RunnerAppConfig()
        self.set_widgets_from_config()
        # self.close_autocomplete_popups()

    def set_widget_value(self, widget, value):
        if isinstance(widget, Scale):
            widget.set(float(value))
        elif isinstance(widget, Text):
            widget.delete("0.0", "end")
            widget.insert("0.0", str(value))
        else:
            widget.delete(0, "end")
            widget.insert(0, value)

    def set_widgets_from_config(self):
        if self.runner_app_config is None:
            raise Exception("No config to set widgets from")
        self.set_playlist_sort_type(self.runner_app_config.workflow_type)
        # self.set_widget_value(self.resolutions_box, self.runner_app_config.resolutions)

        self.delay.set(str(self.runner_app_config.delay_time_seconds))
        self.overwrite.set(self.runner_app_config.overwrite)
        self.muse.set(self.runner_app_config.muse)

    def set_playlist_sort_type(self, event=None, playlist_sort_type=None):
        if playlist_sort_type is None:
            playlist_sort_type = self.sort_type.get()
        self.runner_app_config.workflow_type = PlaylistSortType.get_playlist_sort_type_from_translation(playlist_sort_type).value

    def set_playback_master_strategy(self, event=None):
        self.runner_app_config.playback_master_strategy = self.playlist_strategy.get()

    def set_delay(self, event=None):
        self.runner_app_config.delay_time_seconds = self.delay.get()
        Globals.set_delay(int(self.runner_app_config.delay_time_seconds))

    def set_volume(self, event=None):
        self.runner_app_config.volume = self.volume_slider.get()
        Globals.set_volume(int(self.runner_app_config.volume))
        if (self.current_run is not None and not self.current_run.is_complete \
                and self.current_run.playback is not None):
            self.current_run.playback.set_volume()

    def set_muse(self, event=None):
        self.runner_app_config.muse = self.muse.get()

    def set_extend(self, event=None):
        self.runner_app_config.extend = self.extend.get()

    def destroy_progress_bar(self):
        if self.progress_bar is not None:
            self.progress_bar.stop()
            self.progress_bar.grid_forget()
            self.destroy_grid_element("progress_bar")
            self.progress_bar = None

    def start_playback(self, track=None, playlist_sort_type=None):
        if playlist_sort_type is not None:
            self.sort_type.set(playlist_sort_type.get_translation())
        self.run(track=track)

    def run(self, event=None, track=None):
        args, args_copy = self.get_args(track=track)

        try:
            args.validate()
        except Exception as e:
            res = self.alert(_("Confirm Run"),
                str(e) + "\n\n" + _("Are you sure you want to proceed?"),
                kind="warning")
            if res != messagebox.OK:
                return None

        def run_async(args) -> None:
            self.job_queue.job_running = True
            self.destroy_progress_bar()
            self.progress_bar = Progressbar(self.sidebar, orient=HORIZONTAL, length=300, mode='determinate')
            self.progress_bar.grid(row=9, column=2)
            self.cancel_btn.grid(row=12, column=2)
            self.text_btn.grid(row=13, column=2)
            self.extension_btn.grid(row=14, column=2)
            self.current_run = Run(args, callbacks=self.app_actions)
            self.current_run.execute()
            self.cancel_btn.grid_forget()
            self.text_btn.grid_forget()
            self.extension_btn.grid_forget()
            self.destroy_progress_bar()
            self.job_queue.job_running = False
            next_job_args = self.job_queue.take()
            if next_job_args:
                Utils.start_thread(run_async, use_asyncio=False, args=[next_job_args])

        if self.job_queue.has_pending():
            self.job_queue.add(args)
        else:
            self.runner_app_config.set_from_run_config(args_copy)
            Utils.start_thread(run_async, use_asyncio=False, args=[args])

    def update_progress_bar(self, progress, elapsed_time, total_duration):
        if self.progress_bar is not None:
            self.progress_bar['value'] = progress
            self.master.update_idletasks()  # Force update of the GUI

    def next(self, event=None) -> None:
        if not self.current_run.is_started:
            self.run()
        else:
            self.current_run.next()

    def next_grouping(self, event=None) -> None:
        if not self.current_run.is_started:
            self.run()
        else:
            self.current_run.next_grouping()

    def pause(self, event=None) -> None:
        self.current_run.pause()

    def cancel(self, event=None):
        self.current_run.cancel()

    def switch_extension(self, event=None):
        self.current_run.switch_extension()

    def get_args(self, track=None):
        self.store_info_cache()
        self.set_delay()
        # self.set_concepts_dir()
        args = RunConfig()
        args.playlist_sort_type = PlaylistSortType.get_playlist_sort_type_from_translation(self.sort_type.get())
        args.total = -1
        args.is_all_tracks, args.directories = self.get_directories()
        args.overwrite = self.overwrite.get()
        args.muse = self.muse.get()
        args.extend = self.extend.get()
        args.track = track

        args_copy = deepcopy(args)
        return args, args_copy

    def open_text(self):
        if self.current_run is None or self.current_run.is_complete or self.current_run.is_cancelled:
            return
        self.current_run.open_text()

    def start_run_from_preset(self, preset, manual=True):
        self.sort_type.set(preset.playlist_sort_type)
        # if manual:
        #     self.run_preset_schedule_var.set(False)
        self.master.update()

    def construct_preset(self, name):
        args, args_copy = self.get_args()
        self.runner_app_config.set_from_run_config(args)
        return Preset.from_runner_app_config(name, self.runner_app_config)

    # def run_preset_schedule(self, override_args={}):
    #     def run_preset_async():
    #         self.job_queue_preset_schedules.job_running = True
    #         starting_total = int(self.total.get())
    #         schedule = SchedulesWindow.current_schedule
    #         if schedule is None:
    #             raise Exception("No Schedule Selected")
    #         print(f"Running Preset Schedule: {schedule}")
    #         for preset_task in schedule.get_tasks():
    #             if not self.job_queue_preset_schedules.has_pending() or not self.run_preset_schedule_var.get() or \
    #                     (self.current_run is not None and not self.current_run.is_infinite() and self.current_run.is_cancelled):
    #                 self.job_queue_preset_schedules.cancel()
    #                 return
    #             try:
    #                 preset = PresetsWindow.get_preset_by_name(preset_task.name)
    #                 print(f"Running Preset Schedule: {preset}")
    #             except Exception as e:
    #                 self.handle_error(str(e), "Preset Schedule Error")
    #                 raise e
    #             self.set_widgets_from_preset(preset, manual=False)
    #             self.total.set(str(preset_task.count_runs if preset_task.count_runs > 0 else starting_total))
    #             self.run()
    #             # NOTE have to do some special handling here because the runs are still not self-contained,
    #             # and overwriting widget values may cause the current run to have its settings changed mid-run
    #             time.sleep(0.1)
    #             started_run_id = self.current_run.id
    #             while (self.current_run is not None and started_run_id == self.current_run.id
    #                     and not self.current_run.is_cancelled and not self.current_run.is_complete):
    #                 if not self.job_queue_preset_schedules.has_pending() or not self.run_preset_schedule_var.get():
    #                     self.job_queue_preset_schedules.cancel()
    #                     return
    #                 time.sleep(1)
    #         self.total.set(str(starting_total))
    #         self.job_queue_preset_schedules.job_running = False
    #         next_preset_schedule_args = self.job_queue_preset_schedules.take()
    #         if next_preset_schedule_args is None:
    #             self.job_queue_preset_schedules.cancel()
    #         else:
    #             self.run_preset_schedule(override_args=next_preset_schedule_args)

    #     Utils.start_thread(run_preset_async, use_asyncio=False, args=[])

    def open_composers_window(self):
        try:
            composers_window = ComposersWindow(self.master, self.app_actions)
        except Exception as e:
            Utils.log_red(f"Exception opening composers window: {e}")
            raise e

    def open_schedules_window(self):
        try:
            schedules_window = SchedulesWindow(self.master, self.app_actions)
        except Exception as e:
            Utils.log_red(f"Exception opening schedules window: {e}")
            raise e

    def open_search_window(self):
        try:
            search_window = SearchWindow(self.master, self.app_actions)
        except Exception as e:
            Utils.log_red(f"Exception opening search window: {e}")
            raise e

    def open_track_details_window(self):
        try:
            track_details_window = TrackDetailsWindow(self.master, self.app_actions)
        except Exception as e:
            Utils.log_red(f"Exception opening track details window: {e}")

    def open_extensions_window(self):
        try:
            extensions_window = ExtensionsWindow(self.master, self.app_actions)
        except Exception as e:
            Utils.log_red(f"Exception opening extensions window: {e}")

    def open_playlist_window(self):
        try:
            playlist_window = PlaylistWindow(self.master, self.app_actions)
        except Exception as e:
            Utils.log_red(f"Exception opening playlist window: {e}")

    def open_presets_window(self):
        try:
            presets_window = PresetsWindow(self.master, self.app_actions, self.construct_preset, self.start_run_from_preset)
        except Exception as e:
            Utils.log_red(f"Exception opening presets window: {e}")

    def open_weather_window(self):
        try:
            weather_window = WeatherWindow(self.master, self.app_actions)
        except Exception as e:
            Utils.log_red(f"Exception opening weather window: {e}")

    def get_directories(self):
        directories = []
        selection = self.playlist_strategy.get()
        all_dirs = config.get_subdirectories()
        if selection == "ALL_MUSIC":
            return True, list(all_dirs.keys())
        else:
            for full_path, key in all_dirs.items():
                if key == selection:
                    directories.append(full_path)
                    break
            return False, directories

    def update_track_text(self, audio_track):
        if isinstance(audio_track, str):
            title_text = audio_track
            album_text = ""
            artist_text = ""
            composer_text = ""
        else:
            title_text = _("Track: ") + audio_track.title
            album_text = (_("Album: ") + audio_track.album) if audio_track.album is not None else ""
            artist_text = (_("Artist: ") + audio_track.artist) if audio_track.artist is not None else ""
            composer_text = (_("Composer: ") + audio_track.composer) if audio_track.composer is not None else ""
        self.label_title_text["text"] = Utils._wrap_text_to_fit_length(title_text, 100)
        self.label_album_text["text"] = Utils._wrap_text_to_fit_length(album_text, 100)
        self.label_artist_text["text"]   = Utils._wrap_text_to_fit_length(artist_text, 100)
        self.label_composer_text["text"] = Utils._wrap_text_to_fit_length(composer_text, 100)
        self.master.update()

    def update_next_up_text(self, next_up_text, no_title=False):
        if next_up_text is None or next_up_text.strip() == "":
            next_up_text = ""
        elif not no_title:
            next_up_text = _("Next Up: ") + next_up_text
        text = Utils._wrap_text_to_fit_length(next_up_text[:500], 90)
        self.label_next_up["text"]  = text
        self.master.update()

    def update_previous_track_text(self, previous_track_text):
        if previous_track_text is None or previous_track_text.strip() == "":
            previous_track_text = ""
        else:
            previous_track_text = _("Previous Track: ") + previous_track_text
        text = Utils._wrap_text_to_fit_length(previous_track_text[:500], 90)
        self.label_previous_title["text"]   = text
        self.master.update()

    def update_spot_profile_topics_text(self, muse_text):
        text = Utils._wrap_text_to_fit_length(muse_text[:500], 90)
        self.label_muse["text"]  = text
        self.master.update()

    def update_label_extension_status(self, extension):
        text = Utils._wrap_text_to_fit_length(extension[:500], 90)
        self.label_extension_status["text"] = text
        self.master.update()

    def update_album_artwork(self, image_filepath):
        self.media_frame.show_image(image_filepath)

    def get_media_frame_handle(self):
        return self.media_frame.winfo_id()

    def toggle_fullscreen(self, event=None):
        self.fullscreen = not self.fullscreen
        self.master.attributes("-fullscreen", self.fullscreen)
        self.sidebar.grid_remove() if self.fullscreen and self.sidebar.winfo_ismapped() else self.sidebar.grid()

    def alert(self, title, message, kind="info", hidemain=True) -> None:
        if kind not in ("error", "warning", "info"):
            raise ValueError("Unsupported alert kind.")

        if kind == "error":
            Utils.log_red(f"Alert - Title: \"{title}\" Message: {message}")
        elif kind == "warning":
            Utils.log_yellow(f"Alert - Title: \"{title}\" Message: {message}")
        else:
            Utils.log(f"Alert - Title: \"{title}\" Message: {message}")

        show_method = getattr(messagebox, "show{}".format(kind))
        return show_method(title, message)

    def handle_error(self, error_text, title=None, kind="error"):
        traceback.print_exc()
        if title is None:
            title = _("Error")
        self.alert(title, error_text, kind=kind)

    def toast(self, message):
        Utils.log("Toast message: " + message)

        # Set the position of the toast on the screen (top right)
        width = 300
        height = 100
        x = self.master.winfo_screenwidth() - width
        y = 0

        # Create the toast on the top level
        toast = Toplevel(self.master, bg=AppStyle.BG_COLOR)
        toast.geometry(f'{width}x{height}+{int(x)}+{int(y)}')
        self.container = Frame(toast, bg=AppStyle.BG_COLOR)
        self.container.pack(fill=BOTH, expand=YES)
        label = Label(
            self.container,
            text=message,
            anchor=NW,
            bg=AppStyle.BG_COLOR,
            fg=AppStyle.FG_COLOR,
            font=('Helvetica', 12)
        )
        label.grid(row=1, column=1, sticky="NSEW", padx=10, pady=(0, 5))
        
        # Make the window invisible and bring it to front
        toast.attributes('-topmost', True)
#        toast.withdraw()

        # Start a new thread that will destroy the window after a few seconds
        def self_destruct_after(time_in_seconds):
            time.sleep(time_in_seconds)
            label.destroy()
            toast.destroy()
        Utils.start_thread(self_destruct_after, use_asyncio=False, args=[2])

    def apply_to_grid(self, component, sticky=None, pady=0, interior_column=0, row=-1, column=0, increment_row_counter=True, columnspan=None):
        if row == -1:
            row = self.row_counter0 if column == 0 else self.row_counter1
        if sticky is None:
            if columnspan is None:
                component.grid(column=interior_column, row=row, pady=pady)
            else:
                component.grid(column=interior_column, row=row, pady=pady, columnspan=columnspan)
        else:
            if columnspan is None:
                component.grid(column=interior_column, row=row, sticky=sticky, pady=pady)
            else:
                component.grid(column=interior_column, row=row, sticky=sticky, pady=pady, columnspan=columnspan)
        if increment_row_counter:
            if column == 0:
                self.row_counter0 += 1
            else:
                self.row_counter1 += 1

    def add_label(self, label_ref, text, sticky=W, pady=0, row=-1, column=0, columnspan=None, increment_row_counter=True):
        label_ref['text'] = text
        self.apply_to_grid(label_ref, sticky=sticky, pady=pady, row=row, column=column, columnspan=columnspan, increment_row_counter=increment_row_counter)

    def add_button(self, button_ref_name, text, command, sidebar=True, interior_column=0, increment_row_counter=True):
        if getattr(self, button_ref_name) is None:
            master = self.sidebar if sidebar else self.prompter_config_bar
            button = Button(master=master, text=text, command=command)
            setattr(self, button_ref_name, button)
            button
            self.apply_to_grid(button, column=(0 if sidebar else 1), interior_column=interior_column, increment_row_counter=increment_row_counter)

    def new_entry(self, text_variable, text="", width=55, sidebar=True, **kw):
        master = self.sidebar if sidebar else self.prompter_config_bar
        return Entry(master, text=text, textvariable=text_variable, width=width, font=fnt.Font(size=8), **kw)

    def destroy_grid_element(self, element_ref_name):
        element = getattr(self, element_ref_name)
        if element is not None:
            element.destroy()
            setattr(self, element_ref_name, None)
            self.row_counter0 -= 1


if __name__ == "__main__":
    try:
        # assets = os.path.join(os.path.dirname(os.path.realpath(__file__)), "assets")
        root = ThemedTk(theme="black", themebg="black")
        root.title(_(" Muse "))
        #root.iconbitmap(bitmap=r"icon.ico")
        # icon = PhotoImage(file=os.path.join(assets, "icon.png"))
        # root.iconphoto(False, icon)
        root.geometry("1200x600")
        # root.attributes('-fullscreen', True)
        root.resizable(1, 1)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        # Graceful shutdown handler
        def graceful_shutdown(signum, frame):
            Utils.log("Caught signal, shutting down gracefully...")
            app.on_closing()
            exit(0)

        # Register the signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, graceful_shutdown)
        signal.signal(signal.SIGTERM, graceful_shutdown)

        app = App(root)
        root.mainloop()
        exit()
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
