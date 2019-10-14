#!/hint/python3

import os
import os.path as p
import asyncio
import aiofiles
import aiofiles.os
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
		async with aiofiles.open(p.join(self.context.staticdir, file), 'r') as f:
			st = await aiofiles.os.stat(f.fileno())
			data = await f.read()

		for k, v in replacements.items():
			data = data.replace(f'@{k}@', v)

		response = aiohttp.web.Response(text=data)
		response.last_modified = st.st_mtime
		return response


	async def response_stream_file(self, request: aiohttp.web.Request, fobj):
		st = await aiofiles.os.stat(fobj.fileno())

		resp = aiohttp.web.StreamResponse()
		resp.content_type = 'application/octet-stream'
		resp.content_length = st.st_size
		resp.last_modified = st.st_mtime
		await resp.prepare(request)

		sz = 256 * 1024
		while True:
			chunk = await fobj.read(sz)
			if not chunk:
				break
			await resp.write(chunk)

		return resp


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
			async with op:
				output = await op.build()

				async with aiofiles.open(output, 'rb') as f:
					# we have already opened the output, release resources
					# (i. e. remove the working directory)
					await op.__aexit__()
					return await self.response_stream_file(request=request, fobj=f)

		elif mode == 'list':
			async with op:
				output = await op.list_packages()

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
