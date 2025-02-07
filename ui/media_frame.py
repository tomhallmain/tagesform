import os
import platform
import warnings
import tkinter as tk
import time

from tkinter import Canvas
from tkinter.ttk import Frame, Scrollbar
from PIL import Image, ImageTk

# try:
#     from pillow_heif import register_heif_opener
#     register_heif_opener()
# except ImportError:
#     print("Failed to import HEIF library, HEIC images will not be viewable!")

# try:
#     import pillow_avif
# except ImportError:
#     print("Failed to import AVIF library, AVIF images will not be viewable!")

import vlc

from utils.config import config
from utils.utils import Utils

class VideoUI:
    def __init__(self, filepath):
        self.filepath = filepath
        self.active = False


def scale_dims(dims, max_dims, maximize=False):
    x = dims[0]
    y = dims[1]
    max_x = max_dims[0]
    max_y = max_dims[1]
    if x <= max_x and y <= max_y:
        if maximize:
            if x < max_x:
                return (int(x * max_y/y), max_y)
            elif y < max_y:
                return (max_x, int(y * max_x/x))
        return (x, y)
    elif x <= max_x:
        return (int(x * max_y/y), max_y)
    elif y <= max_y:
        return (max_x, int(y * max_x/x))
    else:
        x_scale = max_x / x
        y_scale = max_y / y
        if x_scale < y_scale:
            return (int(x * x_scale), int(y * x_scale))
        else:
            return (int(x * y_scale), int(y * y_scale))


class ResizingCanvas(Canvas):
    '''
    Create a Tk Canvas that auto-resizes its components.
    '''

    def __init__(self, parent, **kwargs):
        Canvas.__init__(self, parent, **kwargs)
        self.bind("<Configure>", self.on_resize)
        self.parent = parent
        self.height = parent.winfo_height()
        self.width = parent.winfo_width() * 9/10
        self.imagetk = None

    def reset_sizes(self):
        self.xview_moveto(0)
        self.yview_moveto(0)
        self.height = self.parent.winfo_height()
        self.width = self.parent.winfo_width() * 9/10

    def on_resize(self, event):
        # determine the ratio of old width/height to new width/height
        wscale = float(event.width)/self.width
        hscale = float(event.height)/self.height
        self.width = event.width
        self.height = event.height
        # resize the canvas
        self.config(width=self.width, height=self.height)
        # rescale all the objects tagged with the "all" tag
        self.scale("all", 0, 0, wscale, hscale)

    def get_size(self):
        return (self.width, self.height)

    def get_center_coordinates(self):
        return (self.width/2, (self.height)/2)

    def create_image_center(self, img):
        return self.create_image(self.get_center_coordinates(), image=img, anchor="center", tags=("_"))

    def clear_image(self):
        self.delete("_")

class AutoScrollbar(Scrollbar):
    """ A scrollbar that hides itself if it's not needed. Works only for grid geometry manager """
    def set(self, lo, hi):
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.grid_remove()
        else:
            self.grid()
            Scrollbar.set(self, lo, hi)

    def pack(self, **kw):
        raise tk.TclError('Cannot use pack with the widget ' + self.__class__.__name__)

    def place(self, **kw):
        raise tk.TclError('Cannot use place with the widget ' + self.__class__.__name__)

class MediaFrame(Frame):
    """ Display and zoom image, display other media """
    def __init__(self, master, fill_canvas=False):
        """ Initialize the ImageFrame """
        Frame.__init__(self, master)

        # VLC player controls
        self.vlc_instance = vlc.Instance()
        self.vlc_media_player = self.vlc_instance.media_player_new()
        self.vlc_media = None

        self.imscale = 1.0  # scale for the canvas image zoom, public for outer classes
        self.path = "."  # path to the image, should be public for outer classes
        self.do_grid(row=0, column=1)
        # Create canvas and bind it with scrollbars. Public for outer classes
        self.canvas = ResizingCanvas(self, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky='nswe')
        self.canvas.update()  # wait till canvas is created
        self.container = self.canvas.create_rectangle((0, 0, 1400, 800), width=0)
