class PacketException(Exception):
    pass


class PacketConnectionClosedException(PacketException):
    pass


class PacketInitializationFailedException(PacketException):
    pass
