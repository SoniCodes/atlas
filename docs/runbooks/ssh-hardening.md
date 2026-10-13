# Runbook: SSH hardening

Turn off password logins so the only way in is with a key.

This is managed by Ansible now. The task "Harden ssh (key-only login)" in
`ansible/site.yml` copies `security/01-hardening.conf` onto every host, checks it
with `sshd -t` before putting it in place, and reloads sshd if it changed. To
change anything, edit the file in the repo and run the playbook. Don't edit it on
the servers by hand.

The manual steps below are still worth knowing. They're what the playbook does
for you, and they're how you'd fix a host Ansible can't reach.

## Gotcha: first match wins

`/etc/ssh/sshd_config` has `Include /etc/ssh/sshd_config.d/*.conf`, and sshd uses
the **first** value it finds for each setting. Files are read in name order, so
`50-cloud-init.conf` beats `99-anything.conf`.

That's why the file is `01-hardening.conf`. A low number gets read first.

Netplan works the other way, where higher numbers win. Easy to mix up.

## Manual procedure

Keep your current SSH session open the whole time. Don't close it until step 5
works.

1. Check what's actually in effect right now. `sshd -T` shows the final result
   after every include is read. That's what matters, not what any one file says.

       sudo sshd -T | grep -iE 'passwordauthentication|kbdinteractive|permitrootlogin'

2. Create the drop-in:

       sudo nano /etc/ssh/sshd_config.d/01-hardening.conf

       PasswordAuthentication no
       KbdInteractiveAuthentication no
       PermitRootLogin prohibit-password

3. Check the syntax before applying it. If this errors, fix it and stop there.

       sudo sshd -t && echo "SYNTAX OK"
       sudo sshd -T | grep -iE 'passwordauthentication|kbdinteractive|permitrootlogin'

   The second command tells you your file actually won the ordering.

4. Reload, don't restart. Reload keeps your current connection alive.

       sudo systemctl reload ssh      # Ubuntu
       sudo systemctl reload sshd     # Fedora

   Same service, different name on each distro. The playbook handles that with
   one handler per distro.

5. From a second terminal on a different machine, make sure key login still works:

       ssh atlas "echo ok"

   Only close the first session once this works.

## Note

`ssh atlas` run from atlas itself resolves to 127.0.1.1 and fails with
`Permission denied (publickey)`. Atlas doesn't have a key authorized for itself.
That's expected, not a hardening problem. Always test from another machine.

## Applied to

- atlas: by hand on 2026-08-10.
- macnode: already had the same file when Ansible first checked it on 2026-10-12.
  I don't know exactly when it went on. This runbook still said TODO, so the docs
  had fallen behind the server. Confirmed with `sshd -T`.
- Both hosts are managed by the Ansible task as of 2026-10-12.

When I first wrote this, I noted that macnode also offers GSSAPI auth and runs
Cockpit on the LAN. This file doesn't touch either one, and I haven't rechecked them.