#        print(self.canvas.get_size())

        # Bind events to the Canvas
        self.canvas.bind('<Configure>', lambda event: self.__show_image())  # canvas is resized

        self.__image = None
        self.imwidth = 0
        self.imheight = 0
        self.fill_canvas = fill_canvas
        self.__min_side = min(self.imwidth, self.imheight)  # get the smaller image side
        # Create image pyramid
        self.__pyramid = None
        self.__ratio = 1.0
        self.__curr_img = 0  # current image from the pyramid
        self.__scale = self.imscale * self.__ratio  # image pyramide scale
        self.__reduction = 2  # reduction degree of image pyramid
        # self.focus()  # set focus on the canvas
        self.master.update()
        self.image_displayed = False
        self.mousewheel_bound = False

    def set_background_color(self, background_color):
        self.canvas.config(bg=background_color)

    def video_display(self):
        self.ensure_video_frame()
        self.vlc_media = self.vlc_instance.media_new(self.path)
        self.vlc_media_player.set_media(self.vlc_media)
        if self.vlc_media_player.play() == -1:
            raise Exception("Failed to play video")

    def close(self):
        self.video_stop()

    def video_stop(self):
        self.vlc_media_player.stop()

    def video_pause(self):
        self.vlc_media_player.pause()

    def video_take_screenshot(self):
        self.vlc_media_player.take_snapshot()

    def video_seek(self, pos):
        self.vlc_media_player.set_position(pos)

    def ensure_video_frame(self):
        # set the window id where to render VLC's video output
        if platform.system() == 'Windows':
            self.vlc_media_player.set_hwnd(self.winfo_id())
        else:
            self.vlc_media_player.set_xwindow(self.winfo_id()) # this line messes up windows

    def show_video(self, path):
            path_lower = path.lower()
            if any([path_lower.endswith(ext) for ext in config.video_types]):
                self.clear()
                self.__image = VideoUI(path)
                self.video_display()

    def show_image(self, path):
        if (isinstance(self.__image, VideoUI)):
            self.video_stop()
        if config.show_videos_in_main_window:
            self.show_video(path)
            return
        self.path = path
        if path is None or path == "." or path.strip() == '' or not os.path.exists(path):
            self.clear()
            return

        self.imscale = 1.0
        self.__huge = False  # huge or not
        with warnings.catch_warnings():  # suppress DecompressionBombWarning
            warnings.simplefilter('ignore')
            try:
                self.__image = Image.open(self.path)  # open image, but down't load it
            except Exception as e:
                if "truncated" in str(e):
                    time.sleep(0.25) # If the image was just created in the directory, it's possible it's still being filled with data
                    self.__image = Image.open(self.path)  # open image, but down't load it
                else:
                    raise e
        self.imwidth, self.imheight = self.__image.size  # public for outer classes
        self.container = self.canvas.create_rectangle((0, 0, self.imwidth, self.imheight), width=0)
        self.__show_image()
        # self.focus()  # set focus on the canvas

    def focus(self, refresh_image=False):   # set focus on the canvas
        self.canvas.focus_set()
        if refresh_image:
            self.show_image(self.path)

    def clear(self) -> None:
        if self.__image is not None and self.canvas is not None:
            if (isinstance(self.__image, VideoUI)):
               self.video_stop()
            self.canvas.clear_image()
            self.master.update()

    def release_media(self):
        if self.__pyramid is not None:
            if self.__image is not None:
                if (isinstance(self.__image, VideoUI)):
                    self.video_stop()
                else:
                    self.__image.close()

    def redraw_figures(self):
        """ Dummy function to redraw figures in the children classes """
        pass

    def do_grid(self, **kw):
        """ Put CanvasImage widget on the parent widget """
        self.grid(**kw)  # place CanvasImage widget on the grid
        self.grid(sticky='nswe')  # make frame container sticky
        self.rowconfigure(0, weight=1)  # make canvas expandable
        self.columnconfigure(0, weight=1)

    def pack(self, **kw):
        """ Exception: cannot use pack with this widget """
        raise Exception('Cannot use pack with the widget ' + self.__class__.__name__)

    def place(self, **kw):
        """ Exception: cannot use place with this widget """
        raise Exception('Cannot use place with the widget ' + self.__class__.__name__)

    def __show_image(self):
        if self.path is None or self.path == ".":
            return
        imagetk = self.get_image_to_fit(self.path)
        imageid = self.canvas.create_image_center(imagetk)
        self.canvas.reset_sizes()
        self.canvas.lower(imageid)  # set image into background
        self.canvas.imagetk = imagetk  # keep an extra reference to prevent garbage-collection
        self.image_displayed = True

    def get_image_to_fit(self, filename) -> ImageTk.PhotoImage:
        '''
        Get the object required to display the image in the UI.
        '''
        img = Image.open(filename)
