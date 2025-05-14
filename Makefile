CC     := gcc
PKGS   := glib-2.0 gstreamer-1.0 gstreamer-sdp-1.0 gstreamer-webrtc-1.0 \
          gstreamer-rtp-1.0 json-glib-1.0 libsoup-2.4

LIBS   := $(shell pkg-config --libs $(PKGS))
CFLAGS := -O0 -ggdb -Wall -fno-omit-frame-pointer \
          $(shell pkg-config --cflags $(PKGS))

webrtc-sendrecv: webrtc-sendrecv.c
		$(CC) $(CFLAGS) $^ $(LIBS) -o $@