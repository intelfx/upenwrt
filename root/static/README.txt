upenwrt(1)                          UPENWRT                           upenwrt(1)

NAME

    upenwrt - generate an OpenWRT sysupgrade image with all your packages

SYNOPSIS

    curl @BASE_URL@/get | sh [-s -- OPTIONS...] >/tmp/sysupgrade.img
    sysupgrade /tmp/sysupgrade.img

OPTIONS

    RELEASE
        OpenWRT release (e. g. "18.06.4") or the string "snapshot".

FILES

    /etc/openwrt_release
        Used to determine OpenWRT target name and current (installed) OpenWRT
        release and revision.

    /tmp/sysinfo/board_name
        Used to determine OpenWRT device name.

    /usr/lib/opkg/status
        Used to determine the list of packages to integrate into the image.

OPTIONS

    --debug
        Enables (slightly more) verbose logging.

    --dry-run
        Skips the actual call; only generates a curl(1) command line.

    --hw-target TARGET-NAME
        OpenWRT target name (e. g. "ramips/mt7621").
        Overrides $TARGET_NAME and DISTRIB_TARGET= of /etc/openwrt_release.

    --hw-board BOARD-NAME
        OpenWRT board or profile name (e. g. "xiaomi,mir3g" or "mir3g").
        Overrides $BOARD_NAME and contents of /tmp/sysinfo/board_name.

    --current-release RELEASE
        Current (installed) OpenWRT release, e. g. "SNAPSHOT".
        Overrides $RELEASE and DISTRIB_RELEASE= of /etc/openwrt_release.

    --current-revision REVISION
        Current (installed) OpenWRT revision, e. g. "r10574-273b803623".
        Overrides $REVISION and DISTRIB_REVISION= of /etc/openwrt_release.

    -P, --packages "PKG1 [PKG2...]"
        List of packages to integrate into the image (space-separated).
        Overrides $PACKAGES and contents of /usr/lib/opkg/status.

    -A, --packages-add "PKG1 [PKG2...]"
        List of packages to add to the image (space-separated).
        Overrides $PKGS_ADD and supplements contents of /usr/lib/opkg/status.

    -S, --packages-remove "PKG1 [PKG2...]"
        List of packages to skip adding to the image (space-separated).
        Overrides $PKGS_REMOVE and supplements contents of /usr/lib/opkg/status.

        Note: package dependencies take precedence over this option.

    -T, --target TARGET-RELEASE
        Desired (to be built) OpenWRT release, e. g. "snapshot" or "v18.06".
        Overrides $TARGET and defaults to "snapshot", which stands for the latest published nightly.

ENVIRONMENT

    DEBUG
        Enables (slightly more) verbose logging.

    DRY_RUN
        Skips the actual call; only generates a curl(1) command line.

    TARGET_NAME
        OpenWRT target name (e. g. "ramips/mt7621").
        Overrides DISTRIB_TARGET= of /etc/openwrt_release.

    BOARD_NAME
        OpenWRT board or profile name (e. g. "xiaomi,mir3g" or "mir3g").
        Overrides contents of /tmp/sysinfo/board_name.

    RELEASE
        Current (installed) OpenWRT release, e. g. "snapshot".
        Overrides DISTRIB_RELEASE= of /etc/openwrt_release.

    REVISION
        Current (installed) OpenWRT revision, e. g. "r10574-273b803623".
        Overrides DISTRIB_REVISION= of /etc/openwrt_release.

    PACKAGES
        List of packages to integrate into the image (space-separated).
        Overrides contents of /usr/lib/opkg/status.

WWW

    https://github.com/intelfx/upenwrt

upenwrt 0.1.0                                                         upenwrt(1)