#        print("TESTING")
#        print(self.canvas.get_size())
        size_float = self.canvas.get_size()
        canvas_width = int(size_float[0])
        canvas_height = int(size_float[1])
        fit_dims = scale_dims((img.width, img.height), (canvas_width, canvas_height), maximize=self.fill_canvas)
        img = img.resize(fit_dims)
        return ImageTk.PhotoImage(img)

    def __move_from(self, event):
        """ Remember previous coordinates for scrolling with the mouse """
        self.canvas.scan_mark(event.x, event.y)

    def __move_to(self, event):
        """ Drag (move) canvas to the new position """
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        self.__show_image()  # zoom tile and show it on the canvas

    def outside(self, x, y):
        """ Checks if the point (x,y) is outside the image area """
        bbox = self.canvas.coords(self.container)  # get image area
        if bbox[0] < x < bbox[2] and bbox[1] < y < bbox[3]:
            return False  # point (x,y) is inside the image area
        else:
            return True  # point (x,y) is outside the image area

    def crop(self, bbox):
        """ Crop rectangle from the image and return it """
        if self.__huge:  # image is huge and not totally in RAM
            band = bbox[3] - bbox[1]  # width of the tile band
            self.__tile[1][3] = band  # set the tile height
            self.__tile[2] = self.__offset + self.imwidth * bbox[1] * 3  # set offset of the band
            self.__image.close()
            self.__image = Image.open(self.path)  # reopen / reset image
            self.__image.size = (self.imwidth, band)  # set size of the tile band
            self.__image.tile = [self.__tile]
            return self.__image.crop((bbox[0], 0, bbox[2], band))
        else:  # image is totally in RAM
            return self.__pyramid[0].crop(bbox)

    def destroy(self):
        """ ImageFrame destructor """
        try:
            if hasattr(self, "__image"):
                self.__image.close()
            if hasattr(self, "__pyramid") and self.__pyramid:
                map(lambda i: i.close, self.__pyramid)  # close all pyramid images
                del self.__pyramid[:]  # delete pyramid list
                del self.__pyramid  # delete pyramid variable
        except Exception as e:
            print(e)
        super().destroy()


class MainWindow(Frame):
    """ Main window class """
    def __init__(self, mainframe):
        """ Initialize the main Frame """
        Frame.__init__(self, master=mainframe)
        self.master.title('Advanced Zoom v3.0')
        self.master.geometry('1400x800')  # size of the main window
        self.master.resizable(1, 1)
        self.master.columnconfigure(0, weight=1)
        self.master.columnconfigure(1, weight=9)
        self.master.rowconfigure(0, weight=1)  # make the CanvasImage widget expandable
        self.sidebar = tk.Frame(self.master)
        self.sidebar.grid(row=0, column=0)
        self.show_image_btn = tk.Button(master=self.sidebar, text="Show image", command=self.show_image)
        self.show_image_btn.grid(row=0, column=0)
        self.canvas = MediaFrame(self.master)  # create widget
        self.canvas.grid(row=0, column=1)  # show widget
        self.master.update()

    def get_file(self):
        return 'C:\\Users\\tehal\\ComfyUI\\output\\SOLID\\CUI_17009716554786131.png'
#        return filedialog.askopenfile(
#            initialdir=".", title="Set image comparison file").name


    def show_image(self):
        filepath = self.get_file()
        self.canvas.show_image(filepath)

if __name__ == "__main__":
    filename = 'C:\\Users\\tehal\\ComfyUI\\output\\SOLID\\CUI_17009715322666056.png'  # place path to your image here
    #filename = 'd:/Data/yandex_z18_1-1.tif'  # huge TIFF file 1.4 GB
    #filename = 'd:/Data/The_Garden_of_Earthly_Delights_by_Bosch_High_Resolution.jpg'
    #filename = 'd:/Data/The_Garden_of_Earthly_Delights_by_Bosch_High_Resolution.tif'
    #filename = 'd:/Data/heic1502a.tif'
    #filename = 'd:/Data/land_shallow_topo_east.tif'
    #filename = 'd:/Data/X1D5_B0002594.3FR'
    app = MainWindow(tk.Tk())
    app.mainloop()
