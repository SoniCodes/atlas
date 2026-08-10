# Runbook: SSH hardening

Disable password authentication on a host so only key auth is accepted.

## Gotcha: drop-in ordering is FIRST match wins

`/etc/ssh/sshd_config` has `Include /etc/ssh/sshd_config.d/*.conf` and sshd uses the
**first** value it finds for each setting. Files are read in lexical order, so
`50-cloud-init.conf` beats `99-anything.conf`.

Name the file with a LOW number (`01-hardening.conf`) so it is read first.

This is the OPPOSITE of netplan, where higher-numbered files win.

## Procedure

Keep your current SSH session open through the entire procedure. Do not close it
until step 5 passes.

1. Check the current effective config. `sshd -T` shows the result after all includes,
   which is what actually matters — not what any single file says.

       sudo sshd -T | grep -iE 'passwordauthentication|kbdinteractive|permitrootlogin'

2. Create the drop-in:

       sudo nano /etc/ssh/sshd_config.d/01-hardening.conf

       PasswordAuthentication no
       KbdInteractiveAuthentication no
       PermitRootLogin prohibit-password

3. Validate syntax BEFORE applying. If this errors, fix it and do not continue.

       sudo sshd -t && echo "SYNTAX OK"
       sudo sshd -T | grep -iE 'passwordauthentication|kbdinteractive|permitrootlogin'

   The second command confirms your file actually won the ordering fight.

4. Reload (not restart — reload keeps existing connections alive):

       sudo systemctl reload ssh

5. From a SECOND terminal on another machine, confirm key auth still works:

       ssh atlas "echo ok"

   Only close the original session after this succeeds.

## Note

Running `ssh atlas` from Atlas resolves to 127.0.1.1 and fails with
`Permission denied (publickey)` — the host has no key authorized for itself. That is
expected and is not a failure of the hardening. Always test from a different machine.

## Applied to

- atlas — 2026-08-10
- macnode — TODO (also offers gssapi; also runs Cockpit on the LAN)
