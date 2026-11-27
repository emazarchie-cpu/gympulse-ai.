# GymPulse AI door bridge for Hikvision terminals

Lets a Hikvision face, fingerprint or card terminal open the gym door only for members with an active
membership in GymPulse AI. The terminal reads the finger, face or card, asks the bridge, the bridge asks
GymPulse AI, and the terminal opens or shows the reason (for example "Membership expired 02 Nov 2026").

The bridge runs on any always-on computer inside the gym, on the same network as the terminals. This is
needed because Hikvision's remote verification has the platform call back into the terminal, and the
terminal sits inside the gym's network.

## What you need
- A Hikvision access terminal with **remote verification** (for example the DS-K1T341, DS-K1T343, DS-K1T670
  or DS-K1T673 series, on recent firmware). Check the model's settings before buying.
- An electric lock wired to the terminal's lock relay (your installer does this).
- An always-on computer on the same network: a mini PC, or the front-desk laptop if it stays on. Windows,
  Mac or Linux with Python 3.8 or newer. Give it a fixed IP address on the router.

## 1. Get the bridge
In GymPulse AI: **Settings → Check-in devices → Door access → Hikvision terminals**, download both files
into one folder: `gympulse_hikvision_bridge.py` and `bridge_config.json` (your door link is already filled in).

## 2. Add your terminals
Open `bridge_config.json` and, for each terminal, set its IP address, its admin user and password, and the
door name. Name a terminal on the inside of the door `Exit`: it always opens (fire safety) and records who
left. The passwords stay on this computer and are never sent to GymPulse AI.

## 3. Set up each terminal (web page or iVMS-4200)
1. **Network → Advanced → HTTP Listening** (sometimes "Event → Alarm server"): add the bridge computer's IP,
   port `8099`, URL `/`, protocol HTTP. Use **Test**: the bridge answers "running".
2. **Access Control → Parameter Settings → Terminal Parameters**: switch on **Remote Verification**. Set the
   timeout to 3–5 seconds. Leave "offline remote verifying unlocking" **off**, so unpaid members aren't let
   in when the internet is down.
3. **Person management**: for each member, set **Employee No.** to their GymPulse member code (8 letters
   and numbers, on their profile, Check-in tab), then enroll their fingerprint, face or card on the terminal.
   A card can also be linked in GymPulse instead (Door access → Give a member a card or key fob).

## 4. Start the bridge
```
python3 gympulse_hikvision_bridge.py
```
Leave it running (on Windows, add it to Task Scheduler "At startup"; on Linux, a systemd service). Each tap
shows a line such as `Main door 192.168.1.64 code=10D22DB8 -> OPEN (Welcome Yemi)`, and appears in
GymPulse AI under **At the door today**.

## If the internet goes down
With `"when_offline": "deny"` (the default), the door stays shut for everyone except the Exit terminal. Keep a
manual key or override at the front desk. Set it to `"allow"` to let everyone in while offline instead.
