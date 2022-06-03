import json
import pathlib
import math
import ptorrent
import time
import random
import signal
import os
import sys
import argparse
import multiprocessing

# https://wiki.theory.org/BitTorrentSpecification
# https://fileformats.fandom.com/wiki/Torrent_file
# http://www.bittorrent.org/beps/bep_0017.html
# https://en.wikipedia.org/wiki/Torrent_file
# http://www.bittorrent.org/beps/bep_0003.html
# http://www.bittorrent.org/beps/bep_0019.html
# https://blog.thelifeofkenneth.com/2019/09/adding-webseed-urls-to-torrent-files.html

common_parameters = argparse.ArgumentParser(description="A set of common parameters for the tooling", add_help=True)
common_parameters.add_argument("--torrent", nargs="?", type=pathlib.Path, help="Which torrent to download.", required=True)
arguments, unknown = common_parameters.parse_known_args()

def handler(signum, frame):
	ptorrent.close_all_workers()
	for uuid in ptorrent.storage['torrents']:
		try:
			ptorrent.storage['torrents'][uuid]['peers'].close()
		except:
			pass
		try:
			ptorrent.storage['torrents'][uuid]['chunks'].close()
		except:
			pass

	torrent.close()
	exit(0)
	
signal.signal(signal.SIGINT, handler)

chunks_queue = multiprocessing.Queue()
peers_queue = multiprocessing.Queue()

torrent_internal_uuid = ptorrent.load_torrent(arguments.torrent, chunks_queue, peers_queue)
torrent = ptorrent.storage['torrents'][torrent_internal_uuid]['torrent']
chunks_count = torrent.info.length / torrent.info.piece_length
chunks_h = int(chunks_count * 100) / 100


print(f"Downloading: {torrent.info.name}")
print(f"Filesize: {torrent.info.length / 1024 / 1024}MB ({torrent.info.length} bytes)")
print(f"Chunk size: {torrent.info.piece_length / 1024}KB ({torrent.info.piece_length} bytes)")
print(f"Chunks: {chunks_h}")
print(f"Download location: {pathlib.Path('~/').expanduser().resolve()}")
# print(json.dumps(torrent, cls=ptorrent.JSON, indent=4))

torrent.set_download_location(pathlib.Path('~/'))
chunks = list(torrent.verify_local_data())

for index, chunk in enumerate(chunks):
	if type(chunk) == ptorrent.BrokenChunk:
		ptorrent.create_worker(
			func=chunk.download
		)

last_output = time.time()
last_num_done = 0
for chunk_index in range(len(chunks)):
	chunk = chunks[chunk_index]

	# print(f'On: {chunk}')
	if type(chunk) == ptorrent.BrokenChunk:
		# print(f"Waiting for {chunk} to download.")
		while chunk.is_downloaded is False or chunk.is_complete is False:
			if chunk._broken_download:
				# Retry and hopefully a good peer will come along.
				# print(f"{chunk} was corrupt, re-inserting into pool.")
				# Reset the chunk so we don't get false flags
				chunk = ptorrent.BrokenChunk(torrent=chunk.torrent, index=chunk.index, expected_hash=chunk.expected_hash, data=None, actual_hash=None)
				ptorrent.create_worker(
					func=chunk.download
				)

			alive, next_worker_id = ptorrent.get_number_of_workers_running()
			if next_worker_id is not None and alive < ptorrent.max_threads():
				ptorrent.start_next_worker(next_worker_id)

			if ptorrent.storage['torrents'][torrent_internal_uuid]['chunks'].empty() is False:
				finished_chunk = ptorrent.storage['torrents'][torrent_internal_uuid]['chunks'].get()

				for _index, _chunk in list(enumerate(chunks)):
					if _chunk.index == finished_chunk.index:
						chunks = chunks[:_index] + [finished_chunk] + chunks[_index+1:]

				if finished_chunk.index == chunk.index:
					chunk = finished_chunk

			if time.time() - last_output > 1:
				done = 0
				for _chunk in chunks:
					if type(_chunk) == ptorrent.Chunk:
						done += 1

				if done != last_num_done:
					last_num_done = done
					last_output = time.time()

					print(f"{done}/{len(chunks)} has finished downloading.")

			time.sleep(0.0001)

	if time.time() - last_output > 1:
		done = 0
		for _chunk in chunks:
			if type(_chunk) == ptorrent.Chunk:
				done += 1
				
		if done != last_num_done:
			last_num_done = done
			last_output = time.time()

			print(f"{done}/{len(chunks)} has finished downloading.")

	if last_num_done > 2:
		break

# for uuid in ptorrent.storage['torrents']:
# 	peers = ptorrent.storage['torrents'][uuid]['peers'].get()
# 	for priority in sorted(peers.keys(), key=lambda prio: prio.chunk_speed):
# 		print(priority, peers[priority])

if len(chunks) == chunks_count:
 	torrent.feed(chunks)

ptorrent.close_all_workers()
torrent.close()
#if torrent.url_list:
#	for i in range(math.ceil(chunks)+1):
#		chunk_target = torrent.url_list[i % len(torrent.url_list)]
#		print(f'Downloading chunk {i} from {chunk_target}')