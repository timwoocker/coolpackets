# coolpackets
A python framework for sending and receiving custom packets

This is used for an extension to Ableton Live. I will add features as I need them for that project.

Usage example:

    import socket
    import time
    from typing import Union, Optional, List

    from coolpackets.packet import Packet, Connection, PacketManager


    class MidiPacket(Packet):
        _packet_group = "mrs"
        _alias = "\x00"

        a = int
        b = Union[int, float]
        c_is_optional = Optional[int]

        def on_recv(self):
            print("RECEIVED MidiPacket!", self.a, self.b, self.c_is_optional)
            self.respond(UselessPacket(cool=["1", "2", "3"]))


    class UselessPacket(Packet):
        _alias = "useless"
        # _dump = False

        cool = List[str]

        def on_recv(self):
            print("RECEIVED UselessPacket!")

        def encode(self) -> bytes:
            return b""

        @classmethod
        def decode(cls, data: bytes):
            return cls(cool=["nice", "cool"])


    PacketManager.dump_packets("./packet_dumps/demo_packet_dump.py")


    # setup
    srv = socket.socket()
    srv.bind(('', 9056))
    srv.listen(1)

    cli = socket.socket()
    cli.connect(('localhost', 9056))
    peer, addr = srv.accept()

    conn1 = Connection(cli)
    conn2 = Connection(peer, addr, {'mrs'})

    # main logic
    pck = MidiPacket(a=3, b=7.4)
    conn1.send(pck, lambda p: print(f"RECEIVED RESPONSE: {p}"))

    # time to process packets. Usually we wouldn't just close the sockets
    time.sleep(.1)

    # cleanup
    conn1.close()
    conn2.close()
    srv.close()

    print("Done")
