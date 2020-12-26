#!/hint/python3

import os.path as p
import logging
import attr
import re

from . import util
from . import wrapio
from .targetinfo import OpenwrtProfile
from .util import UpenwrtError, UpenwrtUserError


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
			self.workdir = await wrapio.tempfile_mkdtemp(dir=self.context.workdir)


	async def __aexit__(self, *args, **kwargs):
		if self.workdir:
			await wrapio.shutil_rmtree(self.workdir)
			self.workdir = None


	async def prepare(self):
		assert(self.workdir)
		logging.info(f'OpenwrtOperation: prepare(): target name: {self.target_name}')
		logging.info(f'OpenwrtOperation: prepare(): board name: {self.board_name}')
		logging.debug(f'OpenwrtOperation: prepare(): workdir at: {self.workdir}')

		builddir = await self.artifact.get_imagebuilder(self.workdir)
		logging.debug(f'OpenwrtOperation: prepare(): builddir at: {builddir}')

		bld_targetinfo = await self.artifact.get_targetinfo(builddir)
		try:
			bld_profile = bld_targetinfo.profiles[self.board_name]
		except KeyError:
			targetinfo_dump = bld_targetinfo.dump()
			raise UpenwrtUserError(f"""
Invalid board or device name '{self.board_name}' for target '{self.target_name}'.
Available targets, boards and devices for this imagebuilder:
{targetinfo_dump}
""".strip())
		logging.debug(f'OpenwrtOperation: prepare(): builder profile: {bld_profile}')

		if self.source:
			sourcedir = await self.source.get_checkout(self.workdir)
			logging.debug(f'OpenwrtOperation: prepare(): sourcedir at: {sourcedir}')

			src_targetinfo = await self.source.get_targetinfo(sourcedir)
			src_target = src_targetinfo.targets[self.target_name]
			logging.debug(f'OpenwrtOperation: prepare(): source target: {src_target}')
			src_profile = src_targetinfo.profiles[self.board_name]
			logging.debug(f'OpenwrtOperation: prepare(): source profile: {src_profile}')
			default_target_packages = set(src_target.packages)
			default_profile_packages = set(src_profile.packages)
		else:
			logging.warning(f'OpenwrtOperation: prepare(): no source -- not subtracting default packages!')
			default_target_packages = set()
			default_profile_packages = set()

		logging.debug(f'OpenwrtOperation: prepare(): per-target defaults: {default_target_packages}')
		logging.debug(f'OpenwrtOperation: prepare(): per-profile defaults: {default_profile_packages}')

		default_target_only_packages = default_target_packages - default_profile_packages
		default_profile_only_packages = default_profile_packages - default_target_packages
		default_both_packages = default_target_packages & default_profile_packages
		logging.debug(f'OpenwrtOperation: prepare(): note: excl. per-target defaults: {default_target_only_packages}')
		logging.debug(f'OpenwrtOperation: prepare(): note: excl. per-profile defaults: {default_profile_only_packages}')
		logging.debug(f'OpenwrtOperation: prepare(): note: common defaults: {default_both_packages}')

		default_packages = default_target_packages | default_profile_packages
		logging.info(f'OpenwrtOperation: prepare(): client defaults: {default_packages}')
		packages = self.packages
		#logging.info(f'OpenwrtOperation: prepare(): client packages: {packages}')

		# FIXME: correlate default and installed packages using Provides:
		# HACK: replace known non-stable package names with their stable aliases
		def fixup_packages_early(packages):
			for p in packages:
				if p.startswith('libgcc'):
					yield 'libgcc'
				elif p.startswith('kernel'):
					pass
				else:
					yield p
		packages = set(fixup_packages_early(packages))
		logging.info(f'OpenwrtOperation: prepare(): client packages (fixed-up): {packages}')

		default_only_packages = default_packages - packages
		user_only_packages = packages - default_packages
		logging.info(f'OpenwrtOperation: prepare(): client REMOVED: {default_only_packages}')
		#logging.info(f'OpenwrtOperation: prepare(): client INSTALLED: {user_only_packages}')

		# FIXME: attempt Provides: substitution for client packages that do not exist in target
		# HACK: replace known non-stable package names with their stable aliases
		def fixup_packages(packages):
			for p in packages:
				if m := re.fullmatch("(libustream-[a-z]+)([0-9]+)", p):
					yield m.group(1)
				else:
					yield p
		user_only_packages = set(fixup_packages(user_only_packages))
		logging.info(f'OpenwrtOperation: prepare(): client INSTALLED (fixed-up): {user_only_packages}')

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
		logging.debug(f'OpenwrtOperation: build(): outdir at: {outdir}')
		filelist = await wrapio.os_listdir(outdir)
		logging.debug(f'OpenwrtOperation: build(): outputs: {filelist}')

		outputs = [ x for x in filelist if 'sysupgrade' in x ]
		if len(outputs) != 1:
			raise RuntimeError(f'OpenwrtOperation: got {len(outputs)} != 1 sysupgrade files after building: {outputs}')

		return p.join(outdir, outputs[0])
