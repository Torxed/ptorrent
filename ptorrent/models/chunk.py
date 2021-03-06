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
import socket
import ssl
import logging
from dataclasses import dataclass
from .torrent import Torrent
from .seeders import Priority, Peer
from ..storage import storage
from ..logger import log

class Reader(threading.Thread):
	def __init__(self, func, chunksize):
		self.func = func
		self.chunksize = chunksize
		self.data = None
		threading.Thread.__init__(self)
		self._stop_event = threading.Event()
		self.start()

	def kill(self):
		self._stop_event.set()

	def stopped(self):
		return self._stop_event.is_set()

	def run(self):
		try:
			self.data = self.func(self.chunksize)
		except Exception as error:
			if storage['arguments'].debug:
				log(f'Could not read data: {error}', level=logging.ERROR, fg="red")
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

	def download(self):
		colors = {
			0 : "gray",
			1 : "teal",
			2 : "blue",
			3 : "magenta",
			4 : "green"
		}

		if storage['arguments'].debug:
			log(f"{self.index}: Initating download", level=logging.INFO, fg=colors[self.index % (len(colors)-1)])

		last_output = time.time()
		prio = None
		while prio is None:
			prio, peer = self.torrent.get_fastest_peer()
			time.sleep(0.0001)

			if storage['arguments'].debug and time.time() - last_output > 5:
				log(f"{self.index} still waiting for fastest available peer...", level=logging.WARNING, fg="orange")
				last_output = time.time()

		chunk_start_byte = int(self.index * self.torrent.info.piece_length)
		chunk_end_byte = int(chunk_start_byte + self.torrent.info.piece_length)-1

		if (http_schema := urllib.parse.urlparse(peer.target)).scheme:
			if http_schema.path.endswith('/') is True:
				http_schema = urllib.parse.urlparse(peer.target + self.torrent.info.name.decode('UTF-8', errors='replace'))

			if storage['arguments'].debug:
				log(f"{self.index}: Starting download of index via {http_schema}", level=logging.INFO, fg=colors[self.index % (len(colors)-1)])

			# request = urllib.request.Request(peer.target)
			# request.headers['Range'] = f"bytes={start}-{end}"
			
			try:
				con_start = time.time()
				
				if http_schema.scheme == 'https':
					handle = http.client.HTTPSConnection(*http_schema.netloc.split(':', 1), timeout=1)
				elif http_schema.scheme == 'http':
					handle = http.client.HTTPConnection(*http_schema.netloc.split(':', 1), timeout=1)
				else:
					raise ValueError(f"Unknown schema: {http_schema.scheme}")

				handle.putrequest('GET', http_schema.path)
				handle.putheader('User-Agent', f"pTorrent")
				handle.putheader('Range', f"bytes={chunk_start_byte}-{chunk_end_byte}")
				handle.endheaders()
				handle.send(b'')
				
				con_end = time.time()

				dl_started = time.time()
				if storage['arguments'].debug:
					log(f"{self.index}: Connecting took {con_end - con_start}", level=logging.INFO, fg=colors[self.index % (len(colors)-1)])

				response = handle.getresponse()
				if response.status != 206:
					raise TimeoutError(f"Wrong HTTP status code: {response.status}.")

				reader = Reader(response.read, self.torrent.info.piece_length)
				while reader.is_alive():
					if time.time() - dl_started > 1:
						reader.kill()
						break
					time.sleep(0.0001)

				if reader.data is None:
					raise TimeoutError(f"Could not read data in timely fashion.")

				dl_ended = time.time()
				if storage['arguments'].debug:
					log(f"{self.index}: Download took {dl_ended - dl_started}", level=logging.INFO, fg=colors[self.index % (len(colors)-1)])
				self.torrent.update_priority(
					priority=Priority(connectivity=con_end - con_start, chunk_speed=dl_ended - dl_started),
					peer=peer
				)

				self.data = reader.data
				self.actual_hash = hashlib.sha1(self.data).digest()
			except ssl.SSLCertVerificationError as error:
				if storage['arguments'].debug:
					log(f"{self.index} ******> {error}", level=logging.ERROR, fg="red")
				self._broken_download = True
			except socket.gaierror as error:
				if storage['arguments'].debug:
					log(f"{self.index} ******> {error}", level=logging.ERROR, fg="red")
				self._broken_download = True
			except OSError as error:
				if storage['arguments'].debug:
					log(f"{self.index} ******> {error}", level=logging.ERROR, fg="red")
				self._broken_download = True
			except http.client.IncompleteRead as error:
				if storage['arguments'].debug:
					log(f"{self.index} ******> {error}", level=logging.ERROR, fg="red")
				self._broken_download = True
			except urllib.error.HTTPError as error:
				if storage['arguments'].debug:
					log(f"{self.index} ******> {error}", level=logging.ERROR, fg="red")
				self._broken_download = True
			except TimeoutError as error:
				if storage['arguments'].debug:
					log(f"{self.index} ******> {error}", level=logging.ERROR, fg="red")
				self._broken_download = True
			except http.client.RemoteDisconnected as error:
				if storage['arguments'].debug:
					log(f"{self.index} ******> {error}", level=logging.ERROR, fg="red")
				self._broken_download = True

		if self.is_complete:
			storage['torrents'][self.torrent.uuid]['chunks'].put(
				Chunk(
					torrent=self.torrent,
					index=self.index,
					expected_hash=self.expected_hash,
					data=self.data,
					actual_hash=self.actual_hash
				)
			)
		else:
			storage['torrents'][self.torrent.uuid]['chunks'].put(self)

		return self