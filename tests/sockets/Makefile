TOP=$(abspath ../..)
include $(TOP)/defs.mak

APPDIR = appdir
CFLAGS = -fPIC
LDFLAGS = -Wl,-rpath=$(MUSL_LIB)

all:
	$(MAKE) myst
	$(MAKE) rootfs

rootfs: sockets.c
	mkdir -p $(APPDIR)/bin
	$(MUSL_GCC) $(CFLAGS) -o $(APPDIR)/bin/sockets sockets.c $(LDFLAGS)
	$(MYST) mkcpio $(APPDIR) rootfs

ifdef STRACE
OPTS = --strace
endif

ifdef ETRACE
OPTS = --etrace
endif

UDSPATH=$(OBJDIR)/uds1

tests: all
	rm -rf $(UDSPATH)
	$(RUNTEST) $(MYST_EXEC) $(OPTS) rootfs /bin/sockets $(UDSPATH)

myst:
	$(MAKE) -C $(TOP)/tools/myst

clean:
	rm -rf $(APPDIR) rootfs export ramfs

ls:
	ls $(UDSPATH)
