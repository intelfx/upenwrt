#!/hint/python3

import os
import os.path as p
import http.server
import urllib.parse
import attr

from .artifact import OpenwrtArtifact
from .source import OpenwrtSource
from .operation import OpenwrtOperation


@attr.s(kw_only=True)
class UpenwrtContext:
	basedir = attr.ib()
	staticdir = attr.ib()
	cachedir = attr.ib()
	workdir = attr.ib()
	repodir = attr.ib()
	baseurl = attr.ib()
	baseurlpath = attr.ib()

	@staticmethod
	def from_args(*, basedir, baseurl):
		baseparsed = urllib.parse.urlparse(baseurl)
		# noinspection PyArgumentList
		return UpenwrtContext(
			basedir=basedir,
			staticdir=p.join(basedir, 'static'),
			cachedir=p.join(basedir, 'cache'),
			workdir=p.join(basedir, 'work'),
			repodir=p.join(basedir, 'repo'),
			baseurl=baseurl,
			baseurlpath=p.normpath(p.join('/', baseparsed.path)),
		)


class UpenwrtHTTPServer(http.server.HTTPServer):
	def __init__(self, *args, context, **kwargs):
		http.server.HTTPServer.__init__(self, *args, **kwargs)
		self.context = context


#class UpenwrtHTTPRequestHandlerFiles(http.server.SimpleHTTPRequestHandler):
#	def __init__(self, *args, **kwargs):
#		http.server.SimpleHTTPRequestHandler.__init__(self, *args, **kwargs, directory=self.context.staticdir)

class UpenwrtHTTPRequestHandlerFiles(http.server.BaseHTTPRequestHandler):
	def do_GET(self):
		try:
			with open(self.context.staticdir + self.path, 'r') as f:
				st = os.stat(f.fileno())
				data = f.read()

			for k, v in self.replacements.items():
				data = data.replace(f'@{k}@', v)

			self.send_response(200)
			self.send_header('Last-Modified', util.get_last_modified(st))
			self.send_header('Content-Type', 'text/plain;charset=utf-8')
			self.send_header('Content-Length', str(len(data)))
			self.end_headers()
			self.wfile.write(data.encode('utf-8'))
		except:
			return self.send_error_exc(500, explain=f'Internal error')


class UpenwrtHTTPRequestHandlerAPI(http.server.BaseHTTPRequestHandler):
	def do_GET(self):
		try:
			args = urllib.parse.parse_qs(self.url.query)
			print(f'GET /api/get({args})')

			# parse arguments in URL query string
			# urllib always returns arguments as arrays,
			# destructure them as we go
			target_name, = *args['target_name'],
			board_name, = *args['board_name'],
			current_release, = *args.get('current_release', None),
			current_revision, = *args.get('current_revision', None),
			target_version, = *args.get('target_version', ['snapshot']),
			pkgs = args.get('pkgs', [])
			mode, = *args.get('mode', ['build']),

			artifact = OpenwrtArtifact(
				context=self.context,
				target_name=target_name,
				version_id=target_version,
			)

			source = OpenwrtSource(
				context=self.context,
				target_name=target_name,
				release=current_release,
				revision=current_revision,
			) if (current_release or current_revision) is not None else None

			op = OpenwrtOperation(
				context=self.context,
				source=source,
				artifact=artifact,
				target_name=target_name,
				board_name=board_name,
				pkgs=pkgs,
			)

		except ValueError:
			return self.send_error_exc(500, explain=f'Bad arguments')
		except Exception:
			return self.send_error_exc(500, explain=f'Internal error parsing arguments')

		try:
			if mode == 'build':
				with op:
					output = op.build()
					f = open(output, 'rb')

				with f:
					st = os.stat(f.fileno())

					self.send_response(200)
					self.send_header('Content-Type', 'application/octet-stream')
					self.send_header('Content-Length', st.st_size)
					self.end_headers()

					shutil.copyfileobj(f, self.wfile)

			elif mode == 'list':
				with op:
					output = op.list_packages()

				self.send_response(200)
				self.send_header('Content-Type', 'text/plain;charset=utf-8')
				self.send_header('Content-Length', len(output))
				self.end_headers()

				self.wfile.write(output.encode('utf-8'))

			else:
				raise ValueError(f'Bad mode: {mode}, expected "build" or "list"')

		except Exception:
			return self.send_error_exc(500, explain=f'Internal error processing request')


class UpenwrtHTTPRequestHandler(UpenwrtHTTPRequestHandlerFiles, UpenwrtHTTPRequestHandlerAPI):
	def __init__(self, request, client_address, server, *args, **kwargs):
		self.context = server.context
		self.replacements = None
		self.error_message_format = '''%(explain)s'''
		self.error_content_type = 'text/plain;charset=utf-8'
		UpenwrtHTTPRequestHandlerFiles.__init__(self, request, client_address, server, *args, **kwargs)
		UpenwrtHTTPRequestHandlerAPI.__init__(self, request, client_address, server, *args, **kwargs)

	def send_error_exc(self, code, message=None, explain=None):
		e = sys.exc_info()
		traceback.print_exception(*e)
		return self.send_error(code=code, message=message, explain=f'{explain}:\n{"".join(traceback.format_exception(*e))}')

	def do_HEAD(self):
		return self.send_error(405)

	def do_GET(self):
		self.url = urllib.parse.urlsplit(self.path)
		assert(not self.url.scheme)
		assert(not self.url.netloc)

		path = p.relpath(self.url.path, self.context.baseurlpath)

		self.replacements = {
			'BASE_URL': self.context.baseurl,
		}

		if path == '.':
			self.path = '/README.txt'
			return UpenwrtHTTPRequestHandlerFiles.do_GET(self)

		if path == 'get':
			self.path = '/get.sh'
			self.replacements.update({
				'API_ARGS': ''
			})
			return UpenwrtHTTPRequestHandlerFiles.do_GET(self)

		if path == 'list':
			self.path = '/get.sh'
			self.replacements.update({
				'API_ARGS': "-d 'mode=list'"
			})
			return UpenwrtHTTPRequestHandlerFiles.do_GET(self)

		if path == 'api/get':
			self.path = '/api/get'
			return UpenwrtHTTPRequestHandlerAPI.do_GET(self)

		else:
			return self.send_error(404)
