#CC     := gcc
#PKGS   := glib-2.0 gstreamer-1.0 gstreamer-sdp-1.0 gstreamer-webrtc-1.0 \
          gstreamer-rtp-1.0 json-glib-1.0 libsoup-2.4

#LIBS   := $(shell pkg-config --libs $(PKGS))
#CFLAGS := -O0 -ggdb -Wall -fno-omit-frame-pointer \
          $(shell pkg-config --cflags $(PKGS))

#webrtc-sendrecv: webrtc-sendrecv.c
#		$(CC) $(CFLAGS) $^ $(LIBS) -o $@

CC := gcc

# Base compiler flags
CFLAGS := -O0 -ggdb -Wall -fno-omit-frame-pointer

# GLib/GObject flags
CFLAGS += -I/usr/include/glib-2.0 -I/usr/lib/aarch64-linux-gnu/glib-2.0/include

# GStreamer flags
CFLAGS += -I/usr/include/gstreamer-1.0
CFLAGS += -I/usr/include/gstreamer-1.0/gst/webrtc
CFLAGS += -I/usr/include/gstreamer-1.0/gst/rtp
CFLAGS += -I/usr/include/gstreamer-1.0/gst/sdp

# JSON-GLib flags
CFLAGS += -I/usr/include/json-glib-1.0

# libsoup flags
CFLAGS += -I/usr/include/libsoup-2.4

# Linker flags
LIBS := -lgstreamer-1.0 -lgstwebrtc-1.0 -lgstrtp-1.0 -lgstsdp-1.0
LIBS += -lglib-2.0 -lgobject-2.0
LIBS += -ljson-glib-1.0
LIBS += -lsoup-2.4

webrtc-sendrecv: webrtc-sendrecv.c
	$(CC) $(CFLAGS) $^ $(LIBS) -o $@

.PHONY: clean
clean:
	rm -f webrtc-sendrecv
