#!/bin/sh

set -e


#
# functions
#

log() {
	echo ":: $*" >&2
}

warn() {
	echo "W: $*" >&2
}

err() {
	echo "E: $*" >&2
}

die() {
	err "$@"
	exit 1
}

dbg() {
	if test -n "$DEBUG"; then "$@"; fi
}

function log_choice() {
	local name="$1"
	local value="$(eval "echo \"\${${name}}\"")"
	local reason="$(eval "echo \"\${${name}_reason}\"")"
	if test -z "$reason"; then reason="override"; fi
	log "\$$name='$value' ($reason)"
}

# Oh blackest aeon -- evaluated force
# Holy mother, dreadful creature, be the reason for all cause
AWK_FILTER_PACKAGES='
function parse_vars()
{
	if (package_add != "") {
		split(package_add, tmp, ",")
		for (i in tmp) {
			package_add[tmp[i]]=1
		}
	}

	if (package_remove != "") {
		split(package_remove, tmp, ",")
		for (i in tmp) {
			package_remove[tmp[i]]=1
		}
	}
	delete tmp
}

function pkg_new(pkg)
{
	package = pkg
	p_user = 0
	p_provides = ""
}

function pkg_check()
{
	if (package != "" && !(package in package_remove) && p_user) {
		delete package_add[package]
		if (p_provides != "") {
			print package "," p_provides
		} else {
			print package
		}
	}
}

function pkg_add() {
	for (i in package_add) {
		print i
	}
}

BEGIN { FS = ": "; parse_vars() }
/^Package: / { pkg_new($2) }
/^Provides: / { p_provides = gensub(/, /, ",", "g", $2) }
/^Status: .*\<user\>.*/ { p_user = 1 }
/^$/ { pkg_check() }
END { pkg_check(); pkg_add() }
'

opkg_get_user_all() {
	awk "$@" "$AWK_FILTER_PACKAGES" "$OPKG_STATUS" | sort
}

opkg_get_user() {
	pkgs_2="$(mktemp)"

	opkg_get_user_all -v package_add="$PKGS_ADD" -v package_remove="$PKGS_REMOVE" > "$pkgs_2"
	# write result
	cat "$pkgs_2" | tr -s ' \n' ' '

	# remove temp files
	rm -f "$pkgs_2"
}


#
# main
#

# parse arguments
# openwrt does not have getopt(1) -- sunrise by hand
while test "$#" -ne 0; do
	# fetch arg
	arg="$1"

	# try to split arg by =
	name="${arg%%=*}"
	value="${arg#*=}"
	hasvalue=1
	if test "$arg" == "$name"; then value=""; hasvalue=0; fi

	case "$name" in
	--debug)
		var=DEBUG
		needvalue=0
		;;
	--dry-run)
		var=DRY_RUN
		needvalue=0
		;;
	--hw-target)
		var=TARGET_NAME
		needvalue=1
		;;
	--hw-board)
		var=BOARD_NAME
		needvalue=1
		;;
	--current-release)
		var=RELEASE
		needvalue=1
		;;
	--current-revision)
		var=REVISION
		needvalue=1
		;;
	-P|--packages)
		var=PACKAGES
		needvalue=1
		;;
	-A|--packages-add|--pkg-add|--pkgs-add)
		var=PKGS_ADD
		needvalue=1
		;;
	-S|--packages-remove|--pkg-remove|--pkgs-remove)
		var=PKGS_REMOVE
		needvalue=1
		;;
	-T|--target)
		var=TARGET
		needvalue=1
		;;
	--)
		# exit with consuming
		shift
		break
		;;
	-*)
		die "bad argument: '$arg' is not a valid argument"
		;;
	*)
		# exit without consuming
		break
		;;
	esac
	shift

	if test "$needvalue" -eq 0; then
		# if we don't expect a value and one has been provided via =, it's an error
		if test "$hasvalue" -ne 0; then die "bad argument: '$arg' does not expect a value"; fi
		value=1
	elif test "$hasvalue" -eq 0; then
		# if we expect a value and one hasn't been provided via =, consume next argument
		if test "$#" -eq 0; then die "bad argument: '$arg' expects a value, but there is none"; fi
		value="$1"
		shift
	fi
	eval "${var}='${value}'"
	eval "${var}_reason='command line'"
done

if test "$#" -ne 0; then
	die "bad argument: excess arguments: $*"
fi

# determine board path
if test -n "$TARGET_NAME"; then
	:
