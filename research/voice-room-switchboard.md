# Hands-free voice for a Claude Code fleet: a "voice room" switchboard with one coordinator Claude

Written in October 2026 and kept as written, in its own voice and spelling. Prices, policies and product states are as of the dates given against them.

Build it yourself, but keep it small. Put the phone on a permanent open-mic voice call (a self-hosted Mumble room, with a Discord voice channel as the fallback), and have a small switchboard daemon in WSL on the desktop listen to that call, transcribe it, route by spoken name, and speak replies back into the call. Your preferred coordinator Claude sits behind the switchboard, and spoken keywords give you direct routing to named sessions as well, so you get both of your options. Nothing on the market today does screen-off, headset-mic, multi-session voice to Claude Code from an Android phone. Treating the phone as "on a call" is the one approach that avoids every Android restriction you have already run into.

## TL;DR

- **Recommendation:** an open-mic voice call from phone to desktop, plus a self-built switchboard (Silero VAD → faster-whisper on CUDA → name routing → Kokoro/Piper TTS back into the call). It runs one coordinator Claude Code session and named worker sessions, connected through your existing voice-inbox channel server. Cost is £0/month and the build is roughly 20–30 hours, starting with a 2–3 hour kill test of screen-off headset-mic capture.
- **Why not an existing app:** VoiceMode removed its phone-capable LiveKit transport in 8.0.0, and its new phone calling is still pre-release. Claude app voice mode doesn't work with Claude Code. Remote Control and Dispatch are text-only. Home Assistant's Android wake word works with the phone locked, but it records from the phone mic, not the Bluetooth headset mic.
- **Reach:** local Claude Code sessions get full two-way voice. Cloud sessions get voice-to-send via `claude -p "msg" --cloud <id>`, but replies are not returned to the CLI. claude.ai chats have no supported programmatic route, so keep using the Claude app's own voice mode for those.

## Key Findings

### Existing products (what each one actually does for you)

| Option | Screen-off / pocket | Headset mic | Wake word / open mic | Reach | Verdict |
| --- | --- | --- | --- | --- | --- |
| VoiceMode MCP (mbailey) | No today | Host machine only | Silence detection | Local CC only | The LiveKit transport and its web client "were removed in 8.0.0", and `voicemode serve` "uses the host machine's mic and speakers". On 20 Oct 2026 the owner said phone calling, multi-agent voice, ambient voice and barge-in are "Done", but ready for testers only after fixes.\[1\] Worth watching, not something to build on yet. |
| dictare / OpenVIP | No (local mic) | PC mic | Yes, plus voice agent switching ("agent coding") | Local CLI agents | Good model for keyword switching; doesn't solve the phone.\[2\] |
| Claude app voice mode | Needs the app open | Yes | Hands-free by default | claude.ai chats only | Taku AI's guide says voice mode "does not work with Claude Code or Cowork… Voice mode is a Chat feature. The Code tab and the CLI don't have it." Right tool for (c), wrong tool for (a)/(b). |
| Remote Control / Dispatch / Code tab | Needs screen | n/a (text) | No | Local + cloud CC | Good for visual review and approvals; not a voice path. |
| Claude Code `/voice` | n/a | Local mic only | Push-to-talk | One local session | Docs: it "needs local microphone access, so it does not work in remote environments".\[3\] |
| Home Assistant Assist (Android + Wear OS) | Yes: wake word "works even when your device is locked" | **No: phone mic only** | On-device microWakeWord (Hey Jarvis / Okay Nabu / Hey Mycroft)\[4\] | Any agent via a webhook conversation integration | Best watch path; poor pocket path. |
| AgentWire, tmux-agent (LiveKit) | Browser/room UI | Phone | Push-to-talk / realtime | Local tmux sessions | Closest prior art for multi-session voice; browser-bound.\[5\]\[6\]\[7\] |

### Android realities (these explain your MacroDroid failures)

