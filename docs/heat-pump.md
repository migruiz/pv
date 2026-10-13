# Heat pump: settings and how to change them

The house's Samsung heat pump heats the hot water cylinder and the house. This page records how it was set
on **12 October 2026**, when the house moved to Electric Ireland Home Electric+ Night Boost, and how to read
and change each setting on the wall controller. It is the starting point for any calendar of seasonal changes.

Night Boost prices (from 13 Oct 2026, incl. VAT): **02:00-04:00 10.88c**, rest of the night (23:00-08:00)
18.54c, day (08:00-23:00) 37.60c. So hot water, appliances and battery charging belong in 02:00-04:00.

## The equipment

- **Heat pump**: Samsung EHS air-to-water. The cylinder has an electric **booster heater** (about 3 kW, like a
  kettle element); the heat pump itself can heat the tank to 50°C at most (field setting 3021).
- **Wall controller**: the wired controller from Samsung's EHS control kit **MIM-E03AN** (icon sheet
  DB68-03252A-02). Buttons: On/Off, Mode, Set, Timer, User Set, View, Silent, Outing, +/-, arrows, Set, ESC,
  Delete, and a DHW box with its own On/Off and Mode.
- **Manual**: [MIM-E03AN user manual (PDF)](https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?CDSite=UNI_IE&OriginYN=N&ModelType=N&ModelName=MIM-E03AN&CttFileID=6546345&CDCttType=UM&VPath=UM%2F201607%2F20160704121916468%2FEHS_MONO-KIT_IB_05402A-03_EN_160627.pdf),
  from [Samsung Ireland support](https://www.samsung.com/ie/support/model/MIM-E03AN/). Page numbers below are
  the manual's "ENGLISH-xx" pages.
- The screen shows the **"centralized control is being connected"** icon (a small controller with a signal),
  so something else is linked to the heat pump, possibly a Samsung Wi-Fi kit and the SmartThings app. Not
  checked yet.

## Current settings (12 October 2026)

### Clock

| Setting | Value | Why |
|---|---|---|
| Controller clock | **About 4 minutes slow on purpose** (showed 12:41 when it was 12:45) | Anything set for "02:00" starts a few minutes after 2am, inside the cheap window. The clock gains time, so slow is the safe side |
| Summer time | On, weekly, last Sunday of March to last Sunday of October (User Set menu 3) | It changes the hour by itself |
| Date | Set to 12 Oct 2026 (User Set menu 2) | Summer time needs the date |

**Real time = controller time + about 4 minutes.** Before 12 Oct the clock was about 53 minutes slow (no
summer time, plus drift), and the old timers had been set to suit it.

### Hot water (DHW)

| Setting | Controller | Real time / note |
|---|---|---|
| Mode | **Power** (tap icon with 3 dots) | Booster heater and heat pump together from the start: fastest. Kept on purpose so the tank is done early and 3-4am stays free for heating the house |
| Target temperature | **55°C** (raised from 50°C on 12 Oct) | Above 50°C is all booster heater. Needs field setting 1051 at 55 or more |
| Daily timer 1 | **02:00 On, DHW** | About 02:04 |
| Daily timer 2 | **03:05 Off, DHW** | About 03:09 |

Last month (to 50°C) the tank took 25-56 minutes, drawing about 5 kW from the start. 55°C adds roughly 20
minutes. If the data shows heating still running when the 03:05 timer cuts it off, move the Off time later.

### Weekly anti-bacteria heat (disinfection, field settings 3041-3046)

| Code | Value | Meaning |
|---|---|---|
| 3041 | 1 | On |
| 3042 | **Sunday** (was Tuesday until 12 Oct) | Day: 0 Sun, 1 Mon, 2 Tue, ... 6 Sat, 7 every day |
| 3043 | **2** (was 3) | Start hour, so about 02:04 real, together with the daily heat |
| 3044 | **60°C** (was 55°C until 12 Oct) | Target, above the daily 55°C so it actually kills bacteria |
| 3045 | 15 | Minutes held at the target |
| 3046 | 8 | Hours before it gives up |

It runs whether or not the daily hot water timer is on. It is the hot water that ran every Tuesday morning
while the house was empty on holiday. The old Tuesday run drew about 3.3 kW for 30-40 minutes.

### House heating

| Setting | Value | Note |
|---|---|---|
| Operation | Heat mode on (sun icon) | Runs only when the house is below its target; no early-morning heating seen in Sep-Oct |
| "Set 5.0°C" beside the heating-curve icon | Probably the heating-curve shift at **+5°C**, the maximum | See "Heating curve" below. **Decide when the heating starts** |
| Weekly timers (house heating) | **Not read yet**: read and set them when the heating is turned on | |
| Plan | Heat 03:00-04:00 when it gets cold, with hot water done by about 03:09; morning heating 05:00-08:00 at the night rate | |

### Heating curve (water law, p.16 and p.40-41)

The heat pump does not heat the house to a fixed water temperature. It follows a **heating curve**: the
colder it is outside, the hotter the water it sends round the house. The installer sets the curve's two
ends (field settings 2011/2012 outdoor temperatures, factory -10°C and 15°C; 2021/2022 water temperatures
for underfloor, factory 40°C and 25°C; 2031/2032 for radiators, factory 50°C and 35°C; 2041 which of the two
is used). The **+/-** buttons then **shift the whole curve up or down by up to 5°C**. "Set 5.0" most likely
means it is shifted up by the full +5°C.

- **Cost**: a heat pump gets roughly 2-3% less efficient for every 1°C hotter water, so +5°C uses roughly a
  tenth more electricity for heating, for the same warmth, if the house didn't need it.
- **But with heating done in the cheap night hours**, hotter water at 3-4am and 5-8am stores more heat in the
  house to coast through the day, and the extra electricity costs 10.88c or 18.54c, not the 37.60c day rate.
  So +5 may be deliberate and worth keeping.
- **Test when the heating starts**: lower it 1°C at a time, a few days each, and stop where the house is still
  warm enough in the evening. Read the curve's ends first (view only: **Set + ∧**, main menu **20**).

### Screen (User Set menu 4)

Backlight 4 seconds, green light on, red warning light on (as seen on 12 Oct). 30 seconds makes menus easier.

## How to use the controller

### Just looking (changes nothing)

- **Temperatures now**: press **View** repeatedly: indoor, outdoor, water leaving the heat pump, then the
  hot water tank (p.19).
- **Targets**: press **Set** repeatedly: heating target, then hot water target (p.19).
- **Hot water mode**: hot water must be on (the DHW box shows on the screen). The dots beside the tap icon:
  1 Economic (heat pump only, aims 5°C below target), 2 Standard (booster joins after 20 min), 3 Power
  (booster from the start), basin + tap + 3 dots Forced (p.17). To see it outside the timer, press the DHW
  power button, read it, press it again.
- **Daily timers (hot water)**: **Timer**, **∧/∨** to **Daily**, **>**, **∧/∨** to timer 1. A blinking box
  around the number means it is in use. **>** steps through hour, minute, On/Off, DHW/Silent. **<** back to the
  number, **∧/∨** for the next. **ESC** to leave (p.24-25).
- **Weekly timers (house heating)**: **Timer**, **∧/∨** to **Weekly**, **>**, pick a day, **>**, pick timer
  1-8, **>** through time, On/Off, mode, temperature. **ESC** to leave (p.20-21). A line under a day letter on
  the main screen means that day has weekly timers.
- **Installer settings, view only**: hold **Set + ∧** for 3 seconds. **∧/∨** to the main menu (e.g. 30),
  **>**, **∧/∨** to the sub-menu (e.g. 44), **>** shows the value, **<** back, **ESC** to leave (p.35).

### Changing things

- **Hot water target**: **Set** until the hot water target shows, then **+/-** (p.16, 19). It stops at the
  limit in field setting 1051.
- **Hot water mode**: with hot water on, press **Mode in the DHW box**; each press moves to the next mode.
- **A daily timer**: **Timer**, **Daily**, **>**, pick the number, **>**, then AM/PM, hour, minute, On or
  Off, DHW or Silent, each with **∧/∨** and **>**; **Set** saves (p.24-25). One timer is one moment: a
  start is an "On" timer, an end is a separate "Off" timer. The hot water mode and target are not part of
  the timer; they apply to everything.
- **Clock**: **User Set**, menu **2**, **>**. Sub-menu **1** year, **2** month and day, **3** weekday, hour,
  minute; **Set** after each (p.28-29). **Keep it about 5 minutes behind your phone**: set the minute 5 less
  and press Set as the phone's minute changes.
- **Installer settings**: hold **Set + ∨** for 3 seconds (editing mode). Choose main menu and sub-menu as
  above, change with **∧/∨**, **Set** saves. The manual says to switch the heat pump's power off and on after
  changing these (p.34, 36).

### Don't

- **Never hold Delete for 5 seconds**: it wipes every weekly timer, with no undo (p.23).
- While only looking, don't press **Set** (saves what is on screen) or **Delete** (removes that timer).
- **Set + ESC** opens the installer's service menu (p.32): leave it alone.

### User Set menus (p.27)

| Menu | Sub-menu | What |
|---|---|---|
| 1 Locks | 1 | All buttons locked (0/1) |
| | 2 | Partial lock, four digits: on/off button, mode button, temperature buttons, **timer buttons** |
| 2 Clock | 1 / 2 / 3 | Year / month and day / weekday, hour, minute |
| 3 Summer time | 1 | On or off, and by week or by date |
| | 2 / 3 | Start / end by week (default last Sunday of March / October) |
| | 4 / 5 | Start / end by fixed date (only if "by date") |
| 4 Screen | | Backlight 0-30 s, green light, red light |
| 0 Reset | | Back to factory values, except the clock |

## Installer settings worth knowing (field settings, p.36-49)

| Code | What | Factory value |
|---|---|---|
| 1051 / 1052 | Highest / lowest hot water target you can choose | 50 (up to 70) / 40 |
| 3021 | Highest tank temperature from the heat pump alone | 50 (45-50) |
| 3022 / 3023 | Heat pump stops at target + 2°C / restarts at target − 5°C | 2 / 5 |
| 3025 | Longest hot water turn when the house also wants heat (they take turns) | 30 min |
| 3026 | Longest house-heating turn | 3 h |
| 3031 | Booster heater in use | 1 |
| 3032 | Booster delay in Standard mode | 20 min |
| 3041-3046 | Weekly anti-bacteria heat (see above) | On, Friday, 23:00, 70°C, 10 min, 8 h |
| 4011 | Who goes first: 0 hot water, 1 house | 0 |
| 5021 | How far below target Economic mode stops | 5°C |

## Calendar: when to change what

| When | Change |
|---|---|
| Now (Oct 2026, no house heating yet) | Battery charges 02:01-03:59 (FusionSolar app, set 12 Oct), then powers the house the rest of the day |
| When the house heating starts (expected end of Oct 2026) | Battery charge period **02:01-07:59** (and discharge from 07:59), so it fills 2-4am and stays full through the morning heating; widen the API's night-charge check (`NIGHT_CHARGE`) to 08:00. Read and set the weekly heating timers. Read the heating curve and test lowering the +5 shift |
| Morning after any timer change | Check the Pi's minute history (`/data/history.sqlite3`): hot water should start about 02:04 and stop by itself before about 03:09; Sundays the weekly heat also starts about 02:04 |
| Last Sunday of October and of March | Clocks change. The controller follows by itself; check it is still about 5 minutes slow |
| March 2027 | Supplier changes for the summer: re-time the hot water, the weekly heat and the battery to the new cheap hours |

## Other night-time appliances

- **Washing machine** (Samsung WW90TA046AN, 9 kg): start at 2am. Delay End sets the **finish** time in whole
  hours, so set it to 2am plus the programme time, rounded up (full ECO 40-60 is 3h48: finish at 6am, starts
  about 2:12). Most of its electricity goes on heating water early in the cycle. Times: ECO 40-60 3h48 full,
  2h54 half, 2h36 quarter; Cotton 60°C 2h25 (1.5 kWh); Synthetics 40°C 2h25; 15' Quick Wash 0h15.
- **Dishwasher**: starts at 2am; its last hot step sometimes runs past 4am. A daytime test to time its
  heating is still to do.
- Running everything at 2am is fine for the supply: the house has peaked at about 7.4 kW (8.6 kW max) at 2am,
  plus about 2.2 kW of battery charging, with no problems.
