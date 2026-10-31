#!/bin/sh
m=$(sed -n 's/.*matryoshka.autotest=\([a-z]*\).*/\1/p' /proc/cmdline)
if [ "$m" = run ]; then
  mkdir -p /run/mtest; for i in $(seq 1 30); do [ -e /dev/disk/by-label/MTEST ] && break; sleep 1; done
  mount /dev/disk/by-label/MTEST /run/mtest && sh /run/mtest/run.sh > /run/mtest/out.log 2>&1; echo "AUTOTEST_RC=$?" >> /run/mtest/out.log; cat /run/mtest/out.log > /dev/console; umount /run/mtest; sync; systemctl poweroff; exit 0
fi
d=$(ls /dev/nvme0n1 /dev/vda /dev/sda 2>/dev/null | head -n1)
/usr/lib/matryoshka/install-core.sh --mode $m --disk $d --user tester --fullname Tester --password-hash "$(printf test123 | openssl passwd -6 -stdin)" --yes > /run/autotest.log 2>&1; echo AUTOTEST_RC=$? >> /run/autotest.log; cat /run/autotest.log > /dev/console; sync; systemctl poweroff
