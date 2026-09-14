#!/bin/sh
mkdir -p /mnt/us/koreader/settings /mnt/us/notes/solar
touch /mnt/us/koreader/settings/solar-dashboard-start
exec /mnt/us/koreader/koreader.sh --kual /mnt/us/notes/solar
