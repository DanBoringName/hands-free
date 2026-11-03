# Phase 0 kill test: screen-off capture from a Bluetooth headset

The protocol was written on 3 November 2026, before any run. Each run is added at the end, dated, with the report `hands-free kill-test` wrote for it. A change to the protocol goes in the section it changes, dated, so a run can be read against the protocol it followed.

## What it decides

ADR-2026-11-03-voice-room-switchboard holds until this test says otherwise. With the phone locked and pocketed for 30 minutes:

- nothing may drop when Samsung's sleep timers fire,
- audio has to arrive continuously, and
- the headset mic has to be the one in use.

If Mumla passes, the transport stays and Phase 1 starts. If it fails, a new ADR moves the transport to a Discord voice channel (option 2 in `research/voice-room-switchboard.md`), and that transport takes this test next.

## How each check is measured

`hands-free kill-test` judges a run from two things it leaves behind: Murmur's log, and a recording of the room made by the Mumble desktop client. A check passes, fails, or is unsure when the evidence can't tell. Unsure is not a pass.

### Nothing dropped

Murmur 1.5 keeps its log in its database, and logs when it admits a client and when it closes the connection. A phone whose app has been put to sleep stops answering, and after 30 seconds Murmur logs `Timeout` and closes it. The check passes when one connection under the phone's name was open from before the recording started until after it ended. Mumla's auto-reconnect can stay on, because a reconnect is a second connection and fails the check.

### Audio arrived continuously

Under continuous transmit the phone sends audio all the time, even between words. The check assumes the recording client writes digital silence, exact zeros, where nothing arrived, and that a microphone never produces it. Any run of digital silence of 0.5 s or more is a gap, and one gap fails the check. Calibration A tests both assumptions.

### The headset mic was in use

Bluetooth's hands-free profile (HFP) carries the headset mic at 8 kHz with CVSD, or at 16 kHz with mSBC. Once the phone resamples it, nothing is left above 4 or 8 kHz, and the level falls off a cliff there. The phone's own mic reaches Opus at full band, and speech fades out gradually above a few kHz with no cliff. A phone in a pocket muffles its mic, but muffling is gradual too.

The check averages the spectrum over the loudest quarter of the recording, which is where the speech is. It then looks between 3 and 18 kHz for the sharpest fall in level from the 500 Hz below a frequency to the 500 Hz above it. A fall of 20 dB or more is a cut. A cut within 15% of 4 kHz or 8 kHz passes and names the codec. No cut fails, because the audio is full band. A cut anywhere else is unsure. The commonest cause would be an Opus bitrate too low for full band, which calibration B rules out.

This replaces the research report's covering of the phone's mic by hand, which a pocket does anyway.

## Setup, once

### The room, on the machine that runs the switchboard

1. Install Murmur. The package starts a service of its own on the same port, from `/etc`'s config, so stop it and keep it stopped:

   ```bash
   sudo apt install mumble-server
   sudo systemctl disable --now mumble-server
   ```

2. Let the phone through the firewall WSL sits behind. Its default is to block inbound, and the rule is for Private networks only, so the room is not reachable on a network Windows calls Public. Make sure the home network is set to Private. In an administrator PowerShell:

   ```powershell
   $wsl = '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'
   foreach ($protocol in 'TCP', 'UDP') {
       New-NetFirewallHyperVRule -Name "HandsFreeMurmur$protocol" `
           -DisplayName "hands-free Murmur ($protocol)" -Direction Inbound `
           -VMCreatorId $wsl -Protocol $protocol -LocalPorts 64738 `
           -Action Allow -Profiles Private
   }
   ```

3. Start the room in a terminal of its own, such as a tmux window. The first start makes the server password and says which file holds it. Ctrl-C stops the room.

   ```bash
   uv run --no-sync hands-free murmur
   ```

### The phone

- Mumla: add the server at this machine's address on the home network, port 64738, with the username `phone` and the server password.
- Mumla's audio settings: continuous transmit, the Bluetooth headset option on, and the input quality at its default or above. Note any noise suppression or preprocessing setting it has, which a run records.
- Android: Mumla's battery use set to Unrestricted, and Mumla added to Never sleeping apps. Microphone and notification permissions allowed.
- The headset paired with call audio on.

### The recording client

- The Mumble desktop client on Windows, joined to the room at `localhost` as `recorder`. It must not send any audio of its own, so set it to push-to-talk and mute it.
- Its recording window set to multichannel and WAV, so each user gets a WAV file of their own. The phone's is the one the kill test reads.
- Don't deafen it. A deafened client receives no audio, so it would record nothing. Turn the Windows volume down instead.

## Procedure

Before running, check that the room is running and Mumla has joined it, and that Mumla shows the headset as its mic. Run the two calibrations on the same day as the 30-minute run, with the same settings.

### Calibration A: the gap check works

Phone in hand, screen on, headset in use.

1. Start the recording.
2. Talk for a minute.
3. Mute Mumla for 10 seconds, counting them, then unmute.
4. Stay quiet for 10 seconds, unmuted, in a quiet room.
5. Talk for 30 seconds, then stop the recording.
6. Run `uv run --no-sync hands-free kill-test <the phone's WAV file> --user phone`.

The report should show exactly one gap, about 10 seconds long, where the mute was, and the headset check should pass. A second gap at the quiet 10 seconds means the headset gates silence down to digital silence. The 30-minute run then needs a steady sound near the headset, such as a fan or a radio, and its notes say so. No gap at the mute means the recording client doesn't write silence where nothing arrived, so the gap check can't be used.

### Calibration B: the band check works

Bluetooth off, so Mumla falls back to the phone's own mic. Record a minute of talking and run the kill test on it.

The headset check should fail with no cut, which shows it can tell the mics apart. A cut means Opus isn't coding full band. Raise Mumla's input quality and run calibration B again.

### The 30-minute run

1. Start the recording, with the phone in the room and the headset in use.
2. Lock the phone and put it in a pocket. Then go about something else for 30 minutes and leave the phone alone.
3. Talk at intervals throughout, at least five minutes in all, including some after 10, 20 and 29 minutes.
4. After 30 minutes, take the phone out, stop the recording, and only then leave the room, so the connection outlasts the recording.
5. Run the kill test on the phone's WAV file, and add the run below.

The kill test takes the recording's start from its file's modification time less its length. A file copied somewhere that changed its time needs `--start` with the time the recording started.

## Recording a run

Each run gets a section headed with its date, the time it started, and which of calibration A, calibration B or the 30-minute run it was, such as `### 2026-11-04 21:30, calibration A`. Under the heading:

- the phone, its One UI version, Mumla's version and its transmit, quality and noise suppression settings,
- the headset, and the Bluetooth codec if the phone shows it,
- the machine and the Murmur version the room ran on,
- anything that was not as the protocol says,
- the report, as `hands-free kill-test` wrote it, and
- the verdict, with what follows from it.

The report names the recording by its file name only. Check that no line of it names a person or a home folder before adding it.

## Runs

None yet.
