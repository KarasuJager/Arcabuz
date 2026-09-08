# Security and evidence handling

FuzzRank imports potentially untrusted security-testing captures. It operates offline;
the only network-capable demonstration is a fixed scenario against its own temporary
loopback server. Doctor may execute installed external tools with version-only arguments.
No imported request, command, script, or response body is executed.

Reports, HAR files, headers, URLs, and raw archives may contain sensitive engagement data.
The tool preserves source bytes rather than redacting them. Keep outputs in access-controlled
local storage, and review/redact a separate copy before sharing. Generated output folders
and local virtual environments are excluded from version control by default.

HTML escapes metadata, treats URLs as text, disallows external resources with CSP, and
uses only a fixed inline script/style whose hashes are in the policy. JSON body content
is base64 encoded. Captured bodies are never interpreted as report markup.

Input limits bound files, bytes, records, and decoded bodies. They are not an operating-system
memory sandbox. For untrusted large inputs use tighter limits and isolated local storage.
Do not select an evidence/output directory that another untrusted process can replace
with filesystem links while analysis runs. Watch assumes cooperative local producers.

## Native desktop

The desktop uses plain-text native widgets, with no WebEngine or HTML evidence renderer.
URL copying is an explicit local clipboard action; links are not opened automatically.
Saved JSON reports are bounded, duplicate-key rejected, validated against the bundled
schema, and checked for inconsistent identities, references, counts, and score sums.
Opening a report restores its saved conclusions; it does not establish authenticity or
recompute its scores. Evidence archive references remain data and are never automatically
read or executed by the desktop report loader. JSON/HTML export uses the existing writers.
Preferences store appearance, default profile, and debounce only, without recent paths.

## Reporting a project security issue

Use GitHub Private Vulnerability Reporting: open the repository's **Security** tab,
then **Report a vulnerability**, when available. Otherwise use a maintainer-designated
private channel.
There is no security email address or response-time promise configured by this project.
Do not place secrets, live client captures, or exploit details in public issues.
Provide a minimal synthetic input and expected/actual behavior when possible.

If no private reporting route is available, open a public issue asking only for a private
contact route. Withhold technical details and attachments until a maintainer provides one.

Private reporting should be enabled before inviting security reports. FuzzRank itself
does not automatically upload evidence, send telemetry, or publish anything.
