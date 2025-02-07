import asyncio
import base64
import logging
import math
import re
import os
import shutil
import sys
import threading
import time
import unicodedata

from utils.custom_formatter import CustomFormatter

# create logger
logger = logging.getLogger("muse")
logger.setLevel(logging.DEBUG)
logger.propagate = False

# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(CustomFormatter())
logger.addHandler(ch)


class Utils:
    @staticmethod
    def long_sleep(seconds=0, extra_message=None):
        if seconds <= 0:
            return
        if seconds >= 60:
            minutes  = math.floor(seconds / 60)
            message = f"Sleeping for {minutes} minutes"
        else:
            message = f"Sleeping for {seconds} seconds"
        if extra_message is not None:
            message += f" - {extra_message}"
        Utils.log(message)
        time.sleep(seconds)

    @staticmethod
    def log(message, level=logging.INFO):
        logger.log(level, message)
    
    @staticmethod
    def log_debug(message):
        Utils.log(message, logging.DEBUG)

    @staticmethod
    def log_red(message):
        Utils.log(message, logging.ERROR)
    
    @staticmethod
    def log_yellow(message):
        Utils.log(message, logging.WARNING)

    @staticmethod
    def extract_substring(text, pattern):
        result = re.search(pattern, text)    
        if result:
            return result.group()
        return ""

    @staticmethod
    def ascii_normalize(string):
        string = str(unicodedata.normalize('NFKD', string).encode('ascii', 'ignore'))
        return string[2:-1]

    @staticmethod
    def start_thread(callable, use_asyncio=True, args=None):
        if use_asyncio:
            def asyncio_wrapper():
                asyncio.run(callable())

            target_func = asyncio_wrapper
        else:
            target_func = callable

        if args:
            thread = threading.Thread(target=target_func, args=args)
        else:
            thread = threading.Thread(target=target_func)

        thread.daemon = True  # Daemon threads exit when the main process does
        thread.start()
        return thread

    @staticmethod
    def periodic(run_obj, sleep_attr="", run_attr=None):
        def scheduler(fcn):
            async def wrapper(*args, **kwargs):
                while True:
                    asyncio.create_task(fcn(*args, **kwargs))
                    period = int(run_obj) if isinstance(run_obj, int) else getattr(run_obj, sleep_attr)
                    await asyncio.sleep(period)
                    if run_obj and run_attr and not getattr(run_obj, run_attr):
                        Utils.log(f"Ending periodic task: {run_obj.__name__}.{run_attr} = False")
                        break
            return wrapper
        return scheduler

    @staticmethod
    def open_file_location(filepath):
        if sys.platform=='win32':
            os.startfile(filepath)
        elif sys.platform=='darwin':
            subprocess.Popen(['open', filepath])
        else:
            try:
                subprocess.Popen(['xdg-open', filepath])
            except OSError:
                # er, think of something else to try
                # xdg-open *should* be supported by recent Gnome, KDE, Xfce
                raise Exception("Unsupported distribution for opening file location.")

    @staticmethod
    def string_distance(s, t):
        # create two work vectors of integer distances
        v0 = [0] * (len(t) + 1)
        v1 = [0] * (len(t) + 1)

        # initialize v0 (the previous row of distances)
        # this row is A[0][i]: edit distance from an empty s to t;
        # that distance is the number of characters to append to  s to make t.
        for i in range(len(t) + 1):
            v0[i] = i

        for i in range(len(s)):
            # calculate v1 (current row distances) from the previous row v0

            # first element of v1 is A[i + 1][0]
            # edit distance is delete (i + 1) chars from s to match empty t
            v1[0] = i + 1

            for j in range(len(t)):
                # calculating costs for A[i + 1][j + 1]
                deletion_cost = v0[j + 1] + 1
                insertion_cost = v1[j] + 1
                substitution_cost = v0[j] if s[i] == t[j] else v0[j] + 1
                v1[j + 1] = min(deletion_cost, insertion_cost, substitution_cost)
            # copy v1 (current row) to v0 (previous row) for next iteration
            v0,v1 = v1,v0
        # after the last swap, the results of v1 are now in v0
        return v0[len(t)]

    @staticmethod
    def longest_common_substring(str1, str2):
        m = [[0] * (1 + len(str2)) for _ in range(1 + len(str1))]
        longest, x_longest = 0, 0
        for x in range(1, 1 + len(str1)):
            for y in range(1, 1 + len(str2)):
                if str1[x - 1] == str2[y - 1]:
                    m[x][y] = m[x - 1][y - 1] + 1
                    if m[x][y] > longest:
                        longest = m[x][y]
                        x_longest = x
                else:
                    m[x][y] = 0
        return str1[x_longest - longest: x_longest]

    @staticmethod
    def is_similar_strings(s0, s1, do_print=False):
        l_distance = Utils.string_distance(s0, s1)
        min_len = min(len(s0), len(s1))
        if min_len == len(s0):
            weighted_avg_len = (len(s0) + len(s1) / 2) / 2
        else:
            weighted_avg_len = (len(s0) / 2 + len(s1)) / 2
        threshold = int(weighted_avg_len / 2.1) - int(math.log(weighted_avg_len))
        threshold = min(threshold, int(min_len * 0.8))
        if do_print:
            print(f"Threshold:  {threshold}, Distance: {l_distance}\ns0: {s0}\ns1: {s1}\n")
        return l_distance < threshold

    @staticmethod
    def remove_substring_by_indices(string, start_index, end_index):
        if end_index < start_index:
            raise Exception("End index was less than start for string: " + string)
        if end_index >= len(string) or start_index >= len(string):
            raise Exception("Start or end index were too high for string: " + string)
        if start_index == 0:
            Utils.log("Removed: " + string[:end_index+1])
            return string[end_index+1:]
        left_part = string[:start_index]
        right_part = string[end_index+1:]
        Utils.log("Removed: " + string[start_index:end_index+1])
        return left_part + right_part

    @staticmethod
    def split(string, delimiter=","):
        # Split the string by the delimiter and clean any delimiter escapes present in the string
        parts = []
        i = 0
        while i < len(string):
            if string[i] == delimiter:
                if i == 0 or string[i-1] != "\\":
                    parts.append(string[:i])
                    string = string[i+1:]
                    i = -1
                elif i != 0 and string[i-1] == "\\":
                    string = string[:i-1] + delimiter + string[i+1:]
            elif i == len(string) - 1:
                parts.append(string[:i+1])
            i += 1
        if len(parts) == 0 and len(string) != 0:
            parts.append(string)
        return parts

    @staticmethod
    def _wrap_text_to_fit_length(text: str, fit_length: int):
        if len(text) <= fit_length:
            return text

        if " " in text and text.index(" ") < len(text) - 2:
            test_new_text = text[:fit_length]
            if " " in test_new_text:
                last_space_block = re.findall(" +", test_new_text)[-1]
                last_space_block_index = test_new_text.rfind(last_space_block)
                new_text = text[:last_space_block_index]
                text = text[(last_space_block_index+len(last_space_block)):]
            else:
                new_text = test_new_text
                text = text[fit_length:]
            while len(text) > 0:
                new_text += "\n"
                test_new_text = text[:fit_length]
                if len(test_new_text) <= fit_length:
                    new_text += test_new_text
                    text = text[fit_length:]
                elif " " in test_new_text and test_new_text.index(" ") < len(test_new_text) - 2:
                    last_space_block = re.findall(" +", test_new_text)[-1]
                    last_space_block_index = test_new_text.rfind(
                        last_space_block)
                    new_text += text[:last_space_block_index]
                    text = text[(last_space_block_index
                                 + len(last_space_block)):]
                else:
                    new_text += test_new_text
                    text = text[fit_length:]
        else:
            new_text = text[:fit_length]
            text = text[fit_length:]
            while len(text) > 0:
                new_text += "\n"
                new_text += text[:fit_length]
                text = text[fit_length:]

        return new_text

    @staticmethod
    def get_relative_dirpath(directory, levels=1):
        # get relative dirpath from base directory
        if "/" not in directory and "\\" not in directory:
            return directory
        if "/" in directory:
            # temp = base_dir
            # if "/" == base_dir[0]:
            #     temp = base_dir[1:]
            dir_parts = directory.split("/")
        else:
            dir_parts = directory.split("\\")
        if len(dir_parts) <= levels:
            return directory
        relative_dirpath = ""
        for i in range(len(dir_parts) - 1, len(dir_parts) - levels - 1, -1):
            if relative_dirpath == "":
                relative_dirpath = dir_parts[i]
            else:
                relative_dirpath = dir_parts[i] + "/" + relative_dirpath
        return relative_dirpath

    @staticmethod
    def get_default_user_language():
        _locale = os.environ['LANG'] if "LANG" in os.environ else None
        if not _locale or _locale == '':
            if sys.platform == 'win32':
                import ctypes
                import locale
                windll = ctypes.windll.kernel32
                windll.GetUserDefaultUILanguage()
                _locale = locale.windows_locale[windll.GetUserDefaultUILanguage()]
                if _locale is not None and "_" in _locale:
                    _locale = _locale[:_locale.index("_")]
            # TODO support finding default languages on other platforms
            else:
                _locale = 'en'
        elif _locale is not None and "_" in _locale:
            _locale = _locale[:_locale.index("_")]
        return _locale

    @staticmethod
    def play_sound(sound="success"):
        if sys.platform != 'win32':
            return
        sound = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lib", "sounds", sound + ".wav")
        import winsound
        winsound.PlaySound(sound, winsound.SND_ASYNC)

    @staticmethod
    def open_file(filepath):
        if sys.platform == 'win32':
            os.startfile(filepath)
        elif sys.platform == 'darwin':
            os.system('open "%s"' % filepath)
        else:
            os.system('xdg-open "%s"' % filepath)

    @staticmethod
    def executable_available(path):
        return shutil.which(path) is not None

    @staticmethod
    def ec(s="", n=0):
        if isinstance(s, str):
            s = bytes(s, "UTF-8")
        elif not isinstance(s, bytes):
            raise TypeError("Argument must be bytes or str")
        for i in range(n):
            s = base64.b64encode(s)
        return s.decode("UTF-8")

    @staticmethod
    def dc(s="", n=0, r=True):
        if isinstance(s, str):
            if r:
                s = s[::-1]
            s = bytes(s, "UTF-8")
        elif not isinstance(s, bytes):
            raise TypeError("Argument must be bytes or str")
        for i in range(n):
            s = base64.b64decode(s)
        return s.decode("UTF-8")

    @staticmethod
    # NOTE: Maybe want to raise Exception if either existing filepath or target dir are not valid
    def move_file(existing_filepath, new_filepath, overwrite_existing=False):
        if not overwrite_existing and os.path.exists(new_filepath):
            raise Exception("File already exists: " + new_filepath)
        return shutil.move(existing_filepath, new_filepath)

    @staticmethod
    def copy_file(existing_filepath, new_filepath, overwrite_existing=False):
        if not overwrite_existing and os.path.exists(new_filepath):
            raise Exception("File already exists: " + new_filepath)
        return shutil.copy2(existing_filepath, new_filepath)

    @staticmethod
    def remove_ids(s, min_length=10, fixed_length=None, in_brackets=True):
        """
        Try to determine if a string appears to be a randomized ID following certain logic.
        """
        text = s
        # Check if the string contains at least one lowercase letter, one uppercase letter, and one digit
        if (not in_brackets or "[" in s) and (any(c.islower() for c in s) or any(c.isupper() for c in s) or any(c.isdigit() for c in s)):
            # Check if the string does not contain any spaces or special characters
            if fixed_length is None:
                regex_string = "[A-Za-z0-9_-]{" + str(min_length) + ",}"
            else:
                regex_string = "[A-Za-z0-9_-]{" + str(fixed_length) + "}"
            if in_brackets:
                regex_string = "\\[" + regex_string + "\\]"
            offset = 0
            for match in re.finditer(regex_string, text):
                maybe_id = match.group()[1:-1]
                print("Maybe id: " + maybe_id)
                if Utils.is_id(maybe_id):
                    print("is id: " + maybe_id)
                    left = text[:match.start() + offset]
                    right = text[match.end() + offset:]
                    original_len = len(maybe_id)
                    offset_change = 0
                    text = ""
                    if left is not None and left.strip() != "":
                        text += left.strip()
                    if right is not None and right.strip() != "":
                        if text != "" and text[-1] != " ":
                            text += " "
                            offset_change = 1
                        text += right.strip()
                    offset += offset_change - original_len 

        return text

    @staticmethod
    def is_id(s):
        # Calculate the frequency of uppercase letters, lowercase letters, and digits
        upper_count = sum(1 for c in s if c.isupper())
        lower_count = sum(1 for c in s if c.islower())
        digit_count = sum(1 for c in s if c.isdigit())

        if float(digit_count) / len(s) > 0.5:
            return True

        # print(f"Upper count: {upper_count}")
        # print(upper_count / len(s))
        # print(f"Lower count: {lower_count}")
        # print(lower_count / len(s))
        # print(f"Digit count: {digit_count}")
        
        # Check if the frequency of uppercase letters is at least X% and not more than Y% of the total characters
        # Check if the frequency of lowercase letters is at least X% and not more than Y% of the total characters
        # Check if the frequency of digits is at least X% and not more than Y% of the total characters

        if (0.1 <= upper_count / len(s) <= 0.9 
            and 0.1 <= lower_count / len(s) <= 0.7):

            # Check to see if there are a lot of transitions
            transitions = 0

            for i in range(len(s) - 1):
                c0 = s[i]
                c1 = s[i+1]
                if (c0.isupper() != c1.isupper()
                        or c0.isdigit() != c1.isdigit()
                        or c0.isalnum() != c1.isalnum()):
                    transitions += 1
                #     print(c0 + c1 + " < TRANSITION")
                # else:
                #     print(c0 + c1)

            if transitions > 1:
                return True
            # print(f"transitions: {transitions}, length: {len(s)}")
        return False

    @staticmethod
    def sort_dictionary(_dict, key=None):
        sorted_dict = {}
        keys_list = list(_dict.keys())
        if key:
            keys_list.sort(key=key)
        else:
            keys_list.sort()
        for key in keys_list:
            sorted_dict[key] = _dict[key]
        return sorted_dict


if __name__ == "__main__":
    import pickle
    from muse.playback_config import PlaybackConfig
    if os.path.exists("test.pkl"):
        with open("test.pkl", "rb") as f:
            data = pickle.load(f)
    else:
        data = {}
        cache = PlaybackConfig.DIRECTORIES_CACHE
        for artist_dir, sound_files in cache.items():
            artist_data = {}
            file_basenames = []
            for _file in sound_files:
                file_basenames.append(os.path.basename(_file))
            artist_data["file_basenames"] = file_basenames
            data[os.path.basename(artist_dir)] = artist_data
    pickle.dump(data, open("test.pkl", "wb"))
    
