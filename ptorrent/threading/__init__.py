import resource
import multiprocessing
from ..storage import storage

def close_all_workers():
	for worker in storage.get('workers', []):
		try:
			worker.kill()
		except:
			pass
		try:
			worker.close()
		except:
			pass

def create_worker(func, peers, chunks) -> int:
	if not 'workers' in storage:
		storage['workers'] = []

	storage['workers'].append(multiprocessing.Process(target=func, args=(chunks, peers)))

	return len(storage['workers'])

def get_number_of_workers_running():
	alive = 0
	lowest_non_started_thread = len(storage['workers'])+1
	
	for index, process in enumerate(storage['workers']):
		try:
			if process.exitcode is None and process.is_alive():
				alive += 1
			elif process.is_alive() is False and process.exitcode is None:
				if index < lowest_non_started_thread:
					lowest_non_started_thread = index
			elif process.is_alive() is False and process.exitcode is not None:
				try:
					process.join()
					process.close()
				except:
					pass
		except ValueError:
			continue

	return alive, lowest_non_started_thread if lowest_non_started_thread < len(storage['workers'])+1 else None

def start_next_worker(worker_id):
	storage['workers'][worker_id].start()

def max_threads():
	"""
	ulimit -n returns 1024
	But we can only use half of those, minus 5 for buffert.
	on a ulimit of 1024, 509 is useable.
	I don't know why, but try running:
	```python
		import time
		import resource
		from multiprocessing import Process

		def f():
			x = 1
			y = x * 2
			started = time.time()
			while time.time() - started < 5:
				pass
			return y

		max_threads = resource.getrlimit(resource.RLIMIT_OFILE)[0]
		if __name__ == '__main__':
			processes = []
			for i in range(max_threads):
				processes.append(Process(target=f))

			for index, p in enumerate(processes):
				try:
					p.start()
				except OSError:
					print(index) # This will indicate on what number we crashed
					raise(1)

			time.sleep(10)
			for p in processes:
				p.join()
	```
	"""
	return resource.getrlimit(resource.RLIMIT_OFILE)[0] // 2 - 5 # Return the soft limit