#!/usr/bin/env python3

import sys
import os
import os.path as p
import argparse
import http.server
import urllib
import requests
import time
import calendar
import tempfile
import subprocess
import shutil
import re
import logging
import traceback
import attr

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


class OpenwrtArtifact:
	def openwrt_base_url(self):
		return f'https://downloads.openwrt.org/{self.release_path}/targets/{self.target_name}'

	def openwrt_imagebuilder_name(self):
		return f'openwrt-imagebuilder-{self.target_name.replace("/", "-")}.Linux-x86_64.tar.xz'

	def __init__(self, *, context, target_name, version_id):
		self.context = context
		self.target_name = target_name

		if '/' in version_id:
			raise ValueError(f'OpenwrtArtifact: bad version id: {version_id}')
		elif version_id == 'snapshot':
			self.release_path = 'snapshots'
		else:
			self.release_path = f'releases/{version_id}'

		self.base_url = self.openwrt_base_url()
		self.imagebuilder_file = None
		self.targetinfo = None

	def get_imagebuilder(self, target_dir):
		if not self.imagebuilder_file:
			imagebuilder_name = self.openwrt_imagebuilder_name()
			imagebuilder_url = f'{self.base_url}/{imagebuilder_name}'
			imagebuilder_file = p.join(self.context.cachedir, imagebuilder_name)
			get_file(imagebuilder_url, dest=imagebuilder_file)

			self.imagebuilder_file = imagebuilder_file

		target_path = tempfile.mkdtemp(dir=target_dir, prefix='imagebuilder')
		untar_imagebuilder = run(
			[ 'tar' , '-xaf', self.imagebuilder_file ],
			cwd=target_path,
		)

		filelist = os.listdir(target_path)
		if len(filelist) != 1:
			raise RuntimeError(f'Got {len(filelist)} != 1 files after unpacking imagebuilder: {filelist}')

		return p.join(target_path, filelist[0])

	def get_targetinfo(self, imagebuilder_dir):
		if self.targetinfo is None:
			self.targetinfo = OpenwrtTargetinfo(p.join(imagebuilder_dir, '.targetinfo'))
		return self.targetinfo


class OpenwrtSource:
	REVISION = re.compile('r([0-9]+)-([0-9a-f]+)')

	@staticmethod
	def parse_ref(release, revision):
		if release == 'SNAPSHOT':
			m = OpenwrtSource.REVISION.fullmatch(revision)
			if m:
				return m[2]
		raise ValueError(f'OpenwrtSource: bad revision: release={release}, revision={revision}')

	def __init__(self, *, context, target_name, release, revision):
		self.context = context
		self.target_name = target_name
		self.ref = OpenwrtSource.parse_ref(release=release, revision=revision)
		self.targetinfo = None

	def get_checkout(self, target_dir):
		repo_path = p.join(self.context.repodir, 'openwrt.git')
		target_path = tempfile.mkdtemp(dir=target_dir, prefix='worktree')
		git_clone = run(
			[ 'git', 'clone', '--no-checkout', repo_path, target_path ],
			cwd=target_dir,
		)
		git_checkout = run(
			[ 'git', 'checkout', '--force', self.ref ],
			cwd=target_path,
		)
		# Apply specific patches to the buildsystem that help us to (ab)use it in the way we want
		patchdir = p.join(self.context.staticdir, 'patches')
		for f in sorted(os.listdir(patchdir)):
			git_am = run(
				[ 'git', 'am', '-3', p.join(patchdir, f) ],
				cwd=target_path,
			)
		return target_path

	def _make_targetinfo(self, source_dir):
		if self.target_name.count('/') != 1:
			raise ValueError(f'OpenwrtSource: bad board name: {self.target_name} (expected exactly 1 slash)')
		board_arch, board_soc = p.split(self.target_name)
		targetinfo_path = p.join(source_dir, 'tmp', 'info', f'.targetinfo-{board_arch}')
		if not p.exists(targetinfo_path):
			make_tmpinfo = run(
				[ 'make', 'prepare-tmpinfo' ],
				cwd=source_dir,
			)
		return targetinfo_path

	def get_targetinfo(self, source_dir):
		if self.targetinfo is None:
			self.targetinfo = OpenwrtTargetinfo(self._make_targetinfo(source_dir))
		return self.targetinfo


@attr.s(kw_only=True)
class OpenwrtProfile:
	name = attr.ib(type=str)
	target = attr.ib(type=str)
	packages = attr.ib(type=list)
	devices = attr.ib(type=list)


