#!/hint/python3

import os
import os.path as p
import time
import calendar
import subprocess
import requests


def get_last_modified(st):
	return time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(st.st_mtime))


def parse_last_modified(s):
	return calendar.timegm(time.strptime(s, '%a, %d %b %Y %H:%M:%S GMT'))


def get_file(url, *args, dest, headers=None, **kwargs):
	headers = headers or {}

	try:
		headers.update({
			'If-Modified-Since': get_last_modified(os.stat(dest))
		})
	except FileNotFoundError as e:
		print(f'get_file(url={url}, dest={dest}): dest does not exist, proceeding')
		pass

	with requests.get(url, *args, **kwargs, headers=headers, stream=True) as r:
		r.raise_for_status()
		if r.status_code == requests.codes.not_modified:
			print(f'get_file(url={url}, dest={dest}): not modified')
			return r

		if r.status_code == requests.codes.ok and 'If-Modified-Since' in headers and 'Last-Modified' in r.headers:
			req_mtime = parse_last_modified(headers['If-Modified-Since'])
			resp_mtime = parse_last_modified(r.headers['Last-Modified'])
			if resp_mtime < req_mtime:
				print(f'get_file(url={url}, dest={dest}): remote is not new enough (Last-Modified={r.headers["Last-Modified"]}, If-Modified-Since={headers["If-Modified-Since"]})!')
				return r

		print(f'get_file(url={url}, dest={dest}): commencing download of {r.headers["Content-Length"]} bytes')
		os.makedirs(p.dirname(dest), exist_ok=True)
		with open(dest, 'wb') as f:
			for chunk in r.iter_content(chunk_size=None):
				f.write(chunk)

		print(f'get_file(url={url}, dest={dest}): done {r.headers["Content-Length"]} bytes')
		return r


def run(*args, **kwargs):
	run_kwargs = {
		'text': True,
		'check': True,
		'stdin': subprocess.DEVNULL,
		'stdout': None,
		'stderr': None,
	}
	run_kwargs.update(kwargs)

	return subprocess.run(*args, **run_kwargs)
