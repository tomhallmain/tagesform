from tkinter import Toplevel, Frame, Label, StringVar, BooleanVar, Checkbutton, LEFT, W
from tkinter.ttk import Button, Entry

from lib.tk_scroll_demo import ScrollFrame
from library_data.library_data import LibraryData, LibraryDataSearch
from ui.app_style import AppStyle
from utils.config import config
from utils.globals import PlaylistSortType
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._



class SearchWindow:
    '''
    Window to search media library.
    '''
    COL_0_WIDTH = 300
    top_level = None
    MAX_RESULTS = 200

    def __init__(self, master, app_actions, dimensions="1550x700"):

        SearchWindow.top_level = Toplevel(master, bg=AppStyle.BG_COLOR) 
        SearchWindow.top_level.geometry(dimensions)
        SearchWindow.set_title(_("Search Library"))
        self.master = SearchWindow.top_level
        self.master.resizable(True, True)
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=1)
        self.app_actions = app_actions
        self.library_data = LibraryData()
        self.library_data_search = None
        self.has_closed = False

        self.outer_frame = Frame(self.master, bg=AppStyle.BG_COLOR, width=1500)
        self.outer_frame.grid_rowconfigure(0, weight=1)
        self.outer_frame.grid_rowconfigure(0, weight=7)
        self.outer_frame.grid(row=0, column=0, sticky="nsew")

        self.results_frame = ScrollFrame(self.outer_frame, bg_color=AppStyle.BG_COLOR, width=1500)
        self.results_frame.grid(row=0, column=0, sticky="nsew")

        self.inner_frame = Frame(self.outer_frame, bg=AppStyle.BG_COLOR, width=1500)
        self.inner_frame.grid_columnconfigure(0, weight=1)
        self.inner_frame.grid_columnconfigure(1, weight=1)
        self.inner_frame.grid_columnconfigure(2, weight=1)
        self.inner_frame.grid(row=1, column=0, sticky="nsew")

        self.title_list = []
        self.album_list = []
        self.artist_list = []
        self.composer_list = []
        self.open_details_btn_list = []
        self.play_btn_list = []

        self.search_btn = None
        self.add_btn("search_btn", _("Search"), self.do_search, row=0)

        self._all_label = Label(self.inner_frame)
        self.add_label(self._all_label, "Search all fields", row=1)
        self.all = StringVar(self.inner_frame)
        self.all_entry = Entry(self.inner_frame, textvariable=self.all)
        self.all_entry.grid(row=1, column=1)
        self.all_entry.bind("<Return>", self.do_search)

        self._title_label = Label(self.inner_frame)
        self.add_label(self._title_label, "Search Title", row=2)
        self.title = StringVar(self.inner_frame)
        self.title_entry = Entry(self.inner_frame, textvariable=self.title)
        self.title_entry.grid(row=2, column=1)
        self.title_entry.bind("<Return>", self.do_search)
        self.sort_by_title_button = Button(self.inner_frame, text=_("Sort by"), command=lambda: self.sort_by("title"))
        self.sort_by_title_button.grid(row=2, column=2)

        self._album_label = Label(self.inner_frame)
        self.add_label(self._album_label, "Search Album", row=3)
        self.album = StringVar(self.inner_frame)
        self.album_entry = Entry(self.inner_frame, textvariable=self.album)
        self.album_entry.grid(row=3, column=1)
        self.album_entry.bind("<Return>", self.do_search)
        self.sort_by_album_button = Button(self.inner_frame, text=_("Sort by"), command=lambda: self.sort_by("album"))
        self.sort_by_album_button.grid(row=3, column=2)

        self._artist_label = Label(self.inner_frame)
        self.add_label(self._artist_label, "Search Artist", row=4)
        self.artist = StringVar(self.inner_frame)
        self.artist_entry = Entry(self.inner_frame, textvariable=self.artist)
        self.artist_entry.grid(row=4, column=1)
        self.artist_entry.bind("<Return>", self.do_search)
        self.sort_by_artist_button = Button(self.inner_frame, text=_("Sort by"), command=lambda: self.sort_by("artist"))
        self.sort_by_artist_button.grid(row=4, column=2)

        self._composer_label = Label(self.inner_frame)
        self.add_label(self._composer_label, "Search Composer", row=5)
        self.composer = StringVar(self.inner_frame)
        self.composer_entry = Entry(self.inner_frame, textvariable=self.composer)
        self.composer_entry.grid(row=5, column=1)
        self.composer_entry.bind("<Return>", self.do_search)
        self.sort_by_composer_button = Button(self.inner_frame, text=_("Sort by"), command=lambda: self.sort_by("composer"))
        self.sort_by_composer_button.grid(row=5, column=2)

        self._genre_label = Label(self.inner_frame)
        self.add_label(self._genre_label, "Search Genre", row=6)
        self.genre = StringVar(self.inner_frame)
        self.genre_entry = Entry(self.inner_frame, textvariable=self.genre)
        self.genre_entry.grid(row=6, column=1)
        self.genre_entry.bind("<Return>", self.do_search)
        self.sort_by_genre_button = Button(self.inner_frame, text=_("Sort by"), command=lambda: self.sort_by("get_genre"))
        self.sort_by_genre_button.grid(row=6, column=2)

        self._instrument_label = Label(self.inner_frame)
        self.add_label(self._instrument_label, "Search Instrument", row=7)
        self.instrument = StringVar(self.inner_frame)
        self.instrument_entry = Entry(self.inner_frame, textvariable=self.instrument)
        self.instrument_entry.grid(row=7, column=1)
        self.instrument_entry.bind("<Return>", self.do_search)
        self.sort_by_instrument_button = Button(self.inner_frame, text=_("Sort by"), command=lambda: self.sort_by("get_instrument"))
        self.sort_by_instrument_button.grid(row=7, column=2)

        self._form_label = Label(self.inner_frame)
        self.add_label(self._form_label, "Search Form", row=8)
        self.form  = Entry(self.inner_frame)
        self.form.grid(row=8, column=1)
        self.form.bind("<Return>", self.do_search)
        self.sort_by_form_button = Button(self.inner_frame, text=_("Sort by"), command=lambda: self.sort_by("get_form"))
        self.sort_by_form_button.grid(row=8, column=2)

        self.overwrite_cache = BooleanVar(self.inner_frame)
        self._overwrite = Checkbutton(self.inner_frame, text="Overwrite Cache", variable=self.overwrite_cache)
        self._overwrite.grid(row=9, columnspan=2)

        # self.master.bind("<Key>", self.filter_targets)
        # self.master.bind("<Return>", self.do_action)
        self.master.bind("<Escape>", self.close_windows)
        self.master.protocol("WM_DELETE_WINDOW", self.close_windows)
        self.results_frame.after(1, lambda: self.results_frame.focus_force())
        Utils.start_thread(self.do_search, use_asyncio=False)

    def do_search(self, event=None):
        all = self.all.get().strip()
        title = self.title.get().strip()
        album = self.album.get().strip()
        artist = self.artist.get().strip()
        composer = self.composer.get().strip()
        genre = self.genre.get().strip()
        instrument = self.instrument.get().strip()
        form = self.form.get().strip()
        overwrite = self.overwrite_cache.get()
        self.library_data_search = LibraryDataSearch(all, title, artist, composer, album, genre, instrument, form, SearchWindow.MAX_RESULTS)
        self.library_data.do_search(self.library_data_search, overwrite=overwrite)
        self._refresh_widgets()

    def sort_by(self, attr):
        self.library_data_search.sort_results_by(attr)
        self._refresh_widgets()

    def add_widgets_for_results(self):
        self.library_data_search.sort_results_by()
        results = self.library_data_search.get_results()
        for i in range(len(results)):
            row = i + 1
            track = results[i]

            title_label = Label(self.results_frame.viewPort)
            self.add_label(title_label, track.title, row=row, column=1, wraplength=200)
            self.title_list.append(title_label)

            artist_label = Label(self.results_frame.viewPort)
            self.add_label(artist_label, track.artist, row=row, column=2, wraplength=200)
            self.artist_list.append(artist_label)

            album_label = Label(self.results_frame.viewPort)
            self.add_label(album_label, track.album, row=row, column=3, wraplength=200)
            self.album_list.append(album_label)
            
            composer_label = Label(self.results_frame.viewPort)
            self.add_label(composer_label, track.composer, row=row, column=4, wraplength=200)
            self.composer_list.append(composer_label)

            open_details_btn = Button(self.results_frame.viewPort, text=_("Details"))
            self.open_details_btn_list.append(open_details_btn)
            open_details_btn.grid(row=row, column=5)
            def open_details_handler(event, self=self, audio_track=track):
                self.open_details(audio_track)
            open_details_btn.bind("<Button-1>", open_details_handler)

            play_btn = Button(self.results_frame.viewPort, text=_("Play"))
            self.play_btn_list.append(play_btn)
            play_btn.grid(row=row, column=6)
            def play_handler(event, self=self, audio_track=track):
                print(f"Audio track was: {audio_track}")
                self.run_play_callback(audio_track)
            play_btn.bind("<Button-1>", play_handler)

            # TODO add to playlist buttons

    def open_details(self, track):
        pass

    def run_play_callback(self, track):
        if track is None or track.is_invalid():
            raise Exception(f"Invalid track: {track}")

        playlist_sort_type = self.get_playlist_sort_type()
        self.app_actions.start_play_callback(track=track, playlist_sort_type=playlist_sort_type)

    def get_playlist_sort_type(self):
        if len(self.composer.get()) > 0:
            return PlaylistSortType.COMPOSER_SHUFFLE
        elif len(self.artist.get()) > 0:
            return PlaylistSortType.ARTIST_SHUFFLE
        elif len(self.genre.get()) > 0:
            return PlaylistSortType.GENRE_SHUFFLE
        elif len(self.instrument.get()) > 0:
            return PlaylistSortType.INSTRUMENT_SHUFFLE
        elif len(self.form.get()) > 0:
            return PlaylistSortType.FORM_SHUFFLE
        elif len(self.album.get()) > 0:
            return PlaylistSortType.ALBUM_SHUFFLE
        return PlaylistSortType.RANDOM

    def _refresh_widgets(self):
        self.clear_widget_lists()
        self.add_widgets_for_results()
        self.master.update()

    def clear_widget_lists(self):
        for label in self.title_list:
            label.destroy()
        for label in self.artist_list:
            label.destroy()
        for label in self.album_list:
            label.destroy()
        for label in self.composer_list:
            label.destroy()
        for btn in self.open_details_btn_list:
            btn.destroy()
        for btn in self.play_btn_list:
            btn.destroy()
        self.title_list = []
        self.artist_list = []
        self.album_list = []
        self.composer_list = []
        self.open_details_btn_list = []
        self.play_btn_list = []

    @staticmethod
    def set_title(extra_text):
        SearchWindow.top_level.title(_("Search") + " - " + extra_text)

    def close_windows(self, event=None):
        self.master.destroy()
        self.has_closed = True

    def add_label(self, label_ref, text, row=0, column=0, wraplength=500):
        label_ref['text'] = text
        label_ref.grid(column=column, row=row, sticky=W)
        label_ref.config(wraplength=wraplength, justify=LEFT, bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)

    def add_btn(self, button_ref_name, text, command, row=0, column=0):
        if getattr(self, button_ref_name) is None:
            button = Button(master=self.inner_frame, text=text, command=command)
            setattr(self, button_ref_name, button)
            button # for some reason this is necessary to maintain the reference?
            button.grid(row=row, column=column)