elif test -f /etc/openwrt_release; then
	. /etc/openwrt_release
	test -n "$DISTRIB_TARGET" || die "\$DISTRIB_TARGET not present in /etc/openwrt_release, exiting"
	TARGET_NAME="$DISTRIB_TARGET"
	TARGET_NAME_reason="/etc/openwrt_release \$DISTRIB_TARGET"
else
	die "/etc/openwrt_release does not exist or is not a regular file, exiting"
fi
log_choice TARGET_NAME

# determine board name
if test -n "$BOARD_NAME"; then
	:
elif test -f /tmp/sysinfo/board_name; then
	BOARD_NAME="$(cat /tmp/sysinfo/board_name)"
	BOARD_NAME_reason="/tmp/sysinfo/board_name"
else
	die "/tmp/sysinfo/board_name does not exist or is not a regular file, exiting"
fi
log_choice BOARD_NAME

# determine current release & revision
if test -n "$RELEASE"; then
	:
elif test -n /etc/openwrt_release; then
	. /etc/openwrt_release
	test -n "$DISTRIB_RELEASE" || die "\$DISTRIB_RELEASE not present in /etc/openwrt_release, exiting"
	RELEASE="$DISTRIB_RELEASE"
	RELEASE_reason="/etc/openwrt_release \$DISTRIB_RELEASE"
else
	die "/etc/openwrt_release does not exist or is not a regular file, exiting"
fi
log_choice RELEASE

if test -n "$REVISION"; then
	:
elif test -n /etc/openwrt_release; then
	. /etc/openwrt_release
	test -n "$DISTRIB_REVISION" || die "\$DISTRIB_REVISION not present in /etc/openwrt_release, exiting"
	REVISION="$DISTRIB_REVISION"
	REVISION_reason="/etc/openwrt_release \$DISTRIB_REVISION"
else
	die "/etc/openwrt_release does not exist or is not a regular file, exiting"
fi
log_choice REVISION


# determine packages partial overrides
if test -n "$PKGS_ADD"; then
	dbg log_choice PKGS_ADD
fi

if test -n "$PKGS_REMOVE"; then
	dbg log_choice PKGS_REMOVE
fi

# determine user-installed packages
if test -n "$PACKAGES"; then
	:
else
	if test -n "$OPKG_STATUS"; then
		OPKG_STATUS_reason="override"
	else
		OPKG_STATUS="/usr/lib/opkg/status"
		OPKG_STATUS_reason="default"
	fi
	log_choice OPKG_STATUS

	PACKAGES="$(opkg_get_user)"
	PACKAGES_reason="$OPKG_STATUS"
fi
log_choice PACKAGES

# determine base URL
BASE_URL="@BASE_URL@"
BASE_URL_reason='server-passed'
dbg log_choice BASE_URL

API_ENDPOINT="@API_ENDPOINT@"
API_ENDPOINT_reason='server-passed'
dbg log_choice API_ENDPOINT

# determine target release
if test -n "$TARGET"; then
	:
else
	TARGET="snapshot"
	TARGET_reason='default'
fi
log_choice TARGET

# generate CURL call
URL="$BASE_URL/api/$API_ENDPOINT"
CURL="curl '$URL'"
CURL="$CURL -G"
CURL="$CURL -d 'target_name=$TARGET_NAME'"
CURL="$CURL -d 'board_name=$BOARD_NAME'"
CURL="$CURL -d 'current_release=$RELEASE'"
CURL="$CURL -d 'current_revision=$REVISION'"
CURL="$CURL -d 'target_version=$TARGET'"
for p in $PACKAGES; do
	CURL="$CURL -d 'pkgs=$p'"
done
dbg log "\$CURL='$CURL'"

# exit at this point if we're asked not to do anything
if test -n "$DRY_RUN"; then
	exit 1
fi

# invoke curl protecting against server errors
TMP_BODY="$(mktemp)"
TMP_STATUS="$(mktemp)"
cleanup() { rm -f "$TMP_BODY" "$TMP_STATUS"; }
trap cleanup EXIT

eval "$CURL -sSL -w '%{http_code}' -o '$TMP_BODY' >'$TMP_STATUS'"
STATUS="$(cat "$TMP_STATUS")"
if [ -n "$STATUS" -a "$STATUS" -ge 200 -a "$STATUS" -lt 400 ]; then
	if [ -t 1 ]; then
		mv "$TMP_BODY" /tmp/sysupgrade-$TARGET.img
		echo /tmp/sysupgrade-$TARGET.img
	else
		cat "$TMP_BODY"
	fi
	rc=0
else
	cat "$TMP_BODY" >&2
	if [ -t 2 ]; then echo >&2; fi
	rc=1
fi

exit $rc