- A microphone foreground service can't be created while an app is in the background. Android's docs say "you cannot create a microphone foreground service while your app is in the background", even if other background-start exemptions apply.\[8\] An app *can* keep listening with the screen off if its mic service was started while it was in the foreground. That is how call and voice-chat apps work, so the "always on a call" design falls inside the rules.
- Bluetooth headset mic audio travels over HFP/SCO: CVSD at 8 kHz, or mSBC "wideband speech" at 16 kHz on HFP 1.6.\[9\]\[10\] Whisper models resample to 16 kHz anyway, so mSBC is enough for good STT. CVSD at 8 kHz will raise error rates noticeably.\[11\] While SCO is open, music drops to call quality, so treat talk mode like being on a call.\[12\]
- Home Assistant's companion app "is hardcoded to use AudioSource.MIC".\[13\] A fix PR (#6436) was linked in Feb 2026, but I could not confirm that it merged.\[13\] A draft fork from Oct 2026 would use SCO only for headset-button launches, not for wake-word sessions.\[14\]
- Home Assistant wake-word detection keeps the CPU awake. HA's "Assist on Android" docs say it "has a noticeable impact on battery life" and uses more battery than "Ok Google" because "Google Assistant has access to dedicated low-power hardware". The Open Home Foundation reported battery use rising "from roughly 1% to roughly 15%" (per Kiril Peyanski's blog). In GitHub issue #6472 (22 Feb 2026), a Galaxy S22 Ultra user on app 2026.2.3 beta said it was "only using about 15% of my battery, which isn't great, but is far better than the 25-50%". A Home Assistant Community thread from 9 Mar 2026 ("only works once", reported on a Galaxy A40) described the wake word stopping after the first trigger; a reply says "The fix has been merged into 2026.4.1". PR #7750 addresses a related Galaxy S25 Ultra bug where the wake word was ignored after Assist was dismissed.

### Coordinator and billing facts

- Channels are a research preview. Custom channels still need `--dangerously-load-development-channels`. The channels reference includes a permission relay (`notifications/claude/channel/permission`), so permission prompts can be spoken and answered by voice.\[15\]
- Cloud sessions: `claude -p "msg" --cloud <session-id>` "queues the message into the session and exits without waiting for a reply". Teleport pulls a *copy* of the session locally. Cloud sessions count toward plan limits with "no separate charge for the cloud VM".\[16\]
- `claude -p` and the Agent SDK: Anthropic paused the 15 June 2026 change that would have moved them to a separate credit. Anthropic's support page says that, signed in with your plan, they "still draw from your subscription limits". An 7 Oct 2026 update added monthly API credits for Max.\[17\] This policy has changed twice this year, which is why the design below keeps workers as *interactive* sessions.
- claude.ai chats: I found no supported API for sending to or reading claude.ai chat threads. Scraping or automating the web app would be fragile and is likely against the consumer terms. Use Claude app voice mode for life chats.

## Ranked architectures

1. **Voice-room switchboard (recommended).** Mumla (a Mumble client) on the phone stays connected to a Murmur server on the desktop in continuous or voice-activated transmit. The switchboard bot receives your audio stream, wakes on session names, transcribes on the RTX 3080, routes, and plays TTS replies into the room, which you hear in the headphones.
   - Friction: unlock once to join the room, then nothing.
   - Wake: server-side names or openWakeWord. Phone mic and headset mic both work through the call stack.
   - Reach: local (a) is full duplex; cloud (b) is send-only plus status; (c) is not covered.
   - Risk: medium, mostly Mumla's Bluetooth handling (unverified, tested in Phase 0).
   - Cost: £0. Effort: 20–30 h.
