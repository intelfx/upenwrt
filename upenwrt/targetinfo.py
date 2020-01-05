#!/hint/python3

import logging
import re
import attr


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
	profiles = attr.ib(type=dict)


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
			logging.debug(f'OpenwrtTargetinfo(f={f.name}): parsing targetinfo')
			self._parse_targetinfo(f)

	def dump(self, target=None):
		dump = self._dump([target] if target is not None else self.targets.keys())
		return '\n'.join(dump)

	def _dump(self, targets):
		for t in sorted(targets):
			target = self.targets[t]
			yield f'- Target: {t}'
			for p in sorted(target.profiles.keys()):
				profile = target.profiles[p]
				yield f'\t- Profile: {p}'
				for d in sorted(profile.devices):
					yield f'\t\t- Device: {d}'



	def _parse_targetinfo(self, f):
		targets = dict()
		profiles = dict()
		section = dict()
		section_raw = []
		last_target = None
		profiles_by_target = dict()

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
					# noinspection PyArgumentList
					profile = OpenwrtProfile(
						name=section['profile'],
						target=last_target,  # NOTE: stateful format!
						devices=section.get('profile_devices', []),
						packages=section.get('profile_packages', []),
					)
					logging.debug(f'OpenwrtTargetinfo(f={f.name}): {profile}')
					# lookup dict
					for d in profile.devices:
						profiles[d] = profile
					profiles[profile.name] = profile
					# hierarchy dict
					last_target.profiles[profile.name] = profile
				elif {'target'} <= section.keys():
					# noinspection PyArgumentList
					target = OpenwrtTarget(
						name=section['target'],
						packages=section.get('target_packages', []),
						profiles=dict(),
					)
					logging.debug(f'OpenwrtTargetinfo(f={f.name}): {target}')
					targets[target.name] = target
					last_target = target
				else:
					section_raw_string = '\n'.join(section_raw)
					logging.debug(f'OpenwrtTargetinfo(f={f.name}: strange section:\n{section_raw_string}')

				section = dict()
				section_raw = []

		self.profiles = profiles
		self.targets = targets
