TOP = $(abspath ../..)
include $(TOP)/defs.mak

APPBUILDER=$(TOP)/scripts/appbuilder

all: appdir rootfs

appdir:
	$(APPBUILDER) Dockerfile

rootfs: appdir
	$(MYST) mkext2 appdir ext2rootfs

run:
	$(MYST_EXEC) ext2rootfs /usr/local/bin/python3 --app-config-path config.json

clean:
	rm -rf ext2rootfs appdir