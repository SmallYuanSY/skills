# Setting up Apple WeatherKit (optional)

weatherwise works without this. WeatherKit adds Apple Weather data, and official weather alerts in countries where Apple has them: for example the US, but not Taiwan or Japan (as of 2026-10). Where Apple has no alerts, the output still says `alerts: unsupported`. It needs a paid Apple Developer Program membership (US$99/year), which includes 500,000 WeatherKit calls a month.

Guide the user one step at a time. Steps 1–4 happen on Apple's website and only the user can do them.

## Before you start

Run `config show`, then ask the user what they already have. Skip every step they've done.

- **WeatherKit is already set up** (a `weatherkit:` line, or a `notice: weatherkit_auth_failed` after a key was revoked): the Team ID and Service ID stay the same. The user only needs a new key (step 3). Then run `config weatherkit --key-file <path to the new .p8>`; it keeps the saved IDs.
- **They already have a key and IDs** (for example from another app): ask for the Team ID, the Service ID, and the `.p8` path, then go to step 5.
- **Nothing yet**: start at step 1.

Never guess an ID or retype one from the shortened form `config show` prints. If one is missing, ask the user.

## 1. Join the Apple Developer Program

https://developer.apple.com/programs/ → Enroll. Approval can take a day or two.

## 2. Register a Services ID

Certificates, Identifiers & Profiles → Identifiers → **+** → **Services IDs**. Use a reverse-domain name such as `com.example.weatherwise`. This is the **Service ID**.

## 3. Create a key with WeatherKit enabled

Certificates, Identifiers & Profiles → Keys → **+** → give it a name → tick **WeatherKit** → Continue → Register → **Download**.

The file is named `AuthKey_<KeyID>.p8`. It can only be downloaded once, so the user should keep it somewhere safe. The Key ID is in the file name; there's no need to look it up.

## 4. Find the Team ID

Top right of the developer website, or Membership details. It's 10 characters.

## 5. Save the settings

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py config weatherkit --team-id <TEAM_ID> --service-id <SERVICE_ID> --key-file <path to AuthKey_XXXX.p8>
```

This makes one real request first and only saves if it works. It copies the key into `~/.config/weatherwise/` with permissions `600`, so the downloaded file can be moved or deleted afterwards.

The IDs are identifiers, not secrets (they appear in every WeatherKit request), but they will stay in the chat history. A user who prefers not to share them can run this command in their own terminal.

## 6. Check

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py config show
```

It should say `source: weatherkit`.

## Troubleshooting

- `weatherkit_auth_failed (HTTP 401)`: a wrong Team ID, Service ID, or Key ID, or the key was revoked. The error line shows which values were used and where each came from. Show them to the user and let them check each one; don't try other values. A brand-new key can take a few minutes to start working.
- `weatherkit_auth_failed (HTTP 403)`: the key doesn't have WeatherKit enabled.
- The `.p8` key never expires, but WeatherKit stops working if the Apple Developer membership lapses, and works again after renewal. Meanwhile weatherwise switches to the free source on its own and says so in a `notice:` line.
- To stop using WeatherKit: `uv run ${CLAUDE_SKILL_DIR}/scripts/weatherwise.py config weatherkit --remove`