2. **Same switchboard, with a Discord voice channel as the transport.** Reuses your Discord bot and the Discord app's proven Bluetooth call handling. Risk: bot voice *receive* is semi-supported and has broken before when Discord changed voice encryption (unverified for current DAVE end-to-end encryption). Cost £0, plus 4–6 h on top of option 1.
3. **Home Assistant Assist front end.** HA in Docker on the desktop, with the `webhook-conversation` integration (timeout configurable "1-300 seconds", default 30) pointing at the switchboard's `/ask` endpoint.\[18\] Wake word works with the phone locked, and a watch button launches Assist. The pipeline default timeout is 300 s, enough for 20–60 s Claude replies.\[19\]
   - Cons: phone mic only; experimental. HA must replace Claude as the phone's default assistant, though it can be the *watch's* default instead.\[20\]
   - Use it as the watch add-on rather than the main path. Cost £0 with local STT/TTS. Effort 4–6 h.
4. **Existing apps only.** Remote Control on every session (`/config` → enable for all sessions), Claude app Code tab for review, Dispatch for new tasks, voice mode for chats.\[21\] Zero build, but not voice for Code and needs the screen. Keep as the visual fallback.
5. **Today's Discord talk mode.** Keep as the text and notification fallback. SpeakThat still reads replies when you are not in the room.

Not recommended for now: OpenAI Realtime, Gemini Live or ElevenLabs as a "front desk", and Vapi/Retell/Twilio phone numbers. They add per-minute cost and a second model that would hand off to Claude anyway, and the local Whisper/Kokoro pipeline already meets the latency target. I did not price these in this research, so treat that as a gap if you want to revisit them.

## Recommended design

**Flow:** phone/headset → Mumla (call audio, Opus) → Murmur (desktop, WSL or Windows) → switchboard bot (Python, `pymumble`):

- Silero VAD segments your speech.
- faster-whisper `large-v3-turbo` or `distil-large-v3` on CUDA transcribes each utterance.
- The router then sends the text to the right session.
- Replies are queued, spoken with Kokoro (GPU) or Piper (CPU/laptop), and played into the room.

**Routing grammar:**

- "cpomdp: run the tests" goes straight to that session (direct-keyword mode).
- Anything with no name goes to the **coordinator**, a Claude Code session in your hub folder with `--add-dir` access. It has a switchboard MCP with `list_sessions`, `send(name, text)`, `start_session(repo, name)`, `status(name)` and `cloud_send(id, text)`. It decides, delegates, and summarizes.
- "Coordinator, what's everyone doing?" gets one spoken roll-up.
- Every spoken reply is prefixed with the speaker ("cpomdp says…"), so you always know who is talking.

**Workers** are interactive `claude` processes in tmux (one per repo). They run your voice-inbox channel, extended with:

- a `reply` tool that POSTs back to the switchboard instead of Discord;
- the permission relay, so the switchboard can ask "cpomdp wants to run rm -rf build — yes or no?";
- the appended "short speakable replies; offer details on request" system prompt.

Interactive sessions sidestep the Agent SDK billing question entirely. The Agent SDK with session resume is the cleaner programmatic alternative if channels change, at the cost of that policy risk.

**Interruptions:**

- "Stop" or "cancel" sends `tmux send-keys Escape` to the named or last-active session.
- Barge-in: the bot stops TTS playback as soon as VAD detects your voice.
- Background completions: a `Stop`/`Notification` hook in each worker POSTs to the switchboard, which says "cpomdp finished" between your utterances.

**Cloud sessions:**

- `claude --cloud "task"` creates one, and `claude -p "msg" --cloud <id> --output-format json` sends follow-ups (returns `{ok, session_id, url}`).\[16\]
- There is no reply stream, so the switchboard reports "sent". For results, the coordinator checks the PR/branch with `gh`, or teleports a snapshot to summarize. Use cloud for fire-and-forget work and local sessions for conversation.

**Networking:**

- Home Wi-Fi first: Murmur on port 64738, using your existing mirrored networking and firewall rule.
- Away from home: Tailscale Personal, which is free for non-commercial use. Tailscale's pricing page (checked 25 Oct 2026) lists "six users, unlimited user devices, 50 tagged resources"; the six-user allowance moved into the free plan with the 8 April 2026 pricing v4 change. Bind Murmur to the tailnet only, use a server password plus certificate auth, and never port-forward. Cloudflare Tunnel doesn't suit UDP voice.
- Keep the desktop awake: set Windows sleep to "Never" on AC, or use PowerToys Awake.

