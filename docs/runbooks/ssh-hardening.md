# Runbook: SSH hardening

Disable password auth so the host only accepts keys.

## Gotcha: drop-in ordering is first match wins

`/etc/ssh/sshd_config` has `Include /etc/ssh/sshd_config.d/*.conf`, and sshd uses
the **first** value it finds for each setting. Files are read in lexical order, so
`50-cloud-init.conf` beats `99-anything.conf`.

Name the drop-in with a low number (`01-hardening.conf`) so it wins.

This is the opposite of netplan, where higher numbers win.

## Procedure

Keep your current SSH session open the whole time. Do not close it until step 5
passes.

1. Check the effective config. `sshd -T` is what actually matters. That's the
   result after every include, not what any one file says.

       sudo sshd -T | grep -iE 'passwordauthentication|kbdinteractive|permitrootlogin'

2. Create the drop-in:

       sudo nano /etc/ssh/sshd_config.d/01-hardening.conf

       PasswordAuthentication no
       KbdInteractiveAuthentication no
       PermitRootLogin prohibit-password

3. Validate syntax before applying. If this errors, fix it and stop.

       sudo sshd -t && echo "SYNTAX OK"
       sudo sshd -T | grep -iE 'passwordauthentication|kbdinteractive|permitrootlogin'

   The second command confirms your file actually won the ordering fight.

4. Reload, not restart. Reload keeps existing connections alive:

       sudo systemctl reload ssh

5. From a second terminal on another machine, confirm key auth still works:

       ssh atlas "echo ok"

   Only close the original session after that succeeds.

## Note

Running `ssh atlas` from Atlas itself resolves to 127.0.1.1 and fails with
`Permission denied (publickey)`. The host has no key authorized for itself.
That's expected. Always test from a different machine.

## Applied to

- atlas, 2026-08-10
- macnode, TODO (also offers gssapi; also runs Cockpit on the LAN)
