# GymPulse AI door setup (Hikvision)

## What this does
A member puts their finger, face or card on the terminal at the door.
GymPulse AI checks their membership.
- **Paid:** the door opens, and the screen says "Welcome".
- **Not paid:** the door stays shut, and the screen says why, for example "Membership expired 02 Nov 2026".

Every entry also counts as a check-in in GymPulse AI.

## What you need
1. **A Hikvision terminal** that has *Remote Verification*. For example the DS-K1T341, DS-K1T343, DS-K1T670 or
   DS-K1T673 series. Check this before you buy.
2. **An electric lock** wired to the terminal. Your installer does this.
3. **One computer at the gym that stays on.** A mini PC or the front-desk laptop. It needs Python 3.8 or newer
   (free from python.org). Ask your installer to give it a fixed IP address on the router.

## Step 1: Download the files
In GymPulse AI, go to **Settings → Check-in devices → Door access → Hikvision terminals**.
Download all 3 files and put them in one folder on the computer:
- `gympulse_hikvision_bridge.py` (the bridge)
- `bridge_config.json` (your settings, with your door link already in it)
- this guide

## Step 2: Fill in the config file
Open `bridge_config.json` in Notepad. For each terminal, change:
- `"ip"`: the terminal's IP address, for example `192.168.1.64`
- `"password"`: the terminal's admin password
- `"door"`: a name for the door. Use **Exit** for the door people leave through. It always opens.

Save the file. The passwords stay on this computer. They are never sent to GymPulse AI.

## Step 3: Set up each terminal
Open the terminal's settings (on its web page or in iVMS-4200).
1. Find **HTTP Listening** (sometimes called *Alarm Server*).
   Enter the computer's IP address and port **8099**. Press **Test**.
2. Find **Remote Verification** (under *Access Control → Terminal Parameters*). Turn it **on**.
   Set the wait time to 3–5 seconds.
   Leave *offline remote verifying unlocking* **off**.

## Step 4: Start the bridge
Double-click `gympulse_hikvision_bridge.py`, or open a terminal in the folder and type:
```
python3 gympulse_hikvision_bridge.py
```
Keep it running. To start it by itself when the computer turns on, ask your installer to add it to
*Task Scheduler* (Windows) or as a service (Linux).

## Step 5: Add members to the terminal
For each member:
1. Open their profile in GymPulse AI and copy their **member code** (8 letters and numbers).
2. On the terminal, add a person. Put the member code in **Employee No.**
3. Scan their finger, face or card.

## Check it works
Ask a paid member to tap in. The door should open.
In GymPulse AI, **Door access → At the door today** shows every entry, and every refusal with the reason.

## If the internet is down
The door stays shut, except the Exit door. Keep a key or a manual switch at the front desk.
To let everyone in when the internet is down, change `"when_offline"` to `"allow"` in the config file.
