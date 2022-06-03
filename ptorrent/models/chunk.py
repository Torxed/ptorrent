import typing
import hashlib
import urllib.request
import urllib.error
import multiprocessing
import traceback
import sys
import http.client
import threading
import time
from dataclasses import dataclass
from .torrent import Torrent
from .seeders import Priority, Peer

class Reader(threading.Thread):
	def __init__(self, func):
		self.func = func
		self.data = None
		threading.Thread.__init__(self)
		self.start()

	def run(self):
		try:
			self.data = self.func()
		except Exception as error:
			pass

@dataclass
class Chunk:
	torrent: Torrent
	index: int
	expected_hash :bytes
	data :bytes
	actual_hash :typing.Optional[bytes] = None

	def __repr__(self) -> str:
		return f"Chunk(torrent={self.torrent}, index={self.index}, expected_hash={self.expected_hash}, actual_hash={self.actual_hash})"

	@property
	def is_complete(self) -> bool:
		return self.actual_hash == self.expected_hash

	@property
	def is_downloaded(self) -> bool:
		return True

@dataclass
class BrokenChunk:
	torrent: Torrent
	index: int
	expected_hash :bytes
	data :typing.Optional[bytes] = None
	actual_hash :typing.Optional[bytes] = None
	_broken_download = False

	def __repr__(self) -> str:
		return f"BrokenChunk(torrent={self.torrent}, index={self.index}, expected_hash={self.expected_hash}, actual_hash={self.actual_hash}, downloaded={self.is_downloaded})"

	@property
	def is_complete(self) -> bool:
		return self.actual_hash == self.expected_hash

	@property
	def is_downloaded(self) -> bool:
		if self._broken_download:
			return True

		if self.data is None:
			return False

		return True

	def download(self, torrent_chunks, torrent_peers):
		prio, peer = self.torrent.get_fastest_peer(torrent_peers)

		start = int(self.index * self.torrent.info.piece_length)
		end = int(start + self.torrent.info.piece_length)-1

		if urllib.parse.urlparse(peer.target).scheme:
			if peer.target[-1] == '/':
				peer.target += self.torrent.info.name.decode('UTF-8', errors='replace')

			print(f"Downloading {self} via {peer.target}")

			request = urllib.request.Request(peer.target)
			request.headers['Range'] = f"bytes={start}-{end}"
			
			try:
				con_start = time.time()
#				print(f"Con opening at {con_start}")
				handle = urllib.request.urlopen(request, timeout=2)
				con_end = time.time()
#				print(f"Con open at {con_end}")

				dl_started = time.time()
#				print(f"Dl started at {dl_started}")
				reader = Reader(handle.read)
				while reader.is_alive():
					if time.time() - dl_started > 2:
						raise TimeoutError(f"Could not read data in timely fashion.")
					time.sleep(0.0001)

				if reader.data is None:
					raise TimeoutError(f"Could not read data in timely fashion.")

				dl_ended = time.time()
#				print(f"Dl finished at {dl_ended}")
				self.torrent.update_priority(
					peers_queue=torrent_peers,
					priority=Priority(connectivity=con_end - con_start, chunk_speed=dl_ended - dl_started),
					peer=peer
				)

				self.data = reader.data
				self.actual_hash = hashlib.sha1(self.data).digest()

#				print(f'{self} Finished downloading at connectivity={con_end - con_start}, chunk_speed={dl_ended - dl_started}')
			except http.client.IncompleteRead:
				print(f"IncompleteRead")
				self._broken_download = True
			except urllib.error.HTTPError as error:
				print(f"HTTPError: {error}")
				self._broken_download = True
			except urllib.error.URLError as error:
				print(f"URLError on {peer.target}: {error}")
				self._broken_download = True
			except TimeoutError:
				self._broken_download = True
			except http.client.RemoteDisconnected:
				self._broken_download = True
# 			except Exception as error:
# 				print(f"Error: {error}")
# 				self._broken_download = True
# 
# 				try:
# 					exc_info = sys.exc_info()
# 					traceback_string = ''.join(traceback.format_stack(exc_info))
# 				except AttributeError:
# 					traceback_string = ''#''.join(traceback.format_stack())
# 
# 				print(f"{self} could not download the data from {peer.target}: {error} {traceback_string}")

		print(f'Putting {self} in queue {torrent_chunks}')
		if self.is_complete:
			torrent_chunks.put(
				Chunk(
					torrent=self.torrent,
					index=self.index,
					expected_hash=self.expected_hash,
					data=self.data,
					actual_hash=self.actual_hash
				)
			)
			print('-- Empty:', torrent_chunks.empty())
		else:
			print(f"No conversion needed.")
			torrent_chunks.put(self)

		return self