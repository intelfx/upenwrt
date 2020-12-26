#!/hint/python3

import sys
import os.path as p
import logging
import aiofiles
import aiofiles.os
import aiohttp.web
import urllib.parse
import attr
import subprocess
import traceback
from typing import *

from . import util
from .artifact import OpenwrtArtifact
from .source import OpenwrtSource
from .operation import OpenwrtOperation
from .util import UpenwrtError, UpenwrtUserError


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

		await util.copy_stream(src=fobj, dst=resp)

		return resp


	async def handle_get_readme(self, request: aiohttp.web.Request):
		logging.info(f'GET {request.rel_url.path}')
		replacements = {
			'BASE_URL': self.context.baseurl
		}
		return await self.response_template_file(request=request, file='README.txt', replacements=replacements)


	async def handle_get_sh(self, request: aiohttp.web.Request, api: str):
		logging.info(f'GET {request.rel_url.path}')
		replacements = {
			'BASE_URL': self.context.baseurl,
			'API_ENDPOINT': api,
		}
		return await self.response_template_file(request=request, file='get.sh', replacements=replacements)


	async def api_prepare_operation(self, request: aiohttp.web.Request):
		logging.info(f'GET {request.rel_url.path}(args={request.query})')

		args = request.query

		# read arguments from URL query string
		target_name = args['target_name']
		board_name = args['board_name']
		current_release = args.get('current_release', None)
		current_revision = args.get('current_revision', None)
		target_version = args.get('target_version', 'snapshot')
		pkgs = args.getall('pkgs', [])

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

		return op


	async def handle_api_build(self, request: aiohttp.web.Request):
		op = await self.api_prepare_operation(request=request)
		async with op:
			output = await op.build()

			async with aiofiles.open(output, 'rb') as f:
				# we have already opened the output, release resources
				# (i. e. remove the working directory)
				await op.__aexit__()
				return await self.response_stream_file(request=request, fobj=f)


	async def handle_api_list(self, request: aiohttp.web.Request):
		op = await self.api_prepare_operation(request=request)
		async with op:
			output = await op.list_packages()

		return aiohttp.web.Response(text=output)


	@staticmethod
	def handle_error(factory, text=None, user_error=False):
		e = sys.exc_info()
		traceback.print_exception(*e)

		trace = "".join(traceback.format_exception(*e))
		if text is not None:
			if user_error:
				body = text
			else:
				body = f'{text.rstrip()}\n\n{trace}'
		else:
			body = trace

		raise factory(text=body)


	ResponseCoroutine = Coroutine[Any, Any, aiohttp.web.Response]


	@staticmethod
	def wrap(handler: Callable[..., ResponseCoroutine], *args, **kwargs) -> Callable[[aiohttp.web.Request], ResponseCoroutine]:
		async def wrapped(request: aiohttp.web.Request):
			try:
				return await handler(request, *args, **kwargs)
			except UpenwrtUserError as e:
				UpenwrtHandler.handle_error(
					factory=aiohttp.web.HTTPBadRequest,
					text=str(e),
					user_error=True,
				)
			except subprocess.CalledProcessError as e:
				UpenwrtHandler.handle_error(
					factory=aiohttp.web.HTTPInternalServerError,
					text=e.stdout,
				)
			except Exception as e:
				UpenwrtHandler.handle_error(
					factory=aiohttp.web.HTTPInternalServerError,
				)
		return wrapped


	def routes(self):
		H = UpenwrtHandler.wrap
		base = self.context.baseurlpath
		return [
			aiohttp.web.get(p.join(base, ''), H(self.handle_get_readme)),
			aiohttp.web.get(p.join(base, 'get'), H(self.handle_get_sh, api='build')),
			aiohttp.web.get(p.join(base, 'list'), H(self.handle_get_sh, api='list')),
			aiohttp.web.get(p.join(base, 'api/build'), H(self.handle_api_build), allow_head=False),
			aiohttp.web.get(p.join(base, 'api/list'), H(self.handle_api_list), allow_head=False),
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