## Phased build plan (≈20–30 h)

| Phase | Work | Hours | Reuses | Kill test (stop or switch if it fails) |
| --- | --- | --- | --- | --- |
| 0 | Murmur on desktop; Mumla on phone; voice-activated transmit; Bluetooth headset option on | 2–3 | Mirrored networking, firewall rule | Lock the phone, pocket it, talk 30 min. Audio arrives continuously, the headset mic is used (cover the phone mic), and there are no drops after Samsung's sleep timers. If it fails, try the Discord voice channel (Option 2), then a minimal custom Kotlin app (≈10–15 h). |
| 1 | Bot: receive PCM → VAD → faster-whisper CUDA → log; TTS → room | 4–6 | Your faster-whisper script | Under 5% wrong words on 50 coding phrases over HFP audio. STT+TTS overhead under 1.5 s. |
| 2 | Name router, session registry (YAML: name → tmux/repo/machine or cloud id), voice-inbox `reply` tool, coordinator MCP | 5–7 | voice-inbox server, tmux "talk" launcher | Three sessions answer correctly by name. Coordinator delegates and summarizes. |
| 3 | Permission relay by voice, "stop", barge-in, completion hooks | 3–4 | Channel permission relay | 10 permission prompts answered by voice with no wrong approvals. |
| 4 | Cloud send/create, `gh`-based status | 2–3 | — | Follow-up lands in a cloud session from voice. |
| 5 | Tailscale, laptop as second worker host (send to its voice-inbox over the tailnet), power settings | 2–3 | — | Works on mobile data. |
| 6 (bonus) | HA in Docker + webhook-conversation → `/ask` (timeout 120 s); watch double-press → HA Assist | 3–4 | — | Watch question answered within the timeout. |

The laptop is CPU-only. Run STT centrally on the desktop, or fall back to Groq's free Whisper tier. Groq's rate-limit and speech-to-text docs (prices as of 27 Oct 2026) give the free tier 20 requests/minute, 2,000 requests/day, 7,200 audio-seconds/hour and 28,800 audio-seconds/day. Paid `whisper-large-v3-turbo` costs "$0.04 per hour of audio", with a "minimum 10 seconds billed per request".

## Phone and watch checklist

- **Phone (Samsung One UI):**
  - Set Mumla to **Unrestricted** battery and add it to **Never sleeping apps**.
  - Allow microphone and notifications for Mumla.
  - In Mumla: voice activity (or continuous) transmit, Bluetooth audio on, auto-reconnect on.
  - Turn off "pause music on disconnect" style automations.
  - Keep SpeakThat's Discord rule as the fallback.
  - Keep the Claude app as the default assistant for chats.
- **Headphones:** Pair the Q20i for calls ("Call audio" on in Bluetooth settings). Expect call-quality audio while in the room. Leave the room to get A2DP music quality back.\[12\]
- **Watch (Galaxy Watch6/7):** Install the Home Assistant Wear OS app. Under Settings → Advanced features → Customize keys, set Home key double-press → "HA: Assist".\[4\] Select the switchboard pipeline in Assist.

## Caveats

- **Unverified:** Mumla's Bluetooth SCO handling with the screen off on One UI, and whether it negotiates mSBC with the Q20i. Phase 0 exists to prove this.
- **Unverified:** Discord bot voice receive under current encryption.
- **Unverified:** how the Wear OS Assist app captures audio, and its own timeout.
- **Unverified:** whether claude.ai connectors are usable from Claude Code for the coordinator.
- **Research previews that may change:** channels (including the development flag), Remote Control, Dispatch, cloud-session CLI flags, and HA's "experimental" Android wake word.\[4\]\[22\]
- **Policy risk:** Anthropic's programmatic-use billing (`claude -p` and the Agent SDK) changed in Feb, May/June and Oct 2026.\[17\]\[23\]\[24\] Re-check before relying on SDK-driven workers.
- **Android 17** tightens background audio rules for apps targeting it. Call-style apps with a proper foreground service should be unaffected, but re-test after updates.\[25\]

