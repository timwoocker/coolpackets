import inspect
import socket
import struct
import threading
from inspect import isroutine
from typing import Callable, Any

import msgpack
from typeguard import check_type

from . import utils
from .logger import logger
from .exceptions import PacketInitializationFailedException, PacketConnectionClosedException


class PacketManager(type):
    registered_packets = {}

    def __new__(mcs, name, bases, *args):
        cls = super().__new__(mcs, name, bases, *args)
        alias = str(cls).encode()
        if len(bases) > 0:
            if alias in mcs.registered_packets:
                logger.warning(f"Packet {alias} already registered. (Packet: '{name}')")
            elif cls._unregistered:
                # don't register
                pass
            else:
                mcs.registered_packets[alias] = cls
                logger.info(f"Packet '{name}' registered as {alias}!")
        return cls

    def __del__(self):
        alias = str(self).encode()
        if self.__base__ is not object and alias in PacketManager.registered_packets:
            del PacketManager.registered_packets[alias]
            logger.info(f"Packet {self.__name__} un-registered!")

    def __str__(self):
        if self._alias:
            return self._alias
        return self.__name__

    @staticmethod
    def dump_packets(path: str = "./packets_dump.py", additional_imports=None):
        if additional_imports is None:
            additional_imports = []
        res = "from coolpackets import *\n" \
              "from typing import *\n"
        for additional_import in additional_imports:
            res += additional_import + "\n"

        for name, cls in PacketManager.registered_packets.items():
            if not cls._dump:
                continue
            cls_src = inspect.getsource(cls)
            for func in inspect.getmembers(cls, inspect.ismethod) + inspect.getmembers(cls, inspect.isfunction):
                if func[0] in ("encode", "decode"):
                    continue
                # remove methods if not needed for dump
                func_src = inspect.getsource(func[1])
                func_indent = utils.get_indent(func_src)
                cls_src = cls_src.replace(func_src, f"{' ' * func_indent}# [FUNC REMOVED]: {func[0]}\n")
            cls_src = utils.remove_indent(cls_src)
            cls_src = cls_src.split(":", 1)[0] + ":\n    _unregistered = True" + cls_src.split(":", 1)[1]
            res += "\n\n" + cls_src
        with open(path, 'w') as file:
            file.write(res)


