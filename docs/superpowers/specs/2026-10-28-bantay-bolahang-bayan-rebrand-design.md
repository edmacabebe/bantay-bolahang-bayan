# Bantay Bolahang Bayan Rebrand Design

## Intent

Rebrand the public research project as **Bantay Bolahang Bayan** without
misrepresenting its purpose, legal posture, or statistical limitations.

## Selected approach

Use a branding-and-repository rename. Rename the GitHub repository slug to
`bantay-bolahang-bayan`; update the project title, package metadata, repository
links, collector user-agent, operational documentation, Codex monitor prompt,
and release presentation. Preserve the stable Python import package
`lotto_signal`, command `lotto-signal`, stored data formats, audit family IDs,
prediction IDs, and historical Git data.

## Alternatives considered

- A complete technical rename would also change imports, commands, data IDs,
  and audit identifiers. It was rejected because it adds migration risk without
  improving the public brand.
- A display-name-only change would leave the old GitHub URL and metadata. It
  was rejected because it would be an incomplete rebrand.

## Constraints

- Keep the README explicit that this is open-source statistical research using
  official PCSO results; do not imply PCSO affiliation or guaranteed winnings.
- Keep production research-signal notifications disabled.
- Preserve all deterministic audit evidence and historical records.
- Rely on GitHub's redirect from the old repository URL, then update the local
  `origin` remote to the new canonical URL.
- Verify the full test suite, public repository metadata, scheduled workflow,
  raw alert URLs, and the existing release after the rename.

## Success criteria

The public repository is available as
`edmacabebe/bantay-bolahang-bayan`, the cloud monitor still passes, all links
used by the Codex notification contract resolve to the new canonical address,
and no runtime or evidence behavior changes.
