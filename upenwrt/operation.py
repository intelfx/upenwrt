#!/hint/python3

import os
import os.path as p
import tempfile
import shutil
import attr

from . import util
from .targetinfo import OpenwrtProfile


@attr.s(kw_only=True)
class OpenwrtOperationDetails:
	builddir = attr.ib(type=str)
	profile = attr.ib(type=OpenwrtProfile)
	packages = attr.ib(type=set)


class OpenwrtOperation:
	def __init__(self, *, context, source, artifact, target_name, board_name, pkgs):
		self.context = context
		self.source = source
		self.artifact = artifact
		self.target_name = target_name
		self.board_name = board_name
		self.packages = set(pkgs)
		self.workdir = None

	async def __aenter__(self):
		if not self.workdir:
			self.workdir = tempfile.mkdtemp(dir=self.context.workdir)

	async def __aexit__(self, *args, **kwargs):
		if self.workdir:
			shutil.rmtree(self.workdir)
			self.workdir = None

	async def prepare(self):
		assert(self.workdir)
		print(f'workdir: {self.workdir}')
		print(f'target: {self.target_name}')
		print(f'board: {self.board_name}')

		builddir = await self.artifact.get_imagebuilder(self.workdir)
		print(f'builddir: {builddir}')

		bld_targetinfo = await self.artifact.get_targetinfo(builddir)
		bld_profile = bld_targetinfo.profiles[self.board_name]
		print(f'desired profile: {bld_profile}')

		if self.source:
			sourcedir = await self.source.get_checkout(self.workdir)
			print(f'sourcedir: {sourcedir}')

			src_targetinfo = await self.source.get_targetinfo(sourcedir)
			src_target = src_targetinfo.targets[self.target_name]
			print(f'existing target: {src_target}')
			src_profile = src_targetinfo.profiles[self.board_name]
			print(f'existing profile: {src_profile}')
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

		default_packages = default_target_packages | default_profile_packages
		print(f'default packages: {default_packages}')
		packages = self.packages
		print(f'passed packages: {packages}')

		default_only_packages = default_packages - packages
		user_only_packages = packages - default_packages
		print(f'packages in default only (user removed!): {default_only_packages}')
		print(f'packages in user only (user installed!): {user_only_packages}')

		# noinspection PyArgumentList
		return OpenwrtOperationDetails(
			builddir=builddir,
			profile=bld_profile,
			packages=user_only_packages,
		)

	async def list_packages(self):
		prep = await self.prepare()

		return ' '.join(prep.packages)

	async def build(self):
		prep = await self.prepare()

		make_image = await util.run(
			[ 'make', 'image', f'PROFILE={prep.profile.name}', f'PACKAGES={" ".join(prep.packages)}' ],
			cwd=prep.builddir,
		)

		outdir = p.join(prep.builddir, 'bin', 'targets', self.artifact.target_name)
		print(f'outdir: {outdir}')
		filelist = os.listdir(outdir)
		print(f'outdir files: {filelist}')

		outputs = [ x for x in filelist if 'sysupgrade' in x ]
		if len(outputs) != 1:
			raise RuntimeError(f'Got {len(outputs)} !+ 1 sysupgrade outputs after building: {outputs}')

		return p.join(outdir, outputs[0])