class Connection:
    def __init__(self, sock: socket.socket, addr: (str, int) = None, packet_groups: set = None,
                 on_close: Callable[["Connection"], Any] = lambda conn: None):
        if packet_groups is None:
            packet_groups = set()
        self.packet_groups = packet_groups | {'*'}
        self.sock = sock
        self.addr = addr
        self.on_close = on_close
        self.closed = False
        self.lock = threading.Lock()
        self._req_id = -1
        self.response_callbacks = {}
        threading.Thread(target=self._recv).start()

    @property
    def req_id(self):
        with self.lock:
            self._req_id += 1
            self._req_id %= 256 ** 2    # 2 bytes for the request id
            if self._req_id in self.response_callbacks:
                del self.response_callbacks[self._req_id]
            return self._req_id

    def send(self, packet: "Packet", on_resp: Callable[["Packet"], Any] = None, respond_to: int = None):
        req_id = self.req_id
        req_id_data = struct.pack("!H", req_id)     # 2 bytes unsigned
        if respond_to is None:
            respond_to_data = b'\x00'
        else:
            respond_to_data = b'\x01' + struct.pack("!H", respond_to)
        packet_name = str(packet).encode()
        packet_name_len = bytes([len(packet_name)])
        packet_data = packet.encode()

        data = req_id_data + respond_to_data + packet_name_len + packet_name + packet_data
        data_len = struct.pack("!I", len(data))     # 4 bytes unsigned

        # print(f"SENDING {data_len + data} len({len(data)})")
        try:
            with self.lock:
                self.sock.sendall(data_len + data)
            if on_resp:
                self.response_callbacks[req_id] = on_resp
        except (ConnectionError, OSError) as e:
            self.close(True)
            raise PacketConnectionClosedException(e)

    def _recv_all(self, n: int) -> bytes:
        try:
            received = b''
            while len(received) < n:
                data = self.sock.recv(n - len(received))
                received += data
            return received
        except (ConnectionError, OSError) as e:
            raise PacketConnectionClosedException(e)

    def _recv(self):
        try:
            while True:
                # get packet data
                data_len = self._recv_all(4)
                packet_len = struct.unpack("!I", data_len)[0]
                packet_data = self._recv_all(packet_len)
                req_id = struct.unpack("!H", packet_data[:2])[0]  # used for response
                packet_data = packet_data[2:]

                # check if this is a response to another packet
                if packet_data[0] == 0:
                    # not a response
                    response_to = None
                    packet_data = packet_data[1:]
                else:
                    response_to = struct.unpack("!H", packet_data[1:3])[0]
                    packet_data = packet_data[3:]

                packet_type_len = packet_data[0]
                packet_type = packet_data[1:packet_type_len + 1]
                packet_msg = packet_data[packet_type_len + 1:]
                packet_class = PacketManager.registered_packets.get(packet_type)    # type: Packet

                # check if packet is valid
                if not packet_class:
                    logger.warning(f"Received unknown packet type: {packet_type}")
                    continue
                packet_group = packet_class._packet_group
                if packet_group != "*" and packet_group not in self.packet_groups:
                    logger.warning(f"Received packet with bad group: {packet_type} ({packet_group})")
                    continue

                # decode and call
                packet = packet_class.decode(packet_msg)
                packet._req_id = req_id
                packet._conn = self
                packet.on_recv()
                if response_to is not None:
                    if response_to in self.response_callbacks:
                        self.response_callbacks[response_to](packet)
        except PacketConnectionClosedException as e:
            with self.lock:
                if self.closed:
                    return
            self.close(True)

    def close(self, emit_event=False):
        with self.lock:
            self.closed = True
            self.sock.close()
            if emit_event:
                self.on_close(self)


class Packet(metaclass=PacketManager):
    _packet_group = "*"  # '*' means that all Connection objects handle this packet. Change for security reasons
    _unregistered = False   # True for dumped packets -> doesn't add them to the PacketManager
    _alias = ""   # if set, this will be sent and received (instead of the class name). Used to reduce traffic
    _dump = True    # don't dump if set to False

    _req_id = 0     # set when receiving a packet. Used for responding to a specific req_id
    # set when receiving a packet. Used for responding to a specific connection
    _conn = None    # type: Connection

    def __init__(self, **kwargs):
        try:
            public_attrs = self.public_attributes
            # check if all attrs are present in args
            for attr in public_attrs:
                if attr not in kwargs:
                    try:
                        check_type("x", None, public_attrs[attr])
                        # if Optional not present, set it to None
                        setattr(self, attr, None)
                    except TypeError:
                        raise TypeError(f"Packet '{self.__class__.__name__}' missing "
                                        f"required argument '{attr}' of type: {public_attrs[attr]}")
            # assign attributes
            for key, value in kwargs.items():
                if key not in public_attrs:
                    raise TypeError(f"Packet '{self.__class__.__name__}' got an unexpected argument: {key}")
                check_type(key, value, public_attrs[key])
                self.__setattr__(key, value)
        except TypeError as e:
            raise PacketInitializationFailedException(e)

    def __str__(self):
        if self._alias:
            return self._alias
        return self.__class__.__name__

    @property
    def public_attributes(self):
        return {key: getattr(self, key) for key, value in self.__class__.__dict__.items()
                if not key.startswith("_") and not isroutine(value)
                and getattr(self, key) is not None}     # not None

    def on_recv(self):
        pass

    def respond(self, packet: "Packet", on_resp: Callable[["Packet"], Any] = None):
        self._conn.send(packet, on_resp, self._req_id)

    def encode(self) -> bytes:
        return msgpack.packb(self.public_attributes)

    @classmethod
    def decode(cls, data: bytes):
        return cls(**msgpack.unpackb(data))