@attr.s(kw_only=True)
class OpenwrtTarget:
	name = attr.ib(type=str)
	packages = attr.ib(type=str)


class OpenwrtTargetinfo:
	TARGETINFO_TARGET = re.compile('Target: (.*)')
	TARGETINFO_TARGET_PACKAGES = re.compile('Default-Packages: (.*)')

	TARGETINFO_PROFILE = re.compile('Target-Profile: DEVICE_(.*)')
	TARGETINFO_PROFILE_DEVICES = re.compile('Target-Profile-SupportedDevices: (.*)')
	TARGETINFO_PROFILE_PACKAGES = re.compile('Target-Profile-Packages: (.*)')

	def __init__(self, targetinfo):
		self.profiles = dict()
		self.targets = dict()

		with open(targetinfo, 'r') as f:
			print(f'parsing targetinfo at {targetinfo}')
			self._parse_targetinfo(f)

	def _parse_targetinfo(self, f):
		targets = dict()
		profiles = dict()
		section = dict()
		section_raw = []
		last_target = None

		for line in f:
			line = line.rstrip('\n')
			section_raw.append(line)

			# parse target fields
			m = self.TARGETINFO_TARGET.fullmatch(line)
			if m:
				section['target'] = m[1]
				continue
			m = self.TARGETINFO_TARGET_PACKAGES.fullmatch(line)
			if m:
				section['target_packages'] = m[1].split()
				continue

			# parse profile fields
			m = self.TARGETINFO_PROFILE.fullmatch(line)
			if m:
				section['profile'] = m[1]
				continue
			m = self.TARGETINFO_PROFILE_DEVICES.fullmatch(line)
			if m:
				section['profile_devices'] = m[1].split()
				continue
			m = self.TARGETINFO_PROFILE_PACKAGES.fullmatch(line)
			if m:
				section['profile_packages'] = m[1].split()
				continue

			# parse separator
			if line == '@@':
				if {'profile'} <= section.keys():
					profile = OpenwrtProfile(
						name=section['profile'],
						target=last_target, # NOTE: stateful format!
						devices=section.get('profile_devices', []),
						packages=section.get('profile_packages', []),
					)
					print(f'parse_targetinfo(f={f.name}): {profile}')
					for d in profile.devices:
						profiles[d] = profile
					profiles[profile.name] = profile
				elif {'target'} <= section.keys():
					target = OpenwrtTarget(
						name=section['target'],
						packages=section.get('target_packages', []),
					)
					print(f'parse_targetinfo(f={f.name}): {target}')
					targets[target.name] = target
					last_target = target
				else:
					section_raw_string = '\n'.join(section_raw)
					print(f'parse_targetinfo(f={f.name}: strange section:\n{section_raw_string}')

				section = dict()
				section_raw = []

		self.profiles = profiles
		self.targets = targets


class OpenwrtOperation:
	def __init__(self, *, context, source, artifact, target_name, board_name, pkgs):
		self.context = context
		self.source = source
		self.artifact = artifact
		self.target_name = target_name
		self.board_name = board_name
		self.packages = set(pkgs)
		self.workdir = None

	def __enter__(self):
		if not self.workdir:
			self.workdir = tempfile.mkdtemp(dir=self.context.workdir)

	def __exit__(self, *args, **kwargs):
		if self.workdir:
			shutil.rmtree(self.workdir)

	def build(self):
		assert(self.workdir)
		print(f'workdir: {self.workdir}')
		print(f'target: {self.target_name}')
		print(f'board: {self.board_name}')
		
		builddir = self.artifact.get_imagebuilder(self.workdir)
		print(f'builddir: {builddir}')

		bld_targetinfo = self.artifact.get_targetinfo(builddir)
		bld_profile = bld_targetinfo.profiles[self.board_name]
		print(f'build profile: {bld_profile}')

		if self.source:
			sourcedir = self.source.get_checkout(self.workdir)
			print(f'sourcedir: {sourcedir}')

			src_targetinfo = self.source.get_targetinfo(sourcedir)
			src_target = src_targetinfo.targets[self.target_name]
			print(f'src target: {src_target}')
			src_profile = src_targetinfo.profiles[self.board_name]
			print(f'src profile: {src_profile}')
			default_target_packages = set(src_target.packages)
			default_profile_packages = set(src_profile.packages)
		else:
			print('No source -- not subtracting default packages!')
			default_target_packages = set()
			default_profile_packages = set()

		print(f'default packages in target: {default_target_packages}')
		print(f'default packages in profile: {default_profile_packages}')

		default_target_only_packages = default_target_packages - default_profile_packages
		default_profile_only_packages = default_profile_packages - default_target_packages
		print(f'default packages in target only: {default_target_only_packages}')
		print(f'default packages in profile only: {default_profile_only_packages}')

		default_packages = set(default_target_packages) | set(default_profile_packages)
		print(f'default packages: {default_packages}')
		packages = set(self.packages)
		print(f'passed packages: {packages}')

		default_only_packages = default_packages - packages
		user_only_packages = packages - default_packages
		print(f'packages in default only (user removed!): {default_only_packages}')
		print(f'packages in user only (user installed!): {user_only_packages}')

		make_image = run(
			[ 'make', 'image', f'PROFILE={bld_profile.name}', f'PACKAGES={" ".join(user_only_packages)}' ],
			cwd=builddir,
		)

		outdir = p.join(builddir, 'bin', 'targets', self.artifact.target_name)
		print(f'outdir: {outdir}')
		filelist = os.listdir(outdir)
		print(f'outdir files: {filelist}')

		outputs = [ x for x in filelist if 'sysupgrade' in x ]
		if len(outputs) != 1:
			raise RuntimeError(f'Got {len(outputs)} !+ 1 sysupgrade outputs after building: {outputs}')

		return p.join(outdir, outputs[0])


