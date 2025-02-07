import os
import shutil
import tempfile

from utils.utils import Utils

class TempDir:
    prefix = "tmp_tagesform_"
    temporary_directory_parent = tempfile.gettempdir()
    open_directories = {}

    @staticmethod
    def get(prefix=prefix):
        if prefix not in TempDir.open_directories:
            temp_dir = TempDir(prefix)
            TempDir.open_directories[prefix] = temp_dir
        return TempDir.open_directories[prefix]

    @staticmethod
    def cleanup():
        for prefix, directory in TempDir.open_directories.items():
            try:
                shutil.rmtree(directory._temp_directory)
            except Exception as e:
                print(e)
                Utils.log_red("Failed to delete temp dir: " + directory._temp_directory)
        TempDir.open_directories = {}

    def __init__(self, prefix=prefix):
        self._prefix = prefix
        self.purge_prefix()
        self._temp_directory = os.path.join(TempDir.temporary_directory_parent, prefix + str(os.urandom(24).hex()))
        os.mkdir(self._temp_directory)

    def purge_prefix(self):
        for _dir in os.listdir(TempDir.temporary_directory_parent):
            if _dir.startswith(self._prefix):
                os.remove(os.path.join(TempDir.temporary_directory_parent, _dir))
                Utils.log("Purging stale temp dir: " + _dir)

    def get_filepath(self, filename=None):
        if filename is None or filename.strip() == "":
            return self._temp_directory
        else:
            return os.path.join(self._temp_directory, filename)

    def add_file(self, filename, file_content="", write_flags="w"):
        temp_file_path = os.path.join(TempDir.temporary_directory_parent, filename)
        with open(temp_file_path, write_flags) as f:
            f.write(file_content)
        return temp_file_path
