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
		self.packages = pkgs
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

		bld_packageinfo = await self.artifact.get_packageinfo(builddir)
		bld_targetinfo = await self.artifact.get_targetinfo(builddir)
		try:
			bld_target = bld_targetinfo.targets[self.target_name]
			logging.debug(f'OpenwrtOperation: prepare(): builder target: {bld_target}')
			bld_profile = bld_targetinfo.profiles[self.board_name]
			logging.debug(f'OpenwrtOperation: prepare(): builder profile: {bld_profile}')
		except KeyError:
			targetinfo_dump = bld_targetinfo.dump()
			raise UpenwrtUserError(f"""
Invalid board or device name '{self.board_name}' for target '{self.target_name}'.
Available targets, boards and devices for this imagebuilder:
{targetinfo_dump}
""".strip())

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

		logging.info(f'OpenwrtOperation: prepare(): client packages (raw): {self.packages}')

		# 0. Load input packages, parse aliases
		def load_packages(packages):
			for p in packages:
				aliases = p.split(',')
				yield aliases[0], set(aliases[1:])
		aliases = dict(load_packages(self.packages))
		packages = set(aliases.keys())
		logging.info(f'OpenwrtOperation: prepare(): client packages: {packages}')

		# 1. correlate default and installed packages using Provides:
		def correlate_defaults(packages, aliases, src_defaults):
			for p in packages:
				# shortcut
				if p in src_defaults:
					yield p
					continue

				correlated = set()
				for a in aliases[p]:
					# try to correlate with default packages in source
					if a in src_defaults:
						correlated.add(a)

				if len(correlated) > 1:
					raise RuntimeError(f'OpenwrtOperation: prepare(): package {p} is referenced by more than one alias in defaults: {correlated}')
				elif correlated:
					yield correlated.pop()
				else:
					yield p
		packages = set(correlate_defaults(packages, aliases, default_packages))
		logging.info(f'OpenwrtOperation: prepare(): client packages (correlated 1): {packages}')

		default_only_packages = default_packages - packages
		user_only_packages = packages - default_packages
		logging.info(f'OpenwrtOperation: prepare(): client REMOVED: {default_only_packages}')
		logging.info(f'OpenwrtOperation: prepare(): client INSTALLED: {user_only_packages}')

		# 2. attempt Provides: substitution for client packages that do not exist in target
		def correlate_target(packages, aliases, target_packageinfo):
			for p in packages:
				# shortcut
				if p in target_packageinfo.aliases:
					yield p
					continue

				correlated = set()
				# FIXME: after first round of correlation, aliases might become mismatched with packages
				for a in aliases.get(p, ()):
					# try to correlate with packages that exist in target
					if a in target_packageinfo.aliases:
						# there may be multiple aliases pointing to the same package, both in source information and in target information
						# e. g. in source, libwolfssl<unique> provides libwolfssl, libcyassl
						#       in target, libwolfssl<unique2> provides libwolfssl, libcyassl
						# naïvely, this is a failure condition because libwolfssl<unique> is referenced by two aliases both of which exist in target
						# but in fact, the situation is still unambiguous
						#for p2 in target_packageinfo.aliases[a]:
						#	correlated.add(p2.name)
						correlated.add(a)

				if len(correlated) > 1:
					# HACK: if we managed to get into this situation, try to select a single preferred alias that is a substring of package name
					preferred = { c for c in correlated if c in p }
					if len(preferred) == 1:
						yield preferred.pop()
						continue

					raise RuntimeError(f'OpenwrtOperation: prepare(): package {p} has more than one alias in target: {correlated}')
				elif correlated:
					yield correlated.pop()
				else:
					yield p
		packages = set(correlate_target(packages, aliases, bld_packageinfo))
		logging.info(f'OpenwrtOperation: prepare(): client INSTALLED (correlated 2): {packages}')


		# noinspection PyArgumentList
		return OpenwrtOperationDetails(
			builddir=builddir,
			profile=bld_profile,
			packages=packages,
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
