#!/hint/python3

import os
import os.path as p
import asyncio
import aiohttp.web
import urllib.parse
import attr
from typing import *

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


class UpenwrtHandler:
	def __init__(self, context: UpenwrtContext):
		self.context = context


	async def response_template_file(self, request: aiohttp.web.Request, file, replacements):
		with open(p.join(self.context.staticdir, file), 'r') as f:
			st = os.stat(f.fileno())
			data = f.read()

		for k, v in replacements.items():
			data = data.replace(f'@{k}@', v)

		response = aiohttp.web.Response(text=data)
		response.last_modified = st.st_mtime
		return response


	async def handle_get_readme(self, request: aiohttp.web.Request):
		replacements = {
			'BASE_URL': self.context.baseurl
		}
		print(f'GET /')
		return await self.response_template_file(request=request, file='README.txt', replacements=replacements)


	async def handle_get_sh(self, request: aiohttp.web.Request):
		replacements = {
			'BASE_URL': self.context.baseurl,
			'API_ARGS': '',
		}
		print(f'GET /get')
		return await self.response_template_file(request=request, file='get.sh', replacements=replacements)


	async def handle_list_sh(self, request: aiohttp.web.Request):
		replacements = {
			'BASE_URL': self.context.baseurl,
			'API_ARGS': "-d 'mode=list'",
		}
		print(f'GET /list')
		return await self.response_template_file(request=request, file='get.sh', replacements=replacements)


	async def handle_api_get(self, request: aiohttp.web.Request):
		args = request.query
		print(f'GET /api/get({args})')

		# read arguments from URL query string
		target_name = args['target_name']
		board_name = args['board_name']
		current_release = args.get('current_release', None)
		current_revision = args.get('current_revision', None)
		target_version = args.get('target_version', 'snapshot')
		pkgs = args.getall('pkgs', [])
		mode = args.get('mode', 'build')

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

		if mode == 'build':
			with op:
				output = op.build()
				f = open(output, 'rb')

			with f:
				st = os.stat(f.fileno())

				resp = aiohttp.web.StreamResponse()
				resp.content_type = 'application/octet-stream'
				resp.content_length = st.st_size
				resp.last_modified = st.st_mtime
				await resp.prepare(request)

				sz = 256*1024
				while True:
					chunk = f.read(sz)
					if not chunk:
						break
					await resp.write(chunk)

				return resp

		elif mode == 'list':
			with op:
				output = op.list_packages()

			return aiohttp.web.Response(text=output)

		else:
			raise ValueError(f'Bad mode: {mode}, expected "build" or "list"')


	def routes(self):
		base = self.context.baseurlpath
		return [
			aiohttp.web.get(p.join(base, ''), self.handle_get_readme),
			aiohttp.web.get(p.join(base, 'get'), self.handle_get_sh),
			aiohttp.web.get(p.join(base, 'list'), self.handle_list_sh),
			aiohttp.web.get(p.join(base, 'api/get'), self.handle_api_get, allow_head=False),
		]


class UpenwrtApp(aiohttp.web.Application):
	def __init__(self, context: UpenwrtContext):
		super().__init__()
		handler = UpenwrtHandler(context)
		self.add_routes(handler.routes())


def upenwrt_serve(host, port, app: UpenwrtApp):
	aiohttp.web.run_app(
		app=app,
		host=host,
		port=port,
	)
