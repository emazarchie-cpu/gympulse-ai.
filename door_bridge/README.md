# GymPulse AI door setup (Hikvision)

## What this does
A member shows their face, finger or card at the terminal by the door.
- **Paid:** the door opens.
- **Not paid** (expired, suspended or on hold): the door stays shut.

Every entry also counts as a check-in in GymPulse AI.

**It keeps working when the internet drops.** Every few minutes GymPulse AI copies each member's
paid-until date onto the terminal, so the terminal decides by itself. Entries made while the internet is
down are saved on the gym computer and sent to GymPulse AI when it's back.
When a member renews, the terminal knows within a few minutes, once the internet is up.

## What you need
1. **A Hikvision face terminal**, for example the DS-K1T343, DS-K1T341, DS-K1T670 or DS-K1T673 series.
2. **An electric lock** wired to the terminal, plus an exit button inside. Your installer does this.
   The lock must be **fail-safe**: the door releases if the power fails.
3. **One computer at the gym that stays on.** A mini PC or the front-desk laptop. It needs Python 3.8 or newer
   (free from python.org). Ask your installer to give the computer and the terminal fixed IP addresses on
   the router.

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
- `"door"`: a name for the door, for example `Main door`. If you also have a terminal on the way out,
  call it **Exit**: everyone can always leave.

Save the file. The passwords stay on this computer. They are never sent to GymPulse AI.

## Step 3: Set up the terminal
Open the terminal's web page (type its IP address in a browser) or use iVMS-4200.
1. Find **HTTP Listening** (sometimes called *Event Alarm IP / Alarm Server*).
   Enter the computer's IP address and port **8099**. Press **Test**.
2. Make sure **Remote Verification** is **off**. The terminal decides by itself.

## Step 4: Start the bridge
Double-click `gympulse_hikvision_bridge.py`, or open a terminal in the folder and type:
```
python3 gympulse_hikvision_bridge.py
```
Within a minute it says **"updated … member(s)"**: every current member is now on the terminal, with
their member code as the *Employee No.* and their paid-until date.
Keep it running. To start it by itself when the computer turns on, ask your installer to add it to
*Task Scheduler* (Windows) or as a service (Linux).

## Step 5: Scan each member's face, finger or card
Only for members who agreed (GymPulse AI → Door access → Face and fingerprint consent).
1. On the terminal, open **User** and find the member by name. GymPulse AI already added them.
2. Add their face, then their fingerprint or card if they want one.

New members appear on the terminal by themselves within a few minutes of being added in GymPulse AI.
Cards linked to a member in GymPulse AI are copied to the terminal too.

## Check it works
1. Ask a paid member to try the door. It should open.
2. Ask a member whose plan has expired to try. It should stay shut.
3. In GymPulse AI, **Door access → At the door today** shows both, within a minute.
4. Unplug the internet and try again. The door still opens for the paid member. Plug it back in: the entry
   appears in GymPulse AI within a minute.

## Good to know
- **The computer must stay on** to send new dates and entries. If it's off, the terminal keeps using the
  last dates it had, so the door still works.
- **Renewals during an internet outage** reach the terminal when the internet is back. Until then, staff
  can let the member in with the exit button.
- **If the door ever won't open** (power cut, fault), the lock releases when the power goes off. Keep the
  break-glass release by the door.
- **Live check instead** (needs internet on every tap): set `"mode": "remote"` in the config file and turn
  Remote Verification on in the terminal. Most gyms should keep `"sync"`.
