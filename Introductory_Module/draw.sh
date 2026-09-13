#!/bin/bash

if wget -q --timeout=120 "$DL_URL" -O /tmp/drawio.deb; then
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq /tmp/drawio.deb 2>/dev/null || \
            { apt-get install -f -y -qq; dpkg -i /tmp/drawio.deb; }
        rm -f /tmp/drawio.deb
        ok "draw.io ${LATEST} installed"
    else
        warn "draw.io download failed — install from: https://github.com/jgraph/drawio-desktop/releases"
    fi
