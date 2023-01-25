class Record:
    """
    Top level class for records.

    Create objects only by using the factory function create_record.
    """

    def __init__(self, name, raw_name, root):
        self.name = name
        self.raw_name = raw_name
        self.root = root

    @property
    def root(self):
        """Root of the parse tree"""
        return self._root

    @root.setter
    def root(self, root_new):
        self._root = root_new

    def __str__(self):
        assert self.raw_name is not None
        return self.raw_name + str(self.root)
