#!/bin/bash
# Daily backup of xurshid.org: blog code/content, secrets, and the system config
# that is NOT in git (nginx site, systemd units, sshd config, certbot, LE certs).
#
# Naming matters: files are blog-auto-<date>.tar.gz so the prune glob below can
# never match blog-pre-tech-pivot-2026-07-25.tar.gz, the hand-made pivot backup.
set -euo pipefail

DEST=/root/backups
KEEP=14
OUT="$DEST/blog-auto-$(date +%F).tar.gz"

mkdir -p "$DEST"

tar czf "$OUT.part" \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  -C / \
  root/blog \
  root/.git-credentials \
  root/.ssh/authorized_keys \
  etc/systemd/system/blog.service \
  etc/systemd/system/blog-bot.service \
  etc/nginx/sites-available/blog \
  etc/nginx/sites-enabled/blog \
  etc/ssh/sshd_config \
  etc/ssh/sshd_config.d \
  etc/cron.d/certbot \
  etc/letsencrypt

mv "$OUT.part" "$OUT"
chmod 600 "$OUT"

# Keep the newest $KEEP automatic backups; leave everything else alone.
ls -1t "$DEST"/blog-auto-*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f

echo "$(date -Is) wrote $OUT ($(du -h "$OUT" | cut -f1))"
