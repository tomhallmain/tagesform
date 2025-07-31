import asyncio
import base64
import math
import os
import re
import shutil
import sys
import threading
import time
import unicodedata
from tzlocal import get_localzone

from .logging_setup import get_logger

logger = get_logger(__name__)


class Utils:
    # Regular expression to match emoji characters
    EMOJI_PATTERN = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        # u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        # u"\U0001F680-\U0001F6FF"  # transport & map symbols
        # u"\U0001F700-\U0001F77F"  # alchemical symbols
        # u"\U0001F780-\U0001F7FF"  # Geometric Shapes
        # u"\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
        # u"\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        # u"\U0001FA00-\U0001FA6F"  # Chess Symbols
        # u"\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        u"\U00002702-\U000027B0"  # Dingbats
        # u"\U000024C2-\U0001F251"  # Enclosed characters
        "]+", flags=re.UNICODE)

    # List of valid non-emoji characters that are commonly used in filenames
    VALID_FILENAME_CHARS = {
        u"\uFF1A",  # Chinese colon (ï¼)
        u"\uFF0C",  # Chinese comma (ï¼)
        u"\u3001",  # Japanese comma (ã)
        u"\u3002",  # Japanese period (ã)
        u"\uFF01",  # Full-width exclamation mark (ï¼)
        u"\uFF1F",  # Full-width question mark (ï¼)
        u"\uFF08",  # Full-width left parenthesis (ï¼)
        u"\uFF09",  # Full-width right parenthesis (ï¼)
        u"\u3014",  # Left tortoise shell bracket (ã)
        u"\u3015",  # Right tortoise shell bracket (ã)
        u"\u3010",  # Left black lenticular bracket (ã)
        u"\u3011",  # Right black lenticular bracket (ã)
        u"\u300A",  # Left double angle bracket (ã)
        u"\u300B",  # Right double angle bracket (ã)
        u"\u3008",  # Left angle bracket (ã)
        u"\u3009",  # Right angle bracket (ã)
        u"\u300C",  # Left corner bracket (ã)
        u"\u300D",  # Right corner bracket (ã)
        u"\u300E",  # Left white corner bracket (ã)
        u"\u300F",  # Right white corner bracket (ã)
        u"\u3016",  # Left white lenticular bracket (ã)
        u"\u3017",  # Right white lenticular bracket (ã)
        u"\u3018",  # Left white tortoise shell bracket (ã)
        u"\u3019",  # Right white tortoise shell bracket (ã)
        u"\u301A",  # Left white square bracket (ã)
        u"\u301B",  # Right white square bracket (ã)
    }

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
        logger.info(message)
        time.sleep(seconds)

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
                        logger.info(f"Ending periodic task: {run_obj.__name__}.{run_attr} = False")
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
        return l_distance < threshold or (min_len > 3 and threshold < 1 and l_distance == 1)

    @staticmethod
    def remove_substring_by_indices(string, start_index, end_index):
        if end_index < start_index:
            raise Exception("End index was less than start for string: " + string)
        if end_index >= len(string) or start_index >= len(string):
            raise Exception("Start or end index were too high for string: " + string)
        if start_index == 0:
            logger.info("Removed: " + string[:end_index+1])
            return string[end_index+1:]
        left_part = string[:start_index]
        right_part = string[end_index+1:]
        logger.info("Removed: " + string[start_index:end_index+1])
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

    @staticmethod
    def get_user_timezone():
        """Get the user's system timezone using tzlocal.
        Returns a pytz timezone object."""
        try:
            return get_localzone()
        except Exception as e:
            # Fallback to UTC if we can't determine the local timezone
            import pytz
            return pytz.UTC

    @staticmethod
    def contains_emoji(text):
        """Check if text contains any emoji characters."""
        if not text:
            return False
            
        # First check if any character is in our whitelist
        for char in text:
            if char in Utils.VALID_FILENAME_CHARS:
                continue
            # If not in whitelist, check if it's an emoji
            if Utils.EMOJI_PATTERN.search(char):
                logger.info(f"Found emoji in text: {text}")
                return True
        return False

    @staticmethod
    def clean_emoji(text):
        """Remove emoji characters from text and replace with [emoji] placeholder."""
        if Utils.contains_emoji(text):
            cleaned = Utils.EMOJI_PATTERN.sub("[emoji]", text)
            logger.info(f"Cleaned emoji from text: {text} -> {cleaned}")
            return cleaned
        return text

    @staticmethod
    def count_cjk_characters(text):
        """
        Count the number of CJK characters in the given text.
        
        Args:
            text: The text to analyze
            
        Returns:
            tuple: (total_cjk_chars, dict) where dict contains counts for each script:
                  {
                      'chinese': count,
                      'japanese': count,
                      'korean': count
                  }
                  
        Note:
            CJK characters include:
            - Chinese (Han): \u4e00-\u9fff
            - Japanese (Hiragana): \u3040-\u309f
            - Japanese (Katakana): \u30a0-\u30ff
            - Korean (Hangul): \uac00-\ud7af
        """
        if not text:
            return 0, {'chinese': 0, 'japanese': 0, 'korean': 0}
            
        script_counts = {
            'chinese': 0,
            'japanese': 0,
            'korean': 0
        }
        
        for c in text:
            if '\u4e00' <= c <= '\u9fff':  # Chinese
                script_counts['chinese'] += 1
            elif '\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff':  # Japanese
                script_counts['japanese'] += 1
            elif '\uac00' <= c <= '\ud7af':  # Korean
                script_counts['korean'] += 1
                
        total_cjk = sum(script_counts.values())
        return total_cjk, script_counts

    @staticmethod
    def get_cjk_character_ratio(text, threshold_percentage=None):
        """
        Calculate the ratio of CJK characters in the given text.
        
        Args:
            text: The text to analyze
            threshold_percentage: Optional percentage threshold (0-100). If provided,
                                returns True if the ratio exceeds this threshold.
        
        Returns:
            If threshold_percentage is None:
                float: Ratio of CJK characters (0.0 to 1.0)
            If threshold_percentage is provided:
                bool: True if ratio exceeds threshold, False otherwise
                
        Note:
            CJK characters include:
            - Chinese (Han): \u4e00-\u9fff
            - Japanese (Hiragana): \u3040-\u309f
            - Japanese (Katakana): \u30a0-\u30ff
            - Korean (Hangul): \uac00-\ud7af
        """
        if not text:
            return 0.0 if threshold_percentage is None else False
            
        cjk_char_count, _ = Utils.count_cjk_characters(text)
        ratio = cjk_char_count / len(text)
        
        if threshold_percentage is not None:
            return ratio > (threshold_percentage / 100.0)
            
        return ratio

    @staticmethod
    def is_valid_filename(filename):
        # Implement the logic to check if a filename is valid
        # This is a placeholder and should be replaced with the actual implementation
        return True


