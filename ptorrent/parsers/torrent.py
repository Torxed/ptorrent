import pathlib
import typing
import json
import multiprocessing
import random
import uuid
from .jsonizer import JSON
from ..models import Torrent, TorrentInfo, Peers, Peer, Priority
from ..storage import storage

def torrent_data_to_string(data :bytes) -> typing.Tuple[bytes, int]:
	if data[:1].isdigit() is False:
		raise ValueError(f"torrent_data_to_string() requires first part to be digits only, got: {data[:1]}")

	_index = 0
	_index += len(string_length := data[_index:].split(b':', 1)[0])+1
	_index += len(string := data[_index:_index+int(string_length)])
	return string, _index

def torrent_data_to_integer(data :bytes) -> typing.Tuple[int, int]:
	if data[:1] != b'i':
		raise ValueError(f"torrent_data_to_integer() requires first part to be 'i', got: {data[:1]}")

	integer_end_pos = data.find(b'e')
	if integer_end_pos == -1:
		raise ValueError(f"Could not reliably determaine the end of the integer, expected b'e' at some point but could not find it.")

	integer = data[1:integer_end_pos]

	return int(integer), integer_end_pos+1

def torrent_data_to_list(data :bytes) -> typing.Tuple[int, int]:
	if data[:1] != b'l':
		raise ValueError(f"torrent_data_to_integer() requires first part to be 'l', got: {data[:1]}")

	result = []
	_index = 1
	while _index <= len(data) and data[_index:_index+1] != b'e':
		_index += len(value_length := data[_index:].split(b':', 1)[0])+1
		_index += len(value := data[_index:_index+int(value_length)])

		result.append(value)

	if data[_index:_index+1] != b'e':
		raise ValueError(f"Could not reliably determaine the end of the dictionary, expected b'e' but found {data[_index:_index+1]!r}")

	return result, _index+1

def torrent_data_to_dict(data :bytes):
	if data[:1] != b'd':
		raise ValueError(f"Data is not a torrent dictionary, expected first byte to be b'd', but got {data[:1]!r}")

	result = {}
	_index = 1
	while _index <= len(data) and data[_index:_index+1] != b'e':
		_index += len(key_length := data[_index:].split(b':', 1)[0])+1
		_index += len(key := data[_index:_index+int(key_length)])

		match (first_byte := data[_index:_index+1]):
			case b'd':
				value, _index_moved = torrent_data_to_dict(data[_index:])
			case b'l':
				value, _index_moved = torrent_data_to_list(data[_index:])
			case b'i':
				value, _index_moved = torrent_data_to_integer(data[_index:])
			case _:
				if first_byte.isdigit():
					value, _index_moved = torrent_data_to_string(data[_index:])
				else:
					raise ValueError(f"Could not interpret {first_byte}")
		_index += _index_moved

		# _index += len(value_length := data[_index:].split(b':', 1)[0])+1
		# _index += len(value := data[_index:_index+int(value_length)])

		result[key.decode('UTF-8').replace(' ', '_').replace('-', '_')] = value

	if data[_index:_index+1] != b'e':
		raise ValueError(f"Could not reliably determaine the end of the dictionary, expected b'e' but found {data[_index:_index+1]!r}")

	return result, _index+1

def parse_torrent(data :bytes) -> typing.Any:
	first_byte = data[0:1]
	if first_byte not in (b'd', b'l', b'i') and first_byte.isdigit() is False:
		raise ValueError(f"Improper encoding on torrent file staart, expected d, l, i or number but got: {first_byte!r}")

	_index = 0
	while _index <= len(data):
		match (first_byte := data[_index:_index+1]):
			case b'd':
				result, _index_moved = torrent_data_to_dict(data)
			case b'l':
				result, _index_moved = torrent_data_to_list(data)
			case b'i':
				result, _index_moved = torrent_data_to_integer(data)
			case _:
				if first_byte.isdigit():
					value, _index_moved = torrent_data_to_string(data[_index:])
				elif len(first_byte) == 0:
					break
				else:
					raise ValueError(f"Could not interpret {first_byte}")

		_index += _index_moved

	return result


def load_torrent(path :pathlib.Path, chunks :multiprocessing.queues.Queue, peers:multiprocessing.queues.Queue) -> Torrent:
	if (actual_path := path.expanduser().resolve()).exists() is False:
		raise FileNotFoundError(f"Could not locate Torrent {actual_path}")

	with actual_path.open('rb') as fh:
		data = fh.read()

	result = parse_torrent(data)

	if result.get('info'):
		result['info'] = TorrentInfo(**result['info'])

	Peers, Peer, Priority

	peer_handle = Peers()
	peer_handle.init()
	peer_list_unsorted = [*result['url_list']]

	random.shuffle(peer_list_unsorted)
	for dl_location in peer_list_unsorted:
		peer = Peer(target=dl_location.decode('UTF-8', errors='replace'))
		prio = Priority(connectivity=1, chunk_speed=1)
		peer_handle.add_peer(priority=prio, peer=peer)
	
	peers.put(peer_handle)
	uid = uuid.uuid4()
	result['uuid'] = uid

	if not 'torrents' in storage:
		storage['torrents'] = {}

	storage['torrents'][uid] = {
		'chunks' : chunks,
		'peers' : peers,
		'torrent' : Torrent(**result)
	}

	return uid