## Sources

1. [Feature request: use VoiceMode from a phone (talk to a desktop Claude Code session while away) · Issue #563 · mbailey/voicemode](https://github.com/mbailey/voicemode/issues/563)
2. [GitHub - dragfly/dictare: Voice interaction layer for AI coding agents and beyond. Open protocol (OpenVIP), 100% local. · GitHub](https://github.com/dragfly/dictare)
3. [\> ## Documentation Index](https://code.claude.com/docs/en/voice-dictation.md)
4. [Assist on Android](https://www.home-assistant.io/voice_control/android/)
5. [pypi.org](https://pypi.org/project/agentwire-dev/1.6.0/)
6. [pypi.org](https://pypi.org/project/agentwire-dev/1.3.0/)
7. [GitHub - yepher/tmux-agent: An agent that knows how to use tmux so it can run tools like claude and control them via voicec. · GitHub](https://github.com/yepher/tmux-agent)
8. [Foreground service types | Background work | Android Developers](https://developer.android.com/develop/background-work/services/fgs/service-types)
9. [AN992: HANDS-FREE AND HEADSET PROFILES iWRAP APPLICATION NOTE](https://www.silabs.com/documents/public/application-notes/AN992.pdf)
10. [HFP (Hands-Free Profile - Bluetooth)](https://www.we-fuzz.io/blog/hfp-hands-free-profile---bluetooth)
11. [Smart Bluetooth Headset For Speech Command](https://patents.justia.com/patent/20180295656)
12. [Why Does My Mic Sound So Much Worse on a Wireless Headset Compared to Wired?](https://www.turtlebeach.com/blog/wireless-vs-wired-headset-microphone-quality)
13. [Bluetooth headset microphone not used for Assistant voice input (audio input remains on phone mic)](https://github.com/home-assistant/android/issues/6433)
14. [Fix Bluetooth microphone capture for headset-triggered Assist by mbush91 · Pull Request #1 · mbush91/ha-android · GitHub](https://github.com/mbush91/ha-android/pull/1)
15. [Channels reference - Claude Code Docs](https://code.claude.com/docs/en/channels-reference)
16. <https://code.claude.com/docs/en/claude-code-on-the-web>
17. [Use the Claude Agent SDK with your Claude plan](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan)
18. [GitHub - EuleMitKeule/webhook-conversation: 🤖 Home Assistant custom integration for using webhook-based systems (e.g. n8n) as conversation agents and voice assistants. · GitHub](https://github.com/eulemitkeule/webhook-conversation)
19. [Assist pipelines | Home Assistant Developer Docs](https://developers.home-assistant.io/docs/voice/pipelines/)
20. [Google Has To Open Android Wake Words. What That Could Mean for Home Assistant - Kiril Peyanski Blog](https://peyanski.com/google-open-android-wake-words-home-assistant/)
21. [Claude Cowork Dispatch and Remote Control — Control Your AI Agent From Your Phone](https://israynotarray.com/en/ai/2026/03/19/claude-cowork-dispatch-and-remote-control/)
22. [Push events into a running session with channels - Claude Code Docs](https://code.claude.com/docs/en/channels)
23. [Anthropic Pauses Claude Agent SDK Billing Overhaul](https://letsdatascience.com/news/anthropic-pauses-claude-agent-sdk-billing-overhaul-1cff2071)
24. [Anthropic officially bans using subscription authentication for third-party Claude use](https://alternativeto.net/news/2026/2/anthropic-officially-bans-using-subscription-authentication-for-third-party-claude-use)
25. [Background audio hardening | Android Developers](https://developer.android.com/about/versions/17/changes/bg-audio)
