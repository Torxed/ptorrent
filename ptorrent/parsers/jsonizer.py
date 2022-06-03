import json
import typing
import datetime
import pathlib

def json_dumps(*args :str, **kwargs :str) -> str:
	return json.dumps(*args, **{**kwargs, 'cls': JSON})

class JsonEncoder:
	@staticmethod
	def _encode(obj :typing.Any) -> typing.Any:
		"""
		This JSON encoder function will try it's best to convert
		any archinstall data structures, instances or variables into
		something that's understandable by the json.parse()/json.loads() lib.

		_encode() will skip any dictionary key starting with an exclamation mark (!)
		"""
		if isinstance(obj, dict):
			# We'll need to iterate not just the value that default() usually gets passed
			# But also iterate manually over each key: value pair in order to trap the keys.

			copy = {}
			for key, val in list(obj.items()):
				if isinstance(val, dict):
					# This, is a EXTREMELY ugly hack.. but it's the only quick way I can think of to trigger a encoding of sub-dictionaries.
					val = json.loads(json.dumps(val, cls=JSON))
				else:
					val = JsonEncoder._encode(val)

				copy[JsonEncoder._encode(key)] = val
			return copy
		elif isinstance(obj, bytes):
			return obj.decode('UTF-8', errors='replace')
		elif hasattr(obj, '__json__'):
			return json.loads(json.dumps(obj.__json__(), cls=JSON))
		elif hasattr(obj, 'json'):
			return json.loads(json.dumps(obj.json(), cls=JSON))
		elif hasattr(obj, '__dump__'):
			return obj.__dump__()
		elif isinstance(obj, (datetime.datetime, datetime.date)):
			return obj.isoformat()
		elif isinstance(obj, (list, set, tuple)):
			return [json.loads(json.dumps(item, cls=JSON)) for item in obj]
		elif isinstance(obj, (pathlib.Path)):
			return str(obj)
		else:
			return obj

class JSON(json.JSONEncoder, json.JSONDecoder):
	"""
	A safe JSON encoder that will omit private information in dicts (starting with !)
	"""
	def _encode(self, obj :typing.Any) -> typing.Any:
		return JsonEncoder._encode(obj)

	def encode(self, obj :typing.Any) -> typing.Any:
		return super(JSON, self).encode(self._encode(obj))