class UpenwrtContext:
	def __init__(self, *, basedir):
		self.basedir = basedir
		self.staticdir = p.join(self.basedir, 'static')
		self.cachedir = p.join(self.basedir, 'cache')
		self.workdir = p.join(self.basedir, 'work')
		self.repodir = p.join(self.basedir, 'repo')


class UpenwrtHTTPServer(http.server.HTTPServer):
	def __init__(self, *args, context, **kwargs):
		http.server.HTTPServer.__init__(self, *args, **kwargs)
		self.context = context


class UpenwrtHTTPRequestHandlerFiles(http.server.SimpleHTTPRequestHandler):
	def __init__(self, *args, **kwargs):
		http.server.SimpleHTTPRequestHandler.__init__(self, *args, **kwargs, directory=self.context.staticdir)


class UpenwrtHTTPRequestHandler(UpenwrtHTTPRequestHandlerFiles):
	def __init__(self, request, client_address, server, *args, **kwargs):
		self.context = server.context
		self.error_message_format = '''%(explain)s'''
		self.error_content_type = 'text/plain;charset=utf-8'
		UpenwrtHTTPRequestHandlerFiles.__init__(self, request, client_address, server, *args, **kwargs)

	def send_error_exc(self, code, message=None, explain=None):
		e = sys.exc_info()
		traceback.print_exception(*e)
		return self.send_error(code=code, message=message, explain=f'{explain}:\n{"".join(traceback.format_exception(*e))}')

	def do_HEAD(self):
		if self.path == '/get':
			self.path = '/get.sh'
			return UpenwrtHTTPRequestHandlerFiles.do_HEAD(self)
		else:
			return self.send_error(405)

	def do_GET(self):
		url = urllib.parse.urlsplit(self.path)
		assert(not url.scheme)
		assert(not url.netloc)

		if url.path == '/get':
			self.path = '/get.sh'
			return UpenwrtHTTPRequestHandlerFiles.do_GET(self)
		elif url.path == '/api/get':
			try:
				args = urllib.parse.parse_qs(url.query)
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
				with op:
					output = op.build()
					f = open(output, 'rb')

			except Exception:
				return self.send_error_exc(500, explain=f'Internal error building firmware')

			try:
				with f:
					st = os.stat(f.fileno())

					self.send_response(200)
					self.send_header('Last-Modified', get_last_modified(st))
					self.send_header('Content-Type', 'application/octet-stream')
					self.send_header('Content-Length', st.st_size)
					self.end_headers()

					shutil.copyfileobj(f, self.wfile)

			except Exception:
				return self.send_error_exc(500, explain=f'Internal error sending firmware')

		else:
			return self.send_error(404)


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument('-l', '--listen', default='')
	parser.add_argument('-p', '--port', type=int, default=8000)
	parser.add_argument('-d', '--basedir', default='')
	args = parser.parse_args()

	httpd_address = (args.listen, args.port)
	httpd_context = UpenwrtContext(
		basedir=p.join(os.getcwd(), args.basedir),
	)

	httpd = UpenwrtHTTPServer(httpd_address, UpenwrtHTTPRequestHandler, context=httpd_context)
	httpd.serve_forever()
