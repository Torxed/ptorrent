import random
import typing
from dataclasses import dataclass

@dataclass
class Priority:
	connectivity :float
	chunk_speed :float

	def __hash__(self):
		return hash((self.chunk_speed, self.connectivity))

@dataclass
class Peer:
	target :str

@dataclass
class Peers:
	peers :typing.Optional[typing.Dict[Priority, typing.List[Peer]]] = None

	def add_peer(self, priority :Priority, peer :Peer):
		if not priority in self.peers:
			self.peers[priority] = []

		self.peers[priority].append(peer)

	def __iter__(self):
		for priority in self.peers:
			yield priority

	def __setitem__(self, key, val):
		if type(key) != Priority or (type(val) != Peer and type(val) != list):
			raise ValueError(f"'Peers[key] = val' requires that key is Priority() not {type(key)}, and val being Peer()/list() not {type(val)}.")

		if key not in self.peers:
			if type(val) != list:
				self.peers[key] = []
			else:
				self.peers[key] = val
		elif type(val) == list:
			self.peers[key] = val

		elif val not in self.peers[key]:
			self.peers[key].append(val)

	def __getitem__(self, key):
		return self.peers[key]

	def keys(self):
		return self.peers.keys()

	def items(self):
		return self.peers.items()

	def init(self):
		self.peers = {}

	def get_fastest_peers(self):
		first_10 = {}
		# Sort based on download speed (chunk speed)
		for priority in sorted(self.peers.keys(), key=lambda prio: prio.chunk_speed):
			if len(self.peers[priority]):
				first_10[priority] = self.peers[priority]
				if len(first_10) == 10:
					break

		# Then sort on whoever has the highest connectivity
		for priority in sorted(first_10.keys(), key=lambda prio: prio.connectivity):
			return priority, first_10[priority]

		return None, []