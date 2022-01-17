import shutil
from os import stat
from pathlib import Path

from .baseclass import ModelDatabase


class LocalDirectoryDatabase(ModelDatabase):
    # Files are all stored in the same directory
    # Assuming filenames connected to a model are named modelname + extension
    def __init__(self, path='.', file_extension='.mod'):
        path = Path(path)
        if not path.exists():
            path.mkdir(parents=True)
        self.path = path.resolve()
        self.file_extension = file_extension

    def store_local_file(self, model, path):
        if Path(path).is_file():
            shutil.copy2(path, self.path)

    def retrieve_local_files(self, name, destination_path):
        # Retrieve all files stored for one model
        files = self.path.glob(f'{name}.*')
        for f in files:
            shutil.copy2(f, destination_path)

    def retrieve_file(self, name, filename):
        # Return path to file
        path = self.path / filename
        if path.is_file() and stat(path).st_size > 0:
            return path
        else:
            raise FileNotFoundError(f"Cannot retrieve {filename} for {name}")

    def get_model(self, name):
        filename = name + self.file_extension
        path = self.path / filename
        from pharmpy.model import Model

        try:
            model = Model.create_model(path)
        except FileNotFoundError:
            raise KeyError('Model cannot be found in database')
        model.database = self
        model.read_modelfit_results()
        return model

    def __repr__(self):
        return f"LocalDirectoryDatabase({self.path})"


class LocalModelDirectoryDatabase(LocalDirectoryDatabase):
    def store_local_file(self, model, path):
        if Path(path).is_file():
            destination = self.path / model.name
            if not destination.is_dir():
                destination.mkdir(parents=True)
            shutil.copy2(path, destination)

    def retrieve_local_files(self, name, destination_path):
        path = self.path / name
        files = path.glob('*')
        for f in files:
            shutil.copy2(f, destination_path)

    def retrieve_file(self, name, filename):
        # Return path to file
        path = self.path / name / filename
        if path.is_file() and stat(path).st_size > 0:
            return path
        else:
            raise FileNotFoundError(f"Cannot retrieve {filename} for {name}")

    def get_model(self, name):
        filename = name + self.file_extension
        path = self.path / name / filename
        from pharmpy.model import Model

        model = Model.create_model(path)
        model.database = self
        model.read_modelfit_results()
        return model

    def __repr__(self):
        return f"LocalModelDirectoryDatabase({self.path})"
