#!/hint/python3

import os
import os.path as p
import re
import tempfile

from . import util
from . import wrapio
from .targetinfo import OpenwrtTargetinfo


class OpenwrtSource:
	REVISION = re.compile('r([0-9]+)-([0-9a-f]+)')

	@staticmethod
	def parse_ref(release, revision):
		if release == 'SNAPSHOT':
			m = OpenwrtSource.REVISION.fullmatch(revision)
			if m:
				return m[2]
		else:
			return f'v{release}'
		raise ValueError(f'OpenwrtSource: bad revision: release={release}, revision={revision}')

	def __init__(self, *, context, target_name, release, revision):
		self.context = context
		self.target_name = target_name
		self.ref = OpenwrtSource.parse_ref(release=release, revision=revision)
		self.targetinfo = None

	async def get_checkout(self, target_dir):
		repo_path = p.join(self.context.repodir, 'openwrt.git')
		target_path = tempfile.mkdtemp(dir=target_dir, prefix='worktree')
		git_clone = await util.run(
			[ 'git', 'clone', '--no-checkout', repo_path, target_path ],
			cwd=target_dir,
		)
		git_checkout = await util.run(
			[ 'git', 'checkout', '--force', self.ref ],
			cwd=target_path,
		)
		# Apply specific patches to the buildsystem that help us to (ab)use it in the way we want
		patchdir = p.join(self.context.staticdir, 'patches')
		for f in sorted(await wrapio.os_listdir(patchdir)):
			git_am = await util.run(
				[ 'git', 'am', '-3', p.join(patchdir, f) ],
				cwd=target_path,
			)
		return target_path

	async def _make_targetinfo(self, source_dir):
		if self.target_name.count('/') != 1:
			raise ValueError(f'OpenwrtSource: bad board name: {self.target_name} (expected exactly 1 slash)')
		board_arch, board_soc = p.split(self.target_name)
		targetinfo_path = p.join(source_dir, 'tmp', 'info', f'.targetinfo-{board_arch}')
		if not p.exists(targetinfo_path):
			make_tmpinfo = await util.run(
				[ 'make', 'prepare-tmpinfo' ],
				cwd=source_dir,
			)
		return targetinfo_path

	async def get_targetinfo(self, source_dir):
		if self.targetinfo is None:
			self.targetinfo = OpenwrtTargetinfo(await self._make_targetinfo(source_dir))
		return self.targetinfo
