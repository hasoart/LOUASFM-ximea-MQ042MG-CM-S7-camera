import json
import socket
import time
import pytest
from louasfm_camera.services.beaglebone import BoardClient, decode_message, trigger_edges


def test_current_thulium_messages_and_large_scheme():
    pulses = {f'D{i}': [[n*100, n%2] for n in range(20)] for i in range(19)}
    pulses['D2'] = [[0,1],[200,0],[600,1],[900,0]]
    packet = ('Pulses '+json.dumps(pulses)).encode()
    assert len(packet) > 1024
    task, decoded = decode_message(packet)
    assert task == 'Pulses' and decoded == pulses
    assert trigger_edges(decoded, 'D2') == [0,600]
    assert trigger_edges(decoded, 'D2','FallingEdge') == [200,900]
    assert decode_message(b'First_edge 1810.25') == ('First_edge',1810.25)
    assert decode_message(b'Cycle_finished {"t": 1810.25,"bad_cycle":false}')[1]['bad_cycle'] is False


@pytest.mark.parametrize('packet', [b'Pulses {bad', b'Pulses {"D0":[[1,0],[0,1]]}',
                                     b'Pulses {"D0":[[NaN,1]]}', b'Cycle_finished {}', b'First_edge nan'])
def test_bad_packets_rejected(packet):
    with pytest.raises((ValueError,TypeError)):
        decode_message(packet)


def test_read_only_udp_handshake_and_large_reply():
    server = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    server.bind(('127.0.0.1',0))
    server.settimeout(2)
    messages, errors = [], []
    client = BoardClient(lambda *message: messages.append(message), lambda *_: None, errors.append)
    try:
        client.connect('127.0.0.1',server.getsockname()[1])
        packet, address = server.recvfrom(65535)
        assert packet == b'Hi'
        server.sendto(b'Pulses {bad',address)
        pulses = {f'D{i}': [[0,0],[600,1],[900,0]] for i in range(19)}
        server.sendto(('Pulses '+json.dumps(pulses)).encode(), address)
        server.sendto(b'Cycle_finished {"t":1.0,"bad_cycle":false}',address)
        deadline = time.monotonic()+2
        while client.snapshot()['cycles_observed'] != 1 and time.monotonic()<deadline:
            time.sleep(0.01)
        assert client.snapshot()['pulses'] == pulses
        assert client.snapshot()['cycles_observed'] == 1
        assert errors  # Bad packet did not kill the receiver.
        client.close()
        assert server.recvfrom(65535)[0] == b'Close'
        assert not client.thread
    finally:
        client.close()
        server.close()
