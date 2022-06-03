import typing
import pathlib
import hashlib
import random
import multiprocessing.queues
from dataclasses import dataclass

if typing.TYPE_CHECKING:
	from .chunk import Chunk, BrokenChunk

from .seeders import Peers, Priority, Peer

@dataclass
class TorrentInfo:
	length :int
	name :str
	piece_length :int
	pieces :bytes

	def __json__(self):
		return {
			'length' : self.length,
			'name' : self.name,
			'piece_length' : self.piece_length,
			'pieces' : self.pieces
		}

@dataclass
class Torrent:
	info :TorrentInfo
	# peers :multiprocessing.queues.Queue
	# chunks :multiprocessing.queues.Queue
	download_location :typing.Optional[str] = pathlib.Path('./').resolve()
	creation_date :typing.Optional[str] = None
	created_by :typing.Optional[str] = None
	comment :typing.Optional[str] = None
	url_list :typing.Optional[typing.List[str]] = None
	_url_index = 0

	def __repr__(self) -> str:
		return f"Torrent(name={self.info.name.decode('UTF-8', errors='replace')}, location={self.download_location/self.info.name.decode('UTF-8', errors='replace')})"

	def __json__(self):
		return {
			'info' : self.info,
			'creation date' : self.creation_date,
			'created by' : self.created_by,
			'comment' : self.comment,
			'url-list' : self.url_list
		}

	def close(self):
		# Close any open queues
		self.peers.close()
		self.chunks.close()

	def get_fastest_peer(self, peers_queue):
		# Pop the peer-list out from thread-safe queue
		peers = peers_queue.get()

		priority, peers_list = peers.get_fastest_peers()
		peer_index = random.randint(0, len(peers_list)-1)
		peer = peers_list.pop(peer_index)

		# Pop the peer-list back into the thread safe queue
		peers_queue.put(peers)

		return priority, peer

	def update_priority(self, peers_queue :multiprocessing.queues.Queue, priority :Priority, peer :Peer):
		# Pop the peer-list out from thread-safe queue
		peers = peers_queue.get()

		if priority not in peers:
			peers[priority] = []

		peers[priority].append(peer)

		# Pop the peer-list back into the thread safe queue
		peers_queue.put(peers)

	def set_download_location(self, path :pathlib.Path):
		self.download_location = path.expanduser().resolve()

	def verify_local_data(self) -> typing.Union['Chunk', 'BrokenChunk']:
		from .chunk import Chunk, BrokenChunk

		if (target := self.download_location / self.info.name.decode('UTF-8', errors='replace')).exists():
			with target.open('rb') as target_file:
				for _index in range(0, len(self.info.pieces), 20):
					chunk_expected_hash = self.info.pieces[_index:_index+20]
					target_data = target_file.read(self.info.piece_length)
					chunk_actual_hash = hashlib.sha1(target_data).digest()

					if chunk_expected_hash != chunk_actual_hash:
						yield BrokenChunk(torrent=self, index=_index//20, data=None, expected_hash=chunk_expected_hash, actual_hash=chunk_actual_hash)
					else:
						yield Chunk(torrent=self, index=_index//20, data=target_data, expected_hash=chunk_expected_hash, actual_hash=chunk_actual_hash)
		else:
			for _index in range(0, len(self.info.pieces), 20):
				chunk_expected_hash = self.info.pieces[_index:_index+20]
				yield BrokenChunk(torrent=self, index=_index//20, data=None, expected_hash=chunk_expected_hash, actual_hash=None)

	def next_seed(self):
		target = self.url_list[self._url_index % len(self.url_list)]
		self._url_index += 1
		return target.decode('UTF-8', errors='replace')

	def random_seeder(self):
		return random.choice(self.url_list).decode('UTF-8', errors='replace')

	def feed(self, chunks :typing.List['Chunk']):
		from .chunk import BrokenChunk

		with (self.download_location/self.info.name.decode('UTF-8', errors='replace')).open('wb') as destination_file:
			for chunk in sorted(chunks, key=lambda chunk_obj: chunk_obj.index):
				if type(chunk) == BrokenChunk:
					raise ValueError(f"Torrent.feed() can only eat Chunk(), BrokenChunk() is considered damaged goods.")
				
				destination_file.write(chunk.data)