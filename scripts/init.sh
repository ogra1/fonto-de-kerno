#! /bin/sh

if [ ! -e $SNAP_DATA/.initalized ]; then
  $SNAP/usr/bin/updater && \
	  cp $SNAP/templates/index.html $SNAP_COMMON/out/index.html && \
	  touch $SNAP_DATA/.initalized
  snapctl start --enable $SNAP_NAME.updater 2>&1 || true
fi